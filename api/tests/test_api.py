from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.models import FeedbackVersion
from tests.conftest import add_ai_version


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


def test_create_and_get_assignment(client: TestClient) -> None:
    payload = {
        "course_name": "English 11",
        "title": "Ban cars?",
        "prompt_text": "Should cities ban cars downtown?",
        "rubric": [
            {"name": "Thesis", "description": "Clear thesis", "max_points": 5, "order_index": 0},
            {"name": "Evidence", "description": "Uses evidence", "max_points": 10, "order_index": 1},
        ],
    }
    created = client.post("/assignments", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["course_name"] == "English 11"
    assert body["max_points"] == 15
    assert [c["name"] for c in body["criteria"]] == ["Thesis", "Evidence"]

    fetched = client.get(f"/assignments/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Ban cars?"

    listed = client.get("/assignments")
    assert listed.status_code == 200
    assert listed.json()[0]["submission_count"] == 0


def test_roster_statuses(
    client: TestClient, session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    submission_ids = demo["submission_ids"]
    assert isinstance(submission_ids, list)
    with session_factory() as session:
        # S1: plain AI grade -> ai_graded
        add_ai_version(session, submission_ids[0], [4, 7, 4, 4], [0.9, 0.9, 0.9, 0.9])
        # S2: low confidence AI grade -> needs_review
        add_ai_version(session, submission_ids[1], [2, 3, 2, 3], [0.9, 0.4, 0.8, 0.9], needs_review=True)
        # S3: AI grade then teacher edit -> teacher_edited
        add_ai_version(session, submission_ids[2], [3, 5, 3, 3], [0.8, 0.8, 0.8, 0.8])
        # S4: AI grade published -> published
        published_version = add_ai_version(session, submission_ids[3], [5, 8, 4, 4], [0.95] * 4)

    # Teacher edit for S3
    detail = client.get(f"/submissions/{submission_ids[2]}").json()
    parent_id = detail["versions"][-1]["id"]
    criteria = detail["rubric"]
    edit = client.post(
        f"/submissions/{submission_ids[2]}/feedback-versions",
        json={
            "parent_version_id": parent_id,
            "summary_comment": "Raised evidence after re-read.",
            "criteria": [
                {"criterion_id": c["id"], "points": 4, "justification": "Teacher note"}
                for c in criteria
            ],
        },
    )
    assert edit.status_code == 201

    # Publish S4's AI version
    publish = client.post(
        f"/submissions/{submission_ids[3]}/publish",
        json={"feedback_version_id": published_version.id, "published_by": "prof@example.edu"},
    )
    assert publish.status_code == 200

    roster = client.get(f"/assignments/{demo['assignment_id']}/roster")
    assert roster.status_code == 200
    entries = {entry["external_id"]: entry for entry in roster.json()}
    assert entries["T01"]["status"] == "ai_graded"
    assert entries["T02"]["status"] == "needs_review"
    assert entries["T03"]["status"] == "teacher_edited"
    assert entries["T04"]["status"] == "published"
    assert entries["T01"]["ai_total"] == 19
    assert entries["T02"]["lowest_confidence"] == 0.4
    assert entries["T03"]["current_total"] == 16


def test_teacher_edit_creates_new_version_and_leaves_parent_untouched(
    client: TestClient, session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    submission_id = demo["submission_ids"][0]  # type: ignore[index]
    with session_factory() as session:
        parent = add_ai_version(session, submission_id, [4, 7, 4, 4], [0.9] * 4)
        parent_id = parent.id
        parent_total = parent.total_points
        parent_scores = [(score.id, score.points) for score in parent.scores]

    detail = client.get(f"/submissions/{submission_id}").json()
    criteria = detail["rubric"]
    response = client.post(
        f"/submissions/{submission_id}/feedback-versions",
        json={
            "parent_version_id": parent_id,
            "summary_comment": "Adjusted thesis and evidence.",
            "created_by": "teacher@example.edu",
            "criteria": [
                {"criterion_id": criteria[0]["id"], "points": 5, "justification": "Sharper thesis"},
                {"criterion_id": criteria[1]["id"], "points": 8, "justification": "More evidence"},
                {"criterion_id": criteria[2]["id"], "points": 4, "justification": "Fine"},
                {"criterion_id": criteria[3]["id"], "points": 4, "justification": "Fine"},
            ],
        },
    )
    assert response.status_code == 201
    new_version = response.json()
    assert new_version["source"] == "teacher"
    assert new_version["parent_version_id"] == parent_id
    assert new_version["total_points"] == 21
    assert new_version["needs_review"] is False
    assert new_version["id"] != parent_id

    with session_factory() as session:
        stored_parent = session.get(FeedbackVersion, parent_id)
        assert stored_parent is not None
        assert stored_parent.total_points == parent_total
        assert [(score.id, score.points) for score in stored_parent.scores] == parent_scores
        assert len(stored_parent.scores) == 4

    refreshed = client.get(f"/submissions/{submission_id}").json()
    assert [version["id"] for version in refreshed["versions"]] == [parent_id, new_version["id"]]


def test_publish_rejects_needs_review_version(
    client: TestClient, session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    submission_id = demo["submission_ids"][0]  # type: ignore[index]
    with session_factory() as session:
        version = add_ai_version(
            session, submission_id, [2, 3, 2, 3], [0.4, 0.4, 0.5, 0.5], needs_review=True
        )
        version_id = version.id

    response = client.post(
        f"/submissions/{submission_id}/publish",
        json={"feedback_version_id": version_id},
    )
    assert response.status_code == 409
    assert "needs_review" in response.json()["detail"]

    audit = client.get(f"/submissions/{submission_id}/audit-trail")
    assert audit.status_code == 404


def test_audit_trail_returns_full_chain(
    client: TestClient, session_factory: sessionmaker[Session], demo: dict[str, object]
) -> None:
    submission_id = demo["submission_ids"][0]  # type: ignore[index]
    with session_factory() as session:
        root = add_ai_version(session, submission_id, [4, 7, 4, 4], [0.9] * 4)
        root_id = root.id

    detail = client.get(f"/submissions/{submission_id}").json()
    criteria = detail["rubric"]

    parent_id = root_id
    version_ids = [root_id]
    for delta in (1, 2):
        response = client.post(
            f"/submissions/{submission_id}/feedback-versions",
            json={
                "parent_version_id": parent_id,
                "summary_comment": f"Edit {delta}",
                "criteria": [
                    {"criterion_id": c["id"], "points": 4, "justification": "Teacher"}
                    for c in criteria
                ],
            },
        )
        assert response.status_code == 201
        parent_id = response.json()["id"]
        version_ids.append(parent_id)

    publish = client.post(
        f"/submissions/{submission_id}/publish",
        json={"feedback_version_id": parent_id},
    )
    assert publish.status_code == 200

    trail = client.get(f"/submissions/{submission_id}/audit-trail")
    assert trail.status_code == 200
    body = trail.json()
    assert body["published"]["feedback_version_id"] == parent_id
    assert [version["id"] for version in body["chain"]] == version_ids
    assert body["chain"][0]["source"] == "ai"
    assert body["chain"][0]["prompt_version"] == "v2_criterion_anchored"
    assert body["chain"][0]["raw_model_output"] is not None
    assert body["chain"][-1]["source"] == "teacher"
    assert body["chain"][-1]["raw_model_output"] is None
