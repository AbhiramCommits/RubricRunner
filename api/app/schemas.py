from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Courses / assignments / rubric
# ---------------------------------------------------------------------------


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class RubricCriterionIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    max_points: float = Field(gt=0)
    weight: float = Field(default=1.0, gt=0)
    order_index: int = 0


class RubricCriterionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assignment_id: int
    name: str
    description: str
    max_points: float
    weight: float
    order_index: int


class AssignmentCreate(BaseModel):
    course_id: int | None = None
    course_name: str | None = None
    title: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)
    max_points: float | None = Field(default=None, gt=0)
    rubric: list[RubricCriterionIn] = Field(default_factory=list)


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    course_name: str
    title: str
    prompt_text: str
    max_points: float
    created_at: datetime
    criteria: list[RubricCriterionOut]


class AssignmentSummary(BaseModel):
    id: int
    course_id: int
    course_name: str
    title: str
    max_points: float
    submission_count: int
    graded_count: int
    needs_review_count: int
    published_count: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Roster / submissions / versions
# ---------------------------------------------------------------------------


class CriterionScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criterion_id: int
    criterion_name: str
    points: float
    confidence: float | None
    justification: str


class FeedbackVersionOut(BaseModel):
    id: int
    submission_id: int
    grading_run_id: int | None
    source: str
    parent_version_id: int | None
    summary_comment: str
    total_points: float
    needs_review: bool
    raw_model_output: dict[str, Any] | None
    prompt_version: str
    created_by: str
    created_at: datetime
    criteria: list[CriterionScoreOut]


class RosterEntry(BaseModel):
    student_id: int
    submission_id: int
    external_id: str
    name: str
    status: str
    ai_total: float | None
    current_total: float | None
    lowest_confidence: float | None
    published_version_id: int | None


class SubmissionOut(BaseModel):
    id: int
    assignment_id: int
    assignment_title: str
    student_id: int
    student_name: str
    student_external_id: str
    text: str
    submitted_at: datetime
    max_points: float
    rubric: list[RubricCriterionOut]
    versions: list[FeedbackVersionOut]
    published_version_id: int | None


# ---------------------------------------------------------------------------
# Teacher edits / publishing / audit
# ---------------------------------------------------------------------------


class CriterionScoreIn(BaseModel):
    criterion_id: int
    points: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    justification: str = ""


class TeacherEditIn(BaseModel):
    parent_version_id: int
    summary_comment: str = ""
    criteria: list[CriterionScoreIn] = Field(min_length=1)
    created_by: str = "instructor@example.edu"


class PublishIn(BaseModel):
    feedback_version_id: int
    published_by: str = "instructor@example.edu"


class PublishedGradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    submission_id: int
    feedback_version_id: int
    published_at: datetime
    published_by: str


class AuditTrailOut(BaseModel):
    submission_id: int
    published: PublishedGradeOut
    chain: list[FeedbackVersionOut]


# ---------------------------------------------------------------------------
# Grading runs (populated by the batch queue in step 4)
# ---------------------------------------------------------------------------


class GradingRunItemOut(BaseModel):
    submission_id: int
    student_name: str
    student_external_id: str
    status: str
    attempts: int
    error: str | None
    feedback_version_id: int | None
    needs_review: bool | None = None
    total_points: float | None = None


class GradingRunOut(BaseModel):
    id: int
    assignment_id: int
    prompt_version: str
    provider: str
    model: str
    status: str
    total: int
    completed: int
    failed: int
    started_at: datetime | None
    finished_at: datetime | None
    error_summary: str | None
    duration_seconds: float | None
    outcomes: list[GradingRunItemOut] = Field(default_factory=list)


class GradingRunCreate(BaseModel):
    prompt_version: str = "v2_criterion_anchored"


class GradingRunQueued(BaseModel):
    run_id: int
    status: str
