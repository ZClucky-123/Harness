from pathlib import Path

import pytest

from guarded_harness.core.sessions import SessionStatus
from guarded_harness.memory.store import SQLiteStore


def test_create_session_and_audit_event(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("fix tests", tmp_path)

    store.append_audit(session.id, "session_created", {"task": "fix tests"})
    events = store.list_audit(session.id)

    assert session.task == "fix tests"
    assert session.workspace == tmp_path
    assert events[0].event_type == "session_created"
    assert events[0].payload["task"] == "fix tests"


def test_create_and_resolve_approval(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("publish", tmp_path)
    approval = store.create_approval(session.id, '{"type":"run_shell"}', "git push requires approval")

    assert store.list_pending_approvals() == [approval]

    resolved = store.resolve_approval(approval.id, approved=False)

    assert approval.status == "pending"
    assert resolved.status == "denied"
    assert store.list_pending_approvals() == []


def test_memory_round_trip(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    store.add_memory("decision", "Never edit .env without approval", ["policy"])

    entries = store.list_memory(limit=5)

    assert entries[0].content == "Never edit .env without approval"


def test_rejects_database_paths_with_traversal(tmp_path: Path):
    db_path = tmp_path / "state" / ".." / "state.sqlite3"

    with pytest.raises(ValueError, match="traversal"):
        SQLiteStore(db_path, workspace_root=tmp_path)


def test_rejects_absolute_database_path_without_workspace_root(tmp_path: Path):
    with pytest.raises(ValueError, match="workspace root"):
        SQLiteStore(tmp_path / "state.sqlite3")


def test_rejects_database_outside_workspace_root(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    db_path = tmp_path / "outside" / "state.sqlite3"

    with pytest.raises(ValueError, match="workspace root"):
        SQLiteStore(db_path, workspace_root=workspace_root)


def test_redacts_secrets_in_nested_audit_payloads(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("audit", tmp_path)

    store.append_audit(
        session.id,
        "request",
        {
            "apiToken": "top-secret",
            "nested": {"password": "also-secret", "safe": "visible"},
            "items": [{"authorization": "Bearer secret"}],
        },
    )

    payload = store.list_audit(session.id)[0].payload

    assert payload == {
        "apiToken": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "safe": "visible"},
        "items": [{"authorization": "[REDACTED]"}],
    }


def test_redacts_openai_style_secret_in_neutral_audit_field(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("audit", tmp_path)

    store.append_audit(session.id, "request", {"detail": "sk-live-secret"})

    assert store.list_audit(session.id)[0].payload == {"detail": "[REDACTED]"}


def test_redacts_bearer_token_in_neutral_audit_field(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("audit", tmp_path)

    store.append_audit(session.id, "request", {"detail": "Bearer secret-token"})

    assert store.list_audit(session.id)[0].payload == {"detail": "[REDACTED]"}


def test_cannot_resolve_an_approval_twice(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("publish", tmp_path)
    approval = store.create_approval(session.id, '{"type":"run_shell"}', "approval required")

    store.resolve_approval(approval.id, approved=True)

    with pytest.raises(ValueError, match="already resolved"):
        store.resolve_approval(approval.id, approved=False)


def test_approval_exposes_only_redacted_action_for_display(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    action = (
        '{"type":"write_file","path":".env","content":'
        '"API_KEY=sk-live-secret\\nAuthorization=Bearer bearer-secret\\npassword=hunter2"}'
    )

    approval = store.create_approval(session.id, action, "approval required")

    assert approval.action_json == action
    assert "[REDACTED]" in approval.redacted_action_json
    assert "sk-live-secret" not in approval.redacted_action_json
    assert "bearer-secret" not in approval.redacted_action_json
    assert "hunter2" not in approval.redacted_action_json


def test_begin_approval_resolution_updates_approval_and_session_atomically(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    approval = store.create_approval(session.id, '{"type":"write_file","path":".env","content":"ok"}', "approval")
    session.status = SessionStatus.WAITING_APPROVAL
    session.pending_approval_id = approval.id
    store.update_session(session)

    executing, resumed = store.begin_approval_resolution(approval.id, approved=True)

    assert executing.status == "executing"
    assert resumed.status is SessionStatus.RUNNING
    assert resumed.pending_approval_id is None


def test_finalize_approval_execution_records_outcome(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    approval = store.create_approval(session.id, '{"type":"write_file","path":".env","content":"ok"}', "approval")
    session.status = SessionStatus.WAITING_APPROVAL
    session.pending_approval_id = approval.id
    store.update_session(session)
    store.begin_approval_resolution(approval.id, approved=True)

    finalized = store.finalize_approval_execution(approval.id, succeeded=False)

    assert finalized.status == "failed"


def test_unfinished_approval_remains_visible_after_execution_starts(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    approval = store.create_approval(session.id, '{"type":"write_file","path":".env","content":"ok"}', "approval")
    session.status = SessionStatus.WAITING_APPROVAL
    session.pending_approval_id = approval.id
    store.update_session(session)
    store.begin_approval_resolution(approval.id, approved=True)

    unfinished = store.list_unfinished_approvals()

    assert [(item.id, item.status) for item in unfinished] == [(approval.id, "executing")]
