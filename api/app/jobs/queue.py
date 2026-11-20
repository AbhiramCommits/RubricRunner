"""In-process asyncio worker pool backed by the grading_runs table.

Runs are durable: a row is inserted as `queued`, claimed by a worker with
`SELECT ... FOR UPDATE SKIP LOCKED`, and marked `running` until it reaches a
terminal state. If the API restarts, `requeue_running_runs` puts orphaned runs
back in the queue and the runner resumes any submissions that were not graded.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import SessionLocal
from app.grading.providers import LLMProvider, build_provider, provider_metadata
from app.models import Assignment, GradingRun, RunStatus, Submission

logger = logging.getLogger(__name__)

_session_factory: sessionmaker[Session] = SessionLocal
_provider_factory: Callable[[], LLMProvider] = build_provider


def configure_session_factory(factory: sessionmaker[Session]) -> None:
    """Point the queue at another database (used by the test suite)."""
    global _session_factory
    _session_factory = factory


def get_session_factory() -> sessionmaker[Session]:
    return _session_factory


def configure_provider_factory(factory: Callable[[], LLMProvider]) -> None:
    global _provider_factory
    _provider_factory = factory


def get_provider_factory() -> Callable[[], LLMProvider]:
    return _provider_factory


def enqueue_run(assignment_id: int, prompt_version: str) -> int:
    """Insert a queued run and return its id. The assignment must exist."""
    assignment = None
    with _session_factory() as session:
        assignment = session.get(Assignment, assignment_id)
        if assignment is None:
            raise LookupError(f"Assignment {assignment_id} not found")
        submitted = session.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.assignment_id == assignment_id
            )
        )
        provider_name, model = provider_metadata()
        run = GradingRun(
            assignment_id=assignment_id,
            prompt_version=prompt_version,
            provider=provider_name,
            model=model,
            status=RunStatus.queued.value,
            total=int(submitted or 0),
        )
        session.add(run)
        session.commit()
        run_id = run.id
    logger.info("queued grading run %s for assignment %s", run_id, assignment_id)
    return run_id


def claim_run() -> int | None:
    """Atomically claim the oldest queued run."""
    with _session_factory() as session:
        run = session.scalars(
            select(GradingRun)
            .where(GradingRun.status == RunStatus.queued.value)
            .order_by(GradingRun.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        ).first()
        if run is None:
            session.rollback()
            return None
        run.status = RunStatus.running.value
        run.started_at = run.started_at or datetime.now(UTC)
        session.commit()
        return run.id


def requeue_running_runs() -> int:
    """Requeue runs orphaned by a restart; the runner resumes their work."""
    with _session_factory() as session:
        runs = session.scalars(
            select(GradingRun).where(GradingRun.status == RunStatus.running.value)
        ).all()
        for run in runs:
            run.status = RunStatus.queued.value
            run.finished_at = None
        session.commit()
        return len(runs)


class GradingQueue:
    def __init__(self, concurrency: int | None = None) -> None:
        settings = get_settings()
        self.concurrency = max(1, concurrency or settings.grading_concurrency)
        self._wake = asyncio.Event()
        self._workers: list[asyncio.Task[None]] = []
        self._started = False
        self._shutdown = False

    async def start(self) -> None:
        if self._started:
            return
        self._shutdown = False
        self._wake = asyncio.Event()
        requeued = await asyncio.to_thread(requeue_running_runs)
        if requeued:
            logger.info("requeued %d run(s) after restart", requeued)
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"grading-worker-{index}")
            for index in range(self.concurrency)
        ]
        self._started = True
        self._wake.set()

    async def stop(self) -> None:
        self._shutdown = True
        self._wake.set()
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []
        self._started = False

    async def notify(self) -> None:
        self._wake.set()

    async def _worker(self, index: int) -> None:
        from app.jobs.runner import execute_run

        while not self._shutdown:
            await self._wake.wait()
            if self._shutdown:
                return
            self._wake.clear()
            while not self._shutdown:
                run_id = await asyncio.to_thread(claim_run)
                if run_id is None:
                    break
                logger.info("worker %d claimed run %s", index, run_id)
                try:
                    await asyncio.to_thread(
                        execute_run,
                        run_id,
                        get_session_factory(),
                        get_provider_factory(),
                    )
                except Exception:
                    logger.exception("run %s crashed outside per-submission handling", run_id)


grading_queue = GradingQueue()
