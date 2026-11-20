from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.grading.grader import GradingError, grade_submission, run_grading
from app.grading.providers import MockProvider
from app.grading.schema import GradeResult
from app.models import Assignment, FeedbackVersion, Submission
from tests.conftest import add_ai_version

CRITERIA = ["Thesis", "Evidence", "Organization", "Mechanics"]


class ScriptedProvider:
    name = "scripted"
    model = "scripted-v1"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append(user)
        if not self.responses:
            raise AssertionError("ScriptedProvider exhausted")
        return self.responses.pop(0)


def grade_json(
    points: list[float],
    confidences: list[float] | None = None,
    summary: str = "A solid effort overall; focus on sharper evidence next time.",
) -> str:
    confidences = confidences or [0.9] * len(points)
    return json.dumps(
        {
            "criteria": [
                {
                    "criterion_name": CRITERIA[index],
                    "points": points[index],
                    "confidence": confidences[index],
                    "justification": f"Reason for {CRITERIA[index]}.",
                }
                for index in range(len(CRITERIA))
            ],
            "summary_comment": summary,
        }
    )


def test_grade_result_rejects_malformed_output(session_factory: sessionmaker[Session], demo: dict[str, object]) -> None:
    with session_factory() as session:
        assignment = session.get(Assignment, demo["assignment_id"])
        assert assignment is not None
        rubric = assignment.criteria

        unknown = GradeResult.model_validate(json.loads(grade_json([3, 5, 3, 3])))
        unknown.criteria[0].criterion_name = "Grammar"
        with pytest.raises(ValueError, match="Unknown criterion"):
            unknown.validate_against(rubric)

        missing = GradeResult.model_validate(json.loads(grade_json([3, 5, 3, 3])))
        missing.criteria.pop()
        with pytest.raises(ValueError, match="Missing criteria"):
            missing.validate_against(rubric)

        out_of_range = GradeResult.model_validate(json.loads(grade_json([3, 12, 3, 3])))
        with pytest.raises(ValueError, match="exceed max"):
            out_of_range.validate_against(rubric)

        with pytest.raises(ValidationError):
            GradeResult.model_validate(
                {
                    "criteria": [
                        {
                            "criterion_name": "Thesis",
                            "points": 3,
                            "confidence": 1.5,
                            "justification": "x",
                        }
                    ],
                    "summary_comment": "x",
                }
            )


def test_retry_once_then_success(session_factory: sessionmaker[Session], demo: dict[str, object]) -> None:
    provider = ScriptedProvider(["this is not json at all", grade_json([4, 8, 4, 4])])
    with session_factory() as session:
        submission = session.get(
            Submission,
            demo["submission_ids"][0],
        )
        assert submission is not None
        assignment = submission.assignment
        version = grade_submission(session, submission, assignment, "v2_criterion_anchored", provider)

        assert len(provider.calls) == 2
        assert "REPAIR REQUIRED" in provider.calls[1]
        assert version.needs_review is True
        assert version.raw_model_output is not None
        assert version.raw_model_output["attempts"] == 2
        reasons = version.raw_model_output["needs_review_reasons"]
        assert any("repair retry" in reason for reason in reasons)

        versions = session.query(FeedbackVersion).filter_by(submission_id=submission.id).all()
        assert len(versions) == 1


def test_low_confidence_sets_needs_review(
    session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    provider = ScriptedProvider([grade_json([4, 8, 4, 4], [0.4, 0.4, 0.5, 0.5])])
    with session_factory() as session:
        submission = session.get(
            Submission,
            demo["submission_ids"][0],
        )
        assert submission is not None
        version = grade_submission(
            session, submission, submission.assignment, "v1_basic", provider
        )
        assert version.needs_review is True
        assert version.raw_model_output is not None
        reasons = version.raw_model_output["needs_review_reasons"]
        assert any("low confidence" in reason for reason in reasons)


def test_high_confidence_far_from_boundary_is_publishable(
    session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    provider = ScriptedProvider([grade_json([5, 9, 5, 5], [0.95] * 4)])
    with session_factory() as session:
        submission = session.get(
            Submission,
            demo["submission_ids"][1],
        )
        assert submission is not None
        version = grade_submission(
            session, submission, submission.assignment, "v2_criterion_anchored", provider
        )
        assert version.total_points == 24
        assert version.needs_review is False


def test_grading_appends_exactly_one_version_without_mutating_prior(
    session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    submission_id = demo["submission_ids"][0]
    with session_factory() as session:
        prior = add_ai_version(session, submission_id, [3, 5, 3, 3], [0.8] * 4, prompt_version="v1_basic")
        prior_id = prior.id
        prior_total = prior.total_points
        prior_scores = [(score.id, score.points) for score in prior.scores]

    provider = ScriptedProvider([grade_json([5, 9, 4, 4])])
    with session_factory() as session:
        submission = session.get(
            Submission, submission_id
        )
        assert submission is not None
        fresh = grade_submission(
            session, submission, submission.assignment, "v2_criterion_anchored", provider
        )
        fresh_id = fresh.id
        assert fresh.parent_version_id is None
        assert fresh.source == "ai"
        assert fresh.prompt_version == "v2_criterion_anchored"

    with session_factory() as session:
        versions = (
            session.query(FeedbackVersion)
            .filter_by(submission_id=submission_id)
            .order_by(FeedbackVersion.id)
            .all()
        )
        assert [version.id for version in versions] == [prior_id, fresh_id]
        stored_prior = versions[0]
        assert stored_prior.total_points == prior_total
        assert [(score.id, score.points) for score in stored_prior.scores] == prior_scores


def test_retry_exhaustion_raises(session_factory: sessionmaker[Session], demo: dict[str, object]) -> None:
    provider = ScriptedProvider(["junk", "still junk", "junk again"])
    with session_factory() as session:
        submission = session.get(
            Submission,
            demo["submission_ids"][0],
        )
        assert submission is not None
        with pytest.raises(GradingError, match="after 3 attempts"):
            grade_submission(
                session, submission, submission.assignment, "v2_criterion_anchored", provider
            )
        assert len(provider.calls) == 3


def test_mock_provider_is_deterministic_and_rubric_only(
    session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    with session_factory() as session:
        submission = session.get(
            Submission,
            demo["submission_ids"][2],
        )
        assert submission is not None
        assignment = submission.assignment
        first = run_grading(
            MockProvider(),
            assignment.title,
            assignment.prompt_text,
            submission.text,
            assignment.criteria,
            "v2_criterion_anchored",
        )
        second = run_grading(
            MockProvider(),
            assignment.title,
            assignment.prompt_text,
            submission.text,
            assignment.criteria,
            "v2_criterion_anchored",
        )
        assert first.result.model_dump() == second.result.model_dump()
        assert {item.criterion_name for item in first.result.criteria} == set(CRITERIA)
