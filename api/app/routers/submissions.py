from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Assignment
from app.schemas import SubmissionOut
from app.services import load_submission, load_submissions_for_assignment, submission_out

router = APIRouter(tags=["submissions"])


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: int, session: Session = Depends(get_session)) -> SubmissionOut:
    submission = load_submission(session, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission_out(submission)


@router.get("/assignments/{assignment_id}/submissions", response_model=list[SubmissionOut])
def list_submissions(
    assignment_id: int, session: Session = Depends(get_session)
) -> list[SubmissionOut]:
    if session.get(Assignment, assignment_id) is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    submissions = load_submissions_for_assignment(session, assignment_id)
    return [submission_out(submission) for submission in submissions]
