"""Grade a whole class through the durable run queue, printing live progress.

Usage:
    python -m scripts.grade_class --assignment-id 1 --prompt-version v2_criterion_anchored
"""

from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.jobs.queue import GradingQueue, configure_session_factory, enqueue_run
from app.models import FeedbackVersion, GradingRun, RunStatus

TERMINAL = {
    RunStatus.succeeded.value,
    RunStatus.partial.value,
    RunStatus.failed.value,
}


def _snapshot(run_id: int) -> tuple[int, int, int, str]:
    with SessionLocal() as session:
        run = session.get(GradingRun, run_id)
        if run is None:
            raise SystemExit(f"Run {run_id} disappeared")
        return run.completed, run.failed, run.total, run.status


async def _watch(run_id: int, timeout_seconds: float = 600.0) -> tuple[int, int, int, str]:
    queue = GradingQueue(concurrency=get_settings().grading_concurrency)
    await queue.start()
    started = time.monotonic()
    last_status = ""
    try:
        while True:
            completed, failed, total, status = await asyncio.to_thread(_snapshot, run_id)
            if status != last_status or completed + failed == total:
                print(
                    f"\rprogress: {completed + failed}/{total} processed "
                    f"({completed} ok, {failed} failed) [{status}]",
                    end="",
                    flush=True,
                )
                last_status = status
            if status in TERMINAL:
                print()
                return completed, failed, total, status
            if time.monotonic() - started > timeout_seconds:
                print()
                raise SystemExit(f"Timed out waiting for run {run_id} (status={status})")
            await asyncio.sleep(0.25)
    finally:
        await queue.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade every submission in an assignment")
    parser.add_argument("--assignment-id", type=int, required=True)
    parser.add_argument("--prompt-version", default="v2_criterion_anchored")
    args = parser.parse_args()

    configure_session_factory(SessionLocal)
    run_id = enqueue_run(args.assignment_id, args.prompt_version)
    print(f"Enqueued grading run {run_id} (assignment {args.assignment_id})")
    start = time.monotonic()
    completed, failed, total, status = asyncio.run(_watch(run_id))
    elapsed = time.monotonic() - start

    with SessionLocal() as session:
        needs_review = session.scalar(
            select(func.count())
            .select_from(FeedbackVersion)
            .where(
                FeedbackVersion.grading_run_id == run_id,
                FeedbackVersion.needs_review.is_(True),
            )
        )
    print(f"Run {run_id}: status={status} total={total} completed={completed} failed={failed}")
    print(f"needs_review={int(needs_review or 0)} of {completed}, seconds={elapsed:.2f}")


if __name__ == "__main__":
    main()
