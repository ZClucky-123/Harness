from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore
from guarded_harness.web.app import create_app


def test_index_loads():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Guarded Harness" in response.text


def test_starting_task_redirects_to_session_trace(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3"))

    response = client.post("/sessions", data={"task": "inspect the repository"}, follow_redirects=True)

    assert response.status_code == 200
    assert "inspect the repository" in response.text
    assert "session_started" in response.text
    assert "finished" in response.text


def test_approvals_page_loads():
    client = TestClient(create_app())

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "Approvals" in response.text


def test_denying_approval_resumes_session(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    approval_id = waiting.pending_approval_id
    client = TestClient(create_app(store.db_path))

    response = client.post(f"/approvals/{approval_id}/deny", follow_redirects=True)

    assert response.status_code == 200
    assert "approval_denied" in response.text
    assert store.get_approval(approval_id).status == "denied"


def test_approvals_page_redacts_secrets_from_pending_action(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    with sqlite3.connect(store.db_path) as db:
        db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-secret-approval",
                session.id,
                '{"type":"write_file","path":".env","content":"sk-web-secret Bearer web-bearer password=hunter2"}',
                "environment write requires approval",
                "pending",
                "2026-07-11T00:00:00+00:00",
                None,
            ),
        )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "[REDACTED]" in response.text
    assert "sk-web-secret" not in response.text
    assert "web-bearer" not in response.text
    assert "hunter2" not in response.text


def test_session_page_redacts_legacy_secret_task_and_trace(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("safe task", tmp_path)
    with sqlite3.connect(store.db_path) as db:
        db.execute("UPDATE sessions SET task = ? WHERE id = ?", ("password=legacy-task-secret", session.id))
        db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            (
                "legacy-secret-event",
                session.id,
                "legacy_event",
                '{"detail":"postgres://alice:shortpw@db/prod"}',
                "2026-07-11T00:00:00+00:00",
            ),
        )

    response = TestClient(create_app(store.db_path, workspace_root=tmp_path)).get(f"/sessions/{session.id}")

    assert response.status_code == 200
    assert "[REDACTED]" in response.text
    assert "legacy-task-secret" not in response.text
    assert "shortpw" not in response.text


def test_approving_action_executes_it_and_ends_recovery_round(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(f"/approvals/{waiting.pending_approval_id}/approve", follow_redirects=True)

    assert response.status_code == 200
    assert "approval_recovery_ended" in response.text
    assert (tmp_path / ".env").read_text() == "MODE=prod"
