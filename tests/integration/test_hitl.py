import json
from pathlib import Path

import pytest

from guarded_harness.core.loop import AgentLoop
from guarded_harness.core.sessions import SessionStatus
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def make_loop(tmp_path: Path, responses: list[str], max_steps: int = 3) -> AgentLoop:
    return AgentLoop.for_workspace(
        tmp_path,
        MockLLM(responses),
        SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path),
        max_steps=max_steps,
    )


def test_approval_pauses_and_persists_pending_action(tmp_path: Path):
    loop = make_loop(tmp_path, ['{"type":"write_file","path":".env","content":"MODE=prod"}'])

    session = loop.run("configure production")
    approvals = loop.store.list_pending_approvals()
    persisted = loop.store.get_session(session.id)

    assert session.status == SessionStatus.WAITING_APPROVAL
    assert persisted.pending_approval_id == approvals[0].id
    assert len(approvals) == 1
    assert json.loads(approvals[0].action_json)["path"] == ".env"


def test_loop_uses_atomic_approval_pause_path(tmp_path: Path, monkeypatch):
    loop = make_loop(tmp_path, ['{"type":"write_file","path":".env","content":"MODE=prod"}'])

    monkeypatch.setattr(
        loop.store,
        "create_approval",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy approval path used")),
    )

    session = loop.run("configure production")
    approval = loop.store.list_pending_approvals()[0]
    persisted = loop.store.get_session(session.id)

    assert persisted.status is SessionStatus.WAITING_APPROVAL
    assert persisted.pending_approval_id == approval.id


def test_approved_pending_action_executes_and_persists_finished_session(tmp_path: Path):
    loop = make_loop(
        tmp_path,
        [
            '{"type":"write_file","path":".env","content":"MODE=prod"}',
            '{"type":"finish","message":"configured"}',
        ],
    )

    waiting = loop.run("configure production")
    approval = loop.store.list_pending_approvals()[0]
    session = loop.resume_after_approval(approval.id, approved=True)
    events = loop.store.list_audit(waiting.id)
    persisted = loop.store.get_session(waiting.id)

    assert session.status == SessionStatus.FINISHED
    assert persisted.status == SessionStatus.FINISHED
    assert persisted.pending_approval_id is None
    assert (tmp_path / ".env").read_text() == "MODE=prod"
    assert any(event.event_type == "approval_approved" for event in events)
    assert any(event.event_type == "resumed_tool_result" for event in events)
    assert loop.store.get_approval(approval.id).status == "executed"


def test_approved_pseudo_shell_rm_executes_and_persists_finished_session(tmp_path: Path):
    target = tmp_path / "delete-me.txt"
    target.write_text("remove", encoding="utf-8")
    loop = make_loop(
        tmp_path,
        [
            '{"type":"run_shell","command":"rm delete-me.txt"}',
            '{"type":"finish","message":"removed"}',
        ],
    )

    waiting = loop.run("delete generated file")
    approval = loop.store.list_pending_approvals()[0]
    session = loop.resume_after_approval(approval.id, approved=True)
    events = loop.store.list_audit(waiting.id)

    assert session.status == SessionStatus.FINISHED
    assert not target.exists()
    assert any(event.event_type == "approval_approved" for event in events)
    assert any(event.event_type == "resumed_tool_result" and event.payload["success"] for event in events)
    assert loop.store.get_approval(approval.id).status == "executed"


def test_denied_approval_feeds_back_and_finishes(tmp_path: Path):
    loop = make_loop(
        tmp_path,
        [
            '{"type":"write_file","path":".env","content":"MODE=prod"}',
            '{"type":"finish","message":"will not configure"}',
        ],
    )

    waiting = loop.run("configure production")
    approval = loop.store.list_pending_approvals()[0]
    session = loop.resume_after_approval(approval.id, approved=False)
    events = loop.store.list_audit(waiting.id)

    assert session.status == SessionStatus.FINISHED
    assert not (tmp_path / ".env").exists()
    assert any(event.event_type == "approval_denied" for event in events)
    assert any(event.payload.get("feedback_kind") == "approval_denied" for event in events)
    assert loop.llm.contexts[1]["observations"][0]["feedback_kind"] == "approval_denied"


def test_resolved_approval_cannot_resume_action_again(tmp_path: Path):
    loop = make_loop(
        tmp_path,
        [
            '{"type":"write_file","path":".env","content":"MODE=prod"}',
            '{"type":"finish","message":"configured"}',
        ],
    )

    loop.run("configure production")
    approval = loop.store.list_pending_approvals()[0]
    loop.resume_after_approval(approval.id, approved=True)

    with pytest.raises(ValueError, match="already resolved"):
        loop.resume_after_approval(approval.id, approved=True)


def test_cross_process_approval_recovery_executes_action_then_ends(tmp_path: Path):
    loop = make_loop(tmp_path, ['{"type":"write_file","path":".env","content":"MODE=prod"}'])
    waiting = loop.run("configure production")

    session = loop.resume_after_approval(
        waiting.pending_approval_id,
        approved=True,
        continue_after_resolution=False,
    )

    assert session.status == SessionStatus.FINISHED
    assert (tmp_path / ".env").read_text() == "MODE=prod"
    assert any(event.event_type == "approval_recovery_ended" for event in loop.store.list_audit(session.id))


def test_remember_action_persists_memory_and_audit(tmp_path: Path):
    loop = make_loop(
        tmp_path,
        [
            '{"type":"remember","kind":"decision","content":"Use pytest","tags":["testing","policy"]}',
            '{"type":"finish","message":"remembered"}',
        ],
    )

    session = loop.run("remember convention")

    memories = loop.store.list_memory(limit=5)
    assert session.status == SessionStatus.FINISHED
    assert memories[0].kind == "decision"
    assert memories[0].content == "Use pytest"
    assert memories[0].tags == ["testing", "policy"]
    assert any(event.event_type == "memory_added" for event in loop.store.list_audit(session.id))


def test_invalid_remember_action_becomes_feedback(tmp_path: Path):
    loop = make_loop(
        tmp_path,
        [
            '{"type":"remember","kind":"","content":"Use pytest","tags":"testing"}',
            '{"type":"finish","message":"corrected"}',
        ],
    )

    session = loop.run("remember convention")

    assert session.status == SessionStatus.FINISHED
    assert loop.store.list_memory(limit=5) == []
    assert loop.llm.contexts[1]["observations"][0]["feedback_kind"] == "command_error"
    assert "remember" in loop.llm.contexts[1]["observations"][0]["message"]
