from pathlib import Path

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
