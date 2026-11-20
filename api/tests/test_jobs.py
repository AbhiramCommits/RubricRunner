from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.grading.providers import MockProvider
from app.jobs.queue import configure_provider_factory
from app.models import FeedbackVersion, GradingRun

TERMINAL = {"succeeded", "partial", "failed"}


class FailingProvider(MockProvider):
    """Fails deterministically on two specific seeded submissions."""

    def complete(self, system: str, user: str) -> str:
        if "Basketball is the best sport" in user or "Video games are the best" in user:
            raise RuntimeError("injected provider failure")
        return super().complete(system, user)


def wait_for_run(client: TestClient, run_id: int, timeout: float = 60.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/grading-runs/{run_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in TERMINAL:
            return body
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not reach a terminal state in {timeout}s")


def test_full_class_run_succeeds_with_24_versions(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    response = client.post(
        f"/assignments/{seeded['assignment_id']}/grading-runs",
        json={"prompt_version": "v2_criterion_anchored"},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert response.json()["status"] == "queued"

    body = wait_for_run(client, run_id)
    assert body["status"] == "succeeded"
    assert body["total"] == 24
    assert body["completed"] == 24
    assert body["failed"] == 0
    assert len(body["outcomes"]) == 24
    assert all(outcome["status"] == "succeeded" for outcome in body["outcomes"])

    with session_factory() as session:
        count = session.scalar(
            select(func.count())
            .select_from(FeedbackVersion)
            .where(FeedbackVersion.grading_run_id == run_id)
        )
        assert count == 24
        run = session.get(GradingRun, run_id)
        assert run is not None
        assert run.finished_at is not None


def test_injected_failures_produce_partial_run(
    client: TestClient, session_factory: sessionmaker[Session], seeded: dict[str, int]
) -> None:
    configure_provider_factory(lambda: FailingProvider())
    response = client.post(
        f"/assignments/{seeded['assignment_id']}/grading-runs",
        json={"prompt_version": "v2_criterion_anchored"},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    body = wait_for_run(client, run_id)
    assert body["status"] == "partial"
    assert body["total"] == 24
    assert body["completed"] == 22
    assert body["failed"] == 2
    failed = [outcome for outcome in body["outcomes"] if outcome["status"] == "failed"]
    assert len(failed) == 2
    assert {outcome["student_external_id"] for outcome in failed} == {"S17", "S18"}
    assert all(outcome["attempts"] == 3 for outcome in failed)
    assert body["error_summary"]
    assert "injected provider failure" in str(body["error_summary"])

    with session_factory() as session:
        versions = session.scalar(
            select(func.count())
            .select_from(FeedbackVersion)
            .where(FeedbackVersion.grading_run_id == run_id)
        )
        assert versions == 22


def test_sse_endpoint_emits_terminal_event(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = client.post(
        f"/assignments/{seeded['assignment_id']}/grading-runs",
        json={"prompt_version": "v1_basic"},
    )
    run_id = response.json()["run_id"]
    wait_for_run(client, run_id)

    events: list[dict[str, object]] = []
    with client.stream("GET", f"/grading-runs/{run_id}/events") as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        for line in stream.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
                if events[-1]["status"] in TERMINAL:
                    break

    assert events
    terminal = events[-1]
    assert terminal["status"] == "succeeded"
    assert terminal["completed"] == 24
    assert terminal["failed"] == 0
    assert terminal["total"] == 24


def test_unknown_prompt_version_is_rejected(
    client: TestClient, seeded: dict[str, int]
) -> None:
    response = client.post(
        f"/assignments/{seeded['assignment_id']}/grading-runs",
        json={"prompt_version": "v99_nope"},
    )
    assert response.status_code == 422
    assert "Unknown prompt version" in response.json()["detail"]
