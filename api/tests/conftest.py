from __future__ import annotations

import os
from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_session
from app.main import app
from app.models import (
    Assignment,
    Base,
    Course,
    FeedbackVersion,
    RubricCriterion,
    Student,
    Submission,
)

settings = get_settings()


def _database_urls() -> tuple[str, str]:
    if url_env := os.environ.get("TEST_DATABASE_URL"):
        test_url = make_url(url_env)
    else:
        test_url = make_url(settings.database_url).set(database="rubricrunner_test")
    admin_url = test_url.set(database="postgres")
    return test_url.render_as_string(hide_password=False), admin_url.render_as_string(
        hide_password=False
    )


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    test_url, admin_url = _database_urls()
    database = make_url(test_url).database
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": database}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{database}"'))
    admin.dispose()

    test_engine = create_engine(test_url, pool_pre_ping=True)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine) -> Generator[sessionmaker[Session], None, None]:
    table_names = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory


@pytest.fixture()
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    from app.grading.providers import build_provider
    from app.jobs.queue import configure_provider_factory, configure_session_factory

    configure_session_factory(session_factory)
    configure_provider_factory(build_provider)

    def override_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    configure_provider_factory(build_provider)


@pytest.fixture()
def seeded(session_factory: sessionmaker[Session]) -> dict[str, int]:
    from seed import seed

    return seed(session_factory)


@pytest.fixture()
def demo(session_factory: sessionmaker[Session]) -> dict[str, object]:
    """Minimal course, assignment, four students, and four submissions."""
    with session_factory() as session:
        course = Course(name="Test Course")
        session.add(course)
        session.flush()
        assignment = Assignment(
            course_id=course.id,
            title="Test Essay",
            prompt_text="Argue something.",
            max_points=25,
        )
        assignment.criteria = [
            RubricCriterion(name="Thesis", description="Clear thesis", max_points=5, order_index=0),
            RubricCriterion(name="Evidence", description="Uses evidence", max_points=10, order_index=1),
            RubricCriterion(name="Organization", description="Logical order", max_points=5, order_index=2),
            RubricCriterion(name="Mechanics", description="Clean prose", max_points=5, order_index=3),
        ]
        session.add(assignment)
        session.flush()

        students: list[Student] = []
        submissions: list[Submission] = []
        for index in range(1, 5):
            student = Student(
                course_id=course.id, external_id=f"T{index:02d}", name=f"Student {index}"
            )
            session.add(student)
            session.flush()
            submission = Submission(
                assignment_id=assignment.id,
                student_id=student.id,
                text=f"Submission text for student {index}.",
                submitted_at=datetime.now(UTC),
            )
            session.add(submission)
            students.append(student)
            submissions.append(submission)
        session.commit()
        return {
            "course_id": course.id,
            "assignment_id": assignment.id,
            "criterion_ids": [criterion.id for criterion in assignment.criteria],
            "student_ids": [student.id for student in students],
            "submission_ids": [submission.id for submission in submissions],
        }


def add_ai_version(
    session: Session,
    submission_id: int,
    points: list[float],
    confidences: list[float] | None = None,
    needs_review: bool = False,
    prompt_version: str = "v2_criterion_anchored",
) -> FeedbackVersion:
    from app.models import CriterionScore

    submission = session.get(Submission, submission_id)
    assert submission is not None
    criteria = submission.assignment.criteria
    version = FeedbackVersion(
        submission_id=submission_id,
        source="ai",
        summary_comment="AI summary",
        total_points=sum(points),
        needs_review=needs_review,
        raw_model_output={"criteria": [], "summary_comment": "AI summary"},
        prompt_version=prompt_version,
        created_by="system",
    )
    version.scores = [
        CriterionScore(
            criterion_id=criteria[index].id,
            points=points[index],
            confidence=(confidences[index] if confidences else 0.9),
            justification=f"Justification {index}",
        )
        for index in range(len(criteria))
    ]
    session.add(version)
    session.commit()
    return version
