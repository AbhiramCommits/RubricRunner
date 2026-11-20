from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.grading.prompts import get_prompt
from app.jobs.queue import enqueue_run, get_session_factory, grading_queue
from app.models import Assignment, GradingRun, GradingRunItem, RunStatus, Submission
from app.schemas import GradingRunCreate, GradingRunOut, GradingRunQueued
from app.services import grading_run_out

router = APIRouter(tags=["grading"])

TERMINAL_STATUSES = {
    RunStatus.succeeded.value,
    RunStatus.partial.value,
    RunStatus.failed.value,
}


def _run_options() -> list[Any]:
    return [
        selectinload(GradingRun.items)
        .selectinload(GradingRunItem.submission)
        .selectinload(Submission.student),
        selectinload(GradingRun.versions),
    ]


def _load_run(session: Session, run_id: int) -> GradingRun | None:
    return session.scalars(
        select(GradingRun).where(GradingRun.id == run_id).options(*_run_options())
    ).first()


@router.post(
    "/assignments/{assignment_id}/grading-runs",
    response_model=GradingRunQueued,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_grading_run(
    assignment_id: int,
    payload: GradingRunCreate,
    session: Session = Depends(get_session),
) -> GradingRunQueued:
    assignment = session.get(Assignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    try:
        get_prompt(payload.prompt_version)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    run_id = enqueue_run(assignment_id, payload.prompt_version)
    await grading_queue.notify()
    return GradingRunQueued(run_id=run_id, status=RunStatus.queued.value)


@router.get("/grading-runs", response_model=list[GradingRunOut])
def list_grading_runs(
    limit: int = 10, session: Session = Depends(get_session)
) -> list[GradingRunOut]:
    runs = session.scalars(
        select(GradingRun)
        .options(*_run_options())
        .order_by(GradingRun.id.desc())
        .limit(max(1, min(limit, 50)))
    ).all()
    return [grading_run_out(run) for run in runs]


@router.get("/grading-runs/{run_id}", response_model=GradingRunOut)
def get_grading_run(run_id: int, session: Session = Depends(get_session)) -> GradingRunOut:
    run = _load_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Grading run not found")
    return grading_run_out(run)


@router.get("/grading-runs/{run_id}/events")
async def grading_run_events(run_id: int) -> StreamingResponse:
    factory = get_session_factory()

    def snapshot() -> dict[str, object] | None:
        with factory() as session:
            run = session.get(GradingRun, run_id)
            if run is None:
                return None
            return {
                "completed": run.completed,
                "failed": run.failed,
                "total": run.total,
                "status": run.status,
            }

    async def event_stream() -> AsyncIterator[str]:
        last: dict[str, object] | None = None
        while True:
            payload = await asyncio.to_thread(snapshot)
            if payload is None:
                yield 'data: {"error": "not_found"}\n\n'
                return
            if payload != last:
                yield f"data: {json.dumps(payload)}\n\n"
                last = payload
            if payload["status"] in TERMINAL_STATUSES:
                return
            await asyncio.sleep(0.2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
