from datetime import datetime
from pathlib import Path
import json
import sqlite3

import pytest

from guarded_harness.core.sessions import SessionStatus
from guarded_harness.governance.approvals import ApprovalRequest
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


def test_redacts_authorization_assignment_without_leaving_bearer_value(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("audit", tmp_path)

    store.append_audit(session.id, "request", {"detail": "Authorization: Bearer short-token"})

    assert store.list_audit(session.id)[0].payload == {"detail": "Authorization: [REDACTED]"}


def test_cannot_resolve_an_approval_twice(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("publish", tmp_path)
    approval = store.create_approval(session.id, '{"type":"run_shell"}', "approval required")

    store.resolve_approval(approval.id, approved=True)

    with pytest.raises(ValueError, match="already resolved"):
        store.resolve_approval(approval.id, approved=False)


@pytest.mark.parametrize(
    "secret",
    [
        "DATABASE_URL=postgres://alice:shortpw@db/prod",
        "password=hunter2",
        "sk-live-secret",
        "Authorization: Bearer short-token",
        "-----BEGIN PRIVATE KEY-----",
        "DATABASE_URL=sqlite:///local.db",
    ],
)
def test_approval_rejects_secrets_without_persisting_them(tmp_path: Path, secret: str):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    action = json.dumps({"type": "write_file", "path": ".env", "content": secret})

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.create_approval(session.id, action, "approval required")

    assert secret not in store.db_path.read_bytes().decode("utf-8", errors="ignore")
    with sqlite3.connect(store.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_abcdefghijklmnopqrstuvwxyz1234567890",
        "github_pat_11AA00_exampleexampleexampleexample",
        "gho_abcdefghijklmnopqrstuvwxyz1234567890",
        "ghu_abcdefghijklmnopqrstuvwxyz1234567890",
        "ghs_abcdefghijklmnopqrstuvwxyz1234567890",
        "ghr_abcdefghijklmnopqrstuvwxyz1234567890",
        "AKIAIOSFODNN7EXAMPLE",
        "ASIAIOSFODNN7EXAMPLE",
        "xoxb-1234567890-abcdefghijklmnop",
        "xoxp-1234567890-abcdefghijklmnop",
        "AIzaSyD-exampleexampleexampleexample1234",
    ],
)
@pytest.mark.parametrize("atomic", [False, True])
def test_approval_rejects_provider_tokens_in_neutral_content_without_persisting(
    tmp_path: Path,
    secret: str,
    atomic: bool,
):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    action = json.dumps({"type": "write_file", "path": "notes.txt", "content": f"value {secret}"})

    with pytest.raises(ValueError, match="keyring/secret reference"):
        if atomic:
            store.create_approval_and_pause_session(session, action, "approval required")
        else:
            store.create_approval(session.id, action, "approval required")

    assert store.list_pending_approvals() == []
    assert secret not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


def test_approval_rejects_structured_secret_field_name(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    action = json.dumps({"type": "run_shell", "command": "tool", "authorization": "short"})

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.create_approval(session.id, action, "approval required")

    assert "short" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


@pytest.mark.parametrize("atomic", [False, True])
def test_approval_rejects_secret_reason_without_persisting_it(tmp_path: Path, atomic: bool):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    secret_reason = "operator pasted Authorization: Bearer reason-token"

    with pytest.raises(ValueError, match="keyring/secret reference"):
        if atomic:
            store.create_approval_and_pause_session(
                session,
                '{"type":"write_file","path":".env","content":"MODE=prod"}',
                secret_reason,
            )
        else:
            store.create_approval(
                session.id,
                '{"type":"write_file","path":".env","content":"MODE=prod"}',
                secret_reason,
            )

    assert store.list_pending_approvals() == []
    assert "reason-token" not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


def test_legacy_approval_reason_is_redacted_for_display():
    approval = ApprovalRequest(
        "approval-id",
        "session-id",
        '{"type":"run_shell"}',
        "operator pasted Authorization: Bearer reason-token",
        "pending",
        created_at=datetime.now(),
    )

    assert approval.redacted_reason == "operator pasted Authorization: [REDACTED]"


def test_create_session_rejects_secret_task_without_persisting_it(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    secret = "api_key=sk-task-secret"

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.create_session(f"debug with {secret}", tmp_path)

    assert secret not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


@pytest.mark.parametrize("secret", ["ghp_abcdefghijklmnopqrstuvwxyz1234567890", "AKIAIOSFODNN7EXAMPLE"])
def test_create_session_rejects_provider_token_in_neutral_task(tmp_path: Path, secret: str):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.create_session(f"review this value: {secret}", tmp_path)

    assert secret not in store.db_path.read_bytes().decode("utf-8", errors="ignore")


def test_audit_read_redacts_legacy_url_credentials_and_private_key_block(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("audit", tmp_path)
    private_key = "-----BEGIN PRIVATE KEY-----\nprivate-key-body\n-----END PRIVATE KEY-----"
    with sqlite3.connect(store.db_path) as db:
        db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            (
                "legacy-event",
                session.id,
                "legacy",
                json.dumps({"url": "postgres://alice:shortpw@db/prod", "pem": private_key}),
                "2026-07-11T00:00:00+00:00",
            ),
        )

    payload = store.list_audit(session.id)[0].payload

    assert payload == {"url": "postgres://[REDACTED]@db/prod", "pem": "[REDACTED]"}


@pytest.mark.parametrize(
    ("kind", "content", "tags"),
    [
        ("decision", "Bearer memory-token", ["policy"]),
        ("api_key=kind-secret", "ordinary", ["policy"]),
        ("decision", "ordinary", ["authorization=secret"]),
    ],
)
def test_add_memory_rejects_secrets_in_all_persisted_fields(tmp_path: Path, kind: str, content: str, tags: list[str]):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.add_memory(kind, content, tags)

    with sqlite3.connect(store.db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0] == 0


@pytest.mark.parametrize("secret", ["ghp_abcdefghijklmnopqrstuvwxyz1234567890", "AKIAIOSFODNN7EXAMPLE"])
def test_add_memory_rejects_provider_token_in_neutral_content(tmp_path: Path, secret: str):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)

    with pytest.raises(ValueError, match="keyring/secret reference"):
        store.add_memory("note", f"value {secret}", ["reference"])

    assert store.list_memory(limit=5) == []


def test_create_approval_and_pause_session_is_atomic(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)

    approval = store.create_approval_and_pause_session(
        session,
        '{"type":"write_file","path":".env","content":"MODE=prod"}',
        "approval required",
    )

    persisted = store.get_session(session.id)
    assert persisted.status is SessionStatus.WAITING_APPROVAL
    assert persisted.pending_approval_id == approval.id
    assert store.list_pending_approvals() == [approval]


def test_create_approval_and_pause_session_rolls_back_if_session_update_fails(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    session.id = "missing-session"

    with pytest.raises(KeyError):
        store.create_approval_and_pause_session(
            session,
            '{"type":"write_file","path":".env","content":"MODE=prod"}',
            "approval required",
        )

    assert store.list_pending_approvals() == []


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


def test_executing_approval_can_be_manually_marked_failed_with_audit(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    approval = store.create_approval(session.id, '{"type":"write_file","path":".env","content":"ok"}', "approval")
    session.status = SessionStatus.WAITING_APPROVAL
    session.pending_approval_id = approval.id
    store.update_session(session)
    store.begin_approval_resolution(approval.id, approved=True)

    failed = store.mark_approval_failed(approval.id, "operator recovered crashed execution")

    assert failed.status == "failed"
    assert store.get_session(session.id).status is SessionStatus.FAILED
    event = store.list_audit(session.id)[-1]
    assert event.event_type == "approval_manually_failed"
    assert event.payload == {
        "approval_id": approval.id,
        "reason": "operator recovered crashed execution",
    }


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
