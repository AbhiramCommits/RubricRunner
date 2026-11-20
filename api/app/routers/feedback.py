from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    CriterionScore,
    FeedbackVersion,
    PublishedGrade,
    RubricCriterion,
)
from app.schemas import (
    AuditTrailOut,
    FeedbackVersionOut,
    PublishedGradeOut,
    PublishIn,
    TeacherEditIn,
)
from app.services import audit_chain, feedback_version_out, load_submission

router = APIRouter(tags=["feedback"])


@router.post(
    "/submissions/{submission_id}/feedback-versions",
    response_model=FeedbackVersionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_teacher_version(
    submission_id: int,
    payload: TeacherEditIn,
    session: Session = Depends(get_session),
) -> FeedbackVersionOut:
    submission = load_submission(session, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    parent = session.get(FeedbackVersion, payload.parent_version_id)
    if parent is None or parent.submission_id != submission_id:
        raise HTTPException(
            status_code=422, detail="parent_version_id does not belong to submission"
        )

    criteria = {
        criterion.id: criterion
        for criterion in session.scalars(
            select(RubricCriterion).where(
                RubricCriterion.assignment_id == submission.assignment_id
            )
        ).all()
    }
    provided_ids = [score.criterion_id for score in payload.criteria]
    if len(set(provided_ids)) != len(provided_ids):
        raise HTTPException(status_code=422, detail="Duplicate criterion_id in payload")
    if set(provided_ids) != set(criteria):
        raise HTTPException(
            status_code=422,
            detail="Teacher version must include exactly one score for every rubric criterion",
        )

    scores: list[CriterionScore] = []
    for score in payload.criteria:
        criterion = criteria[score.criterion_id]
        if score.points > criterion.max_points:
            raise HTTPException(
                status_code=422,
                detail=f"points for {criterion.name} exceed max of {criterion.max_points}",
            )
        scores.append(
            CriterionScore(
                criterion_id=criterion.id,
                points=score.points,
                confidence=score.confidence,
                justification=score.justification,
            )
        )

    version = FeedbackVersion(
        submission_id=submission_id,
        grading_run_id=None,
        source="teacher",
        parent_version_id=parent.id,
        summary_comment=payload.summary_comment,
        total_points=sum(score.points for score in scores),
        needs_review=False,
        raw_model_output=None,
        prompt_version=parent.prompt_version,
        created_by=payload.created_by,
    )
    version.scores = scores
    session.add(version)
    session.commit()

    stored = session.get(FeedbackVersion, version.id)
    assert stored is not None
    session.refresh(stored, attribute_names=["scores"])
    for stored_score in stored.scores:
        session.refresh(stored_score, attribute_names=["criterion"])
    return feedback_version_out(stored)


@router.post("/submissions/{submission_id}/publish", response_model=PublishedGradeOut)
def publish(
    submission_id: int,
    payload: PublishIn,
    session: Session = Depends(get_session),
) -> PublishedGradeOut:
    submission = load_submission(session, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    version = session.get(FeedbackVersion, payload.feedback_version_id)
    if version is None or version.submission_id != submission_id:
        raise HTTPException(
            status_code=422, detail="feedback_version_id does not belong to submission"
        )
    if version.needs_review:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Version is flagged needs_review and cannot be published without teacher approval"
            ),
        )

    existing = session.scalars(
        select(PublishedGrade).where(PublishedGrade.submission_id == submission_id)
    ).first()
    if existing is None:
        published = PublishedGrade(
            submission_id=submission_id,
            feedback_version_id=version.id,
            published_by=payload.published_by,
        )
        session.add(published)
    else:
        existing.feedback_version_id = version.id
        existing.published_by = payload.published_by
        published = existing
    session.commit()
    session.refresh(published)
    return PublishedGradeOut.model_validate(published)


@router.get("/submissions/{submission_id}/audit-trail", response_model=AuditTrailOut)
def get_audit_trail(
    submission_id: int, session: Session = Depends(get_session)
) -> AuditTrailOut:
    submission = load_submission(session, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    published = session.scalars(
        select(PublishedGrade).where(PublishedGrade.submission_id == submission_id)
    ).first()
    if published is None:
        raise HTTPException(status_code=404, detail="Submission has not been published")
    chain = audit_chain(session, submission, published)
    for version in chain:
        session.refresh(version, attribute_names=["scores"])
        for score in version.scores:
            session.refresh(score, attribute_names=["criterion"])
    return AuditTrailOut(
        submission_id=submission_id,
        published=PublishedGradeOut.model_validate(published),
        chain=[feedback_version_out(version) for version in chain],
    )
