from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Assignment, Course, RubricCriterion, Submission
from app.schemas import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentSummary,
    RosterEntry,
)
from app.services import (
    assignment_out,
    assignment_summary,
    load_submissions_for_assignment,
    roster_entry,
)

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate, session: Session = Depends(get_session)
) -> AssignmentOut:
    if payload.course_id is not None:
        course = session.get(Course, payload.course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")
    elif payload.course_name:
        course = session.scalars(
            select(Course).where(Course.name == payload.course_name)
        ).first()
        if course is None:
            course = Course(name=payload.course_name)
            session.add(course)
            session.flush()
    else:
        raise HTTPException(status_code=422, detail="Provide course_id or course_name")

    rubric_total = sum(criterion.max_points for criterion in payload.rubric)
    max_points = payload.max_points if payload.max_points is not None else (rubric_total or 100.0)

    assignment = Assignment(
        course_id=course.id,
        title=payload.title,
        prompt_text=payload.prompt_text,
        max_points=max_points,
    )
    assignment.criteria = [
        RubricCriterion(
            name=criterion.name,
            description=criterion.description,
            max_points=criterion.max_points,
            weight=criterion.weight,
            order_index=criterion.order_index or index,
        )
        for index, criterion in enumerate(payload.rubric)
    ]
    session.add(assignment)
    session.commit()
    session.refresh(assignment, attribute_names=["course", "criteria"])
    return assignment_out(assignment)


@router.get("", response_model=list[AssignmentSummary])
def list_assignments(session: Session = Depends(get_session)) -> list[AssignmentSummary]:
    assignments = session.scalars(
        select(Assignment)
        .options(
            selectinload(Assignment.course),
            selectinload(Assignment.criteria),
            selectinload(Assignment.submissions).selectinload(Submission.versions),
            selectinload(Assignment.submissions).selectinload(Submission.published_grade),
            selectinload(Assignment.submissions).selectinload(Submission.student),
        )
        .order_by(Assignment.id)
    ).all()
    return [assignment_summary(assignment) for assignment in assignments]


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(assignment_id: int, session: Session = Depends(get_session)) -> AssignmentOut:
    assignment = session.scalars(
        select(Assignment)
        .where(Assignment.id == assignment_id)
        .options(selectinload(Assignment.course), selectinload(Assignment.criteria))
    ).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment_out(assignment)


@router.get("/{assignment_id}/roster", response_model=list[RosterEntry])
def get_roster(assignment_id: int, session: Session = Depends(get_session)) -> list[RosterEntry]:
    assignment = session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    submissions = load_submissions_for_assignment(session, assignment_id)
    entries = [roster_entry(submission) for submission in submissions]
    return sorted(entries, key=lambda entry: entry.external_id)
