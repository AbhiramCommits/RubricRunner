from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    partial = "partial"
    failed = "failed"


class FeedbackSource(enum.StrEnum):
    ai = "ai"
    teacher = "teacher"


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    students: Mapped[list[Student]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    max_points: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    course: Mapped[Course] = relationship(back_populates="assignments")
    criteria: Mapped[list[RubricCriterion]] = relationship(
        back_populates="assignment",
        cascade="all, delete-orphan",
        order_by="RubricCriterion.order_index",
    )
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )
    grading_runs: Mapped[list[GradingRun]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan"
    )


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_points: Mapped[float] = mapped_column(Float, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assignment: Mapped[Assignment] = relationship(back_populates="criteria")
    scores: Mapped[list[CriterionScore]] = relationship(back_populates="criterion")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("course_id", "external_id", name="uq_student_course_ext"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    course: Mapped[Course] = relationship(back_populates="students")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "student_id", name="uq_submission_assignment_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    student: Mapped[Student] = relationship(back_populates="submissions")
    versions: Mapped[list[FeedbackVersion]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="FeedbackVersion.id",
    )
    published_grade: Mapped[PublishedGrade | None] = relationship(
        back_populates="submission", cascade="all, delete-orphan", uselist=False
    )


class GradingRun(Base):
    __tablename__ = "grading_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RunStatus.queued.value)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)

    assignment: Mapped[Assignment] = relationship(back_populates="grading_runs")
    items: Mapped[list[GradingRunItem]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="GradingRunItem.id"
    )
    versions: Mapped[list[FeedbackVersion]] = relationship(back_populates="grading_run")


class GradingRunItem(Base):
    """Per-submission outcome for a grading run (success or failure + attempts)."""

    __tablename__ = "grading_run_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grading_run_id: Mapped[int] = mapped_column(
        ForeignKey("grading_runs.id", ondelete="CASCADE"), index=True
    )
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    feedback_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("feedback_versions.id", ondelete="SET NULL")
    )

    run: Mapped[GradingRun] = relationship(back_populates="items")
    submission: Mapped[Submission] = relationship()


class FeedbackVersion(Base):
    __tablename__ = "feedback_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), index=True
    )
    grading_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("grading_runs.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("feedback_versions.id", ondelete="SET NULL")
    )
    summary_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    total_points: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_model_output: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    submission: Mapped[Submission] = relationship(back_populates="versions")
    grading_run: Mapped[GradingRun | None] = relationship(back_populates="versions")
    parent: Mapped[FeedbackVersion | None] = relationship(remote_side="FeedbackVersion.id")
    scores: Mapped[list[CriterionScore]] = relationship(
        back_populates="feedback_version",
        cascade="all, delete-orphan",
        order_by="CriterionScore.id",
    )


class CriterionScore(Base):
    __tablename__ = "criterion_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feedback_version_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_versions.id", ondelete="CASCADE"), index=True
    )
    criterion_id: Mapped[int] = mapped_column(
        ForeignKey("rubric_criteria.id", ondelete="CASCADE"), index=True
    )
    points: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    justification: Mapped[str] = mapped_column(Text, nullable=False, default="")

    feedback_version: Mapped[FeedbackVersion] = relationship(back_populates="scores")
    criterion: Mapped[RubricCriterion] = relationship(back_populates="scores")


class PublishedGrade(Base):
    __tablename__ = "published_grades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    feedback_version_id: Mapped[int] = mapped_column(
        ForeignKey("feedback_versions.id", ondelete="RESTRICT"), nullable=False
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_by: Mapped[str] = mapped_column(String(200), nullable=False, default="instructor")

    submission: Mapped[Submission] = relationship(back_populates="published_grade")
    feedback_version: Mapped[FeedbackVersion] = relationship()
