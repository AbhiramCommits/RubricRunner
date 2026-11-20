"""Executes one grading run, isolating submission failures from the run."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from app.grading.grader import grade_submission
from app.grading.providers import LLMProvider
from app.models import (
    Assignment,
    FeedbackVersion,
    GradingRun,
    GradingRunItem,
    RunStatus,
    Submission,
)

logger = logging.getLogger(__name__)

MAX_SUBMISSION_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.25


def _now() -> datetime:
    return datetime.now(UTC)


def _refresh_counts(session: Session, run: GradingRun) -> None:
    items = session.scalars(
        select(GradingRunItem).where(GradingRunItem.grading_run_id == run.id)
    ).all()
    run.completed = sum(1 for item in items if item.status == "succeeded")
    run.failed = sum(1 for item in items if item.status == "failed")


def _reconcile_items(session: Session, run: GradingRun) -> dict[int, int]:
    """Rebuild success items from versions already produced by this run."""
    versions = session.scalars(
        select(FeedbackVersion).where(FeedbackVersion.grading_run_id == run.id)
    ).all()
    done: dict[int, int] = {version.submission_id: version.id for version in versions}
    session.execute(delete(GradingRunItem).where(GradingRunItem.grading_run_id == run.id))
    for submission_id, version_id in done.items():
        session.add(
            GradingRunItem(
                grading_run_id=run.id,
                submission_id=submission_id,
                status="succeeded",
                attempts=1,
                feedback_version_id=version_id,
            )
        )
    session.flush()
    return done


def _record_outcome(
    session: Session,
    run_id: int,
    submission_id: int,
    status: str,
    attempts: int,
    error: str | None = None,
    feedback_version_id: int | None = None,
) -> None:
    item = session.scalars(
        select(GradingRunItem).where(
            GradingRunItem.grading_run_id == run_id,
            GradingRunItem.submission_id == submission_id,
        )
    ).first()
    if item is None:
        item = GradingRunItem(grading_run_id=run_id, submission_id=submission_id)
        session.add(item)
    item.status = status
    item.attempts = attempts
    item.error = error
    item.feedback_version_id = feedback_version_id


def execute_run(
    run_id: int,
    session_factory: sessionmaker[Session],
    provider_factory: Callable[[], LLMProvider],
) -> None:
    with session_factory() as session:
        run = session.get(GradingRun, run_id)
        if run is None:
            logger.error("run %s disappeared", run_id)
            return
        if run.status not in (RunStatus.queued.value, RunStatus.running.value):
            return
        assignment = session.get(Assignment, run.assignment_id)
        if assignment is None:
            run.status = RunStatus.failed.value
            run.finished_at = _now()
            run.error_summary = "Assignment not found"
            session.commit()
            return

        prompt_version = run.prompt_version
        submissions = list(
            session.scalars(
                select(Submission)
                .where(Submission.assignment_id == run.assignment_id)
                .options(selectinload(Submission.student))
                .order_by(Submission.id)
            ).all()
        )
        external = {
            submission.id: submission.student.external_id for submission in submissions
        }
        names = {submission.id: submission.student.name for submission in submissions}

        done = _reconcile_items(session, run)
        run.status = RunStatus.running.value
        run.started_at = run.started_at or _now()
        run.finished_at = None
        run.total = len(submissions)
        run.error_summary = None
        _refresh_counts(session, run)
        session.commit()

        pending = [submission.id for submission in submissions if submission.id not in done]

    for submission_id in pending:
        attempts = 0
        last_error: str | None = None
        version_id: int | None = None
        while attempts < MAX_SUBMISSION_ATTEMPTS:
            attempts += 1
            try:
                with session_factory() as session:
                    submission = session.get(Submission, submission_id)
                    if submission is None:
                        raise LookupError(f"submission {submission_id} not found")
                    result = grade_submission(
                        session=session,
                        submission=submission,
                        assignment=submission.assignment,
                        prompt_version=prompt_version,
                        provider=provider_factory(),
                        grading_run_id=run_id,
                    )
                    version_id = result.id
                break
            except Exception as exc:  # noqa: BLE001 - one bad submission must not kill the run
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "submission %s attempt %d/%d failed: %s",
                    submission_id,
                    attempts,
                    MAX_SUBMISSION_ATTEMPTS,
                    last_error,
                )
                if attempts < MAX_SUBMISSION_ATTEMPTS:
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)))

        with session_factory() as session:
            run = session.get(GradingRun, run_id)
            if run is None:
                return
            if version_id is not None:
                _record_outcome(
                    session,
                    run_id,
                    submission_id,
                    status="succeeded",
                    attempts=attempts,
                    feedback_version_id=version_id,
                )
            else:
                _record_outcome(
                    session,
                    run_id,
                    submission_id,
                    status="failed",
                    attempts=attempts,
                    error=last_error or "unknown error",
                )
            _refresh_counts(session, run)
            session.commit()

    with session_factory() as session:
        run = session.get(GradingRun, run_id)
        if run is None:
            return
        _refresh_counts(session, run)
        failed_items = session.scalars(
            select(GradingRunItem).where(
                GradingRunItem.grading_run_id == run_id, GradingRunItem.status == "failed"
            )
        ).all()
        if run.failed == 0:
            run.status = RunStatus.succeeded.value
        elif run.failed >= run.total:
            run.status = RunStatus.failed.value
        else:
            run.status = RunStatus.partial.value
        run.finished_at = _now()
        if failed_items:
            parts = [
                f"{external.get(item.submission_id, item.submission_id)} "
                f"({names.get(item.submission_id, 'unknown')}): {item.error}"
                for item in failed_items[:5]
            ]
            run.error_summary = "; ".join(parts)
        else:
            run.error_summary = None
        session.commit()
        logger.info(
            "run %s finished: %s (%d/%d, %d failed)",
            run_id,
            run.status,
            run.completed,
            run.total,
            run.failed,
        )
