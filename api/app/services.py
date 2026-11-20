from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Assignment,
    CriterionScore,
    FeedbackVersion,
    GradingRun,
    PublishedGrade,
    Submission,
)
from app.schemas import (
    AssignmentOut,
    AssignmentSummary,
    CriterionScoreOut,
    FeedbackVersionOut,
    GradingRunItemOut,
    GradingRunOut,
    RosterEntry,
    RubricCriterionOut,
    SubmissionOut,
)

STATUS_UNGRADED = "ungraded"
STATUS_AI_GRADED = "ai_graded"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_TEACHER_EDITED = "teacher_edited"
STATUS_PUBLISHED = "published"


def _submission_query() -> Select[Submission]:
    return select(Submission).options(
        selectinload(Submission.student),
        selectinload(Submission.published_grade),
        selectinload(Submission.versions)
        .selectinload(FeedbackVersion.scores)
        .selectinload(CriterionScore.criterion),
    )


def load_submission(session: Session, submission_id: int) -> Submission | None:
    return session.scalars(_submission_query().where(Submission.id == submission_id)).first()


def load_submissions_for_assignment(session: Session, assignment_id: int) -> list[Submission]:
    stmt = _submission_query().where(Submission.assignment_id == assignment_id).order_by(
        Submission.student_id
    )
    return list(session.scalars(stmt).all())


def criterion_score_out(score: CriterionScore) -> CriterionScoreOut:
    return CriterionScoreOut(
        id=score.id,
        criterion_id=score.criterion_id,
        criterion_name=score.criterion.name,
        points=score.points,
        confidence=score.confidence,
        justification=score.justification,
    )


def feedback_version_out(version: FeedbackVersion) -> FeedbackVersionOut:
    return FeedbackVersionOut(
        id=version.id,
        submission_id=version.submission_id,
        grading_run_id=version.grading_run_id,
        source=version.source,
        parent_version_id=version.parent_version_id,
        summary_comment=version.summary_comment,
        total_points=version.total_points,
        needs_review=version.needs_review,
        raw_model_output=version.raw_model_output,
        prompt_version=version.prompt_version,
        created_by=version.created_by,
        created_at=version.created_at,
        criteria=[criterion_score_out(score) for score in version.scores],
    )


def assignment_out(assignment: Assignment) -> AssignmentOut:
    return AssignmentOut(
        id=assignment.id,
        course_id=assignment.course_id,
        course_name=assignment.course.name,
        title=assignment.title,
        prompt_text=assignment.prompt_text,
        max_points=assignment.max_points,
        created_at=assignment.created_at,
        criteria=[RubricCriterionOut.model_validate(c) for c in assignment.criteria],
    )


def submission_out(submission: Submission) -> SubmissionOut:
    assignment = submission.assignment
    published = submission.published_grade
    return SubmissionOut(
        id=submission.id,
        assignment_id=submission.assignment_id,
        assignment_title=assignment.title,
        student_id=submission.student_id,
        student_name=submission.student.name,
        student_external_id=submission.student.external_id,
        text=submission.text,
        submitted_at=submission.submitted_at,
        max_points=assignment.max_points,
        rubric=[RubricCriterionOut.model_validate(c) for c in assignment.criteria],
        versions=[feedback_version_out(v) for v in submission.versions],
        published_version_id=published.feedback_version_id if published else None,
    )


def latest_version(submission: Submission) -> FeedbackVersion | None:
    return submission.versions[-1] if submission.versions else None


def latest_ai_version(submission: Submission) -> FeedbackVersion | None:
    for version in reversed(submission.versions):
        if version.source == "ai":
            return version
    return None


def roster_status(submission: Submission) -> str:
    latest = latest_version(submission)
    published = submission.published_grade
    if latest is None:
        return STATUS_UNGRADED
    if published is not None and published.feedback_version_id == latest.id:
        return STATUS_PUBLISHED
    if latest.source == "teacher":
        return STATUS_TEACHER_EDITED
    if latest.needs_review:
        return STATUS_NEEDS_REVIEW
    return STATUS_AI_GRADED


def roster_entry(submission: Submission) -> RosterEntry:
    latest = latest_version(submission)
    ai_version = latest_ai_version(submission)
    confidence_values = [
        score.confidence
        for score in (ai_version.scores if ai_version else [])
        if score.confidence is not None
    ]
    published = submission.published_grade
    return RosterEntry(
        student_id=submission.student_id,
        submission_id=submission.id,
        external_id=submission.student.external_id,
        name=submission.student.name,
        status=roster_status(submission),
        ai_total=ai_version.total_points if ai_version else None,
        current_total=latest.total_points if latest else None,
        lowest_confidence=min(confidence_values) if confidence_values else None,
        published_version_id=published.feedback_version_id if published else None,
    )


def assignment_summary(assignment: Assignment) -> AssignmentSummary:
    submissions = assignment.submissions
    statuses = [roster_status(s) for s in submissions]
    return AssignmentSummary(
        id=assignment.id,
        course_id=assignment.course_id,
        course_name=assignment.course.name,
        title=assignment.title,
        max_points=assignment.max_points,
        submission_count=len(submissions),
        graded_count=sum(1 for status in statuses if status != STATUS_UNGRADED),
        needs_review_count=sum(1 for status in statuses if status == STATUS_NEEDS_REVIEW),
        published_count=sum(1 for status in statuses if status == STATUS_PUBLISHED),
        created_at=assignment.created_at,
    )


def audit_chain(
    session: Session, submission: Submission, published: PublishedGrade
) -> list[FeedbackVersion]:
    """Walk parent pointers from the published version to the originating version."""
    chain: list[FeedbackVersion] = []
    version: FeedbackVersion | None = session.get(FeedbackVersion, published.feedback_version_id)
    seen: set[int] = set()
    while version is not None and version.id not in seen:
        seen.add(version.id)
        chain.append(version)
        if version.parent_version_id is None:
            break
        version = session.get(FeedbackVersion, version.parent_version_id)
    if not chain or chain[0].submission_id != submission.id:
        return []
    chain.reverse()
    return chain


def grading_run_out(run: GradingRun) -> GradingRunOut:  # noqa: F821
    from app.schemas import GradingRunItemOut, GradingRunOut

    outcomes: list[GradingRunItemOut] = []
    for item in run.items:
        version = next((v for v in run.versions if v.id == item.feedback_version_id), None)
        outcomes.append(
            GradingRunItemOut(
                submission_id=item.submission_id,
                student_name=item.submission.student.name,
                student_external_id=item.submission.student.external_id,
                status=item.status,
                attempts=item.attempts,
                error=item.error,
                feedback_version_id=item.feedback_version_id,
                needs_review=version.needs_review if version else None,
                total_points=version.total_points if version else None,
            )
        )
    duration = None
    if run.started_at is not None and run.finished_at is not None:
        duration = round((run.finished_at - run.started_at).total_seconds(), 3)
    return GradingRunOut(
        id=run.id,
        assignment_id=run.assignment_id,
        prompt_version=run.prompt_version,
        provider=run.provider,
        model=run.model,
        status=run.status,
        total=run.total,
        completed=run.completed,
        failed=run.failed,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_summary=run.error_summary,
        duration_seconds=duration,
        outcomes=outcomes,
    )
