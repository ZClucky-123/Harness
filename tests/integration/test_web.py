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
    assert "GUARDED_HARNESS_BASE_URL" in response.text
    assert "https://njusehub.info/v1" in response.text
    assert "deepseek-v4-flash" in response.text


def test_starting_task_redirects_to_session_trace(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3"))

    response = client.post("/sessions", data={"task": "inspect the repository"}, follow_redirects=True)

    assert response.status_code == 200
    assert "inspect the repository" in response.text
    assert "session_started" in response.text
    assert "finished" in response.text


def test_session_page_preserves_chinese_text_in_task_and_trace(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("回复1+1+?", tmp_path)
    store.append_audit(session.id, "finished", {"message": "答案是2"})
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get(f"/sessions/{session.id}")

    assert response.status_code == 200
    assert "回复1+1+?" in response.text
    assert "答案是2" in response.text
    assert "\\u56de" not in response.text
    assert "\\u7b54" not in response.text


def test_approvals_page_preserves_chinese_text_in_reason_and_action(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("配置中文文件", tmp_path)
    store.create_approval(
        session.id,
        '{"type":"write_file","path":"notes.txt","content":"中文内容"}',
        "需要人工审批",
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "需要人工审批" in response.text
    assert "中文内容" in response.text
    assert "\\u4e2d" not in response.text
    assert "\\u9700" not in response.text


def test_web_live_mode_requires_api_key_when_keyring_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
        },
    )

    assert response.status_code == 400
    assert "API key is required" in response.text


def test_web_live_mode_uses_submitted_provider_config_without_persisting_key(tmp_path: Path, monkeypatch):
    captured = {}

    class FakeProvider:
        def __init__(self, base_url: str, model: str, api_key: str, timeout: float):
            captured.update({"base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout})

        def complete(self, context):
            return '{"type":"finish","message":"2"}'

    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", FakeProvider)
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
            "api_key": "njusehub-secret",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "finished" in response.text
    assert "2" in response.text
    assert captured == {
        "base_url": "https://njusehub.info/v1",
        "model": "deepseek-v4-flash",
        "api_key": "njusehub-secret",
        "timeout": 30.0,
    }
    assert "njusehub-secret" not in response.text
    assert "njusehub-secret" not in (tmp_path / "state.sqlite3").read_bytes().decode("utf-8", errors="ignore")


def test_web_live_mode_can_save_submitted_key_to_keyring(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials(None)
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", _FinishingProvider)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
            "api_key": "stored-secret",
            "save_api_key": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert credentials.key == "stored-secret"


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


def test_web_can_mark_executing_approval_failed(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    store.begin_approval_resolution(waiting.pending_approval_id, approved=True)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(
        f"/approvals/{waiting.pending_approval_id}/mark-failed",
        data={"reason": "crashed worker"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert store.get_approval(waiting.pending_approval_id).status == "failed"
    assert "approval_manually_failed" in response.text


class _FakeCredentials:
    def __init__(self, key: str | None):
        self.key = key

    def get_key(self) -> str | None:
        return self.key

    def set_key(self, key: str) -> None:
        self.key = key


class _FinishingProvider:
    def __init__(self, *args, **kwargs):
        pass

    def complete(self, context):
        return '{"type":"finish","message":"done"}'
