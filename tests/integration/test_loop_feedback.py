from pathlib import Path

from guarded_harness.core.loop import AgentLoop
from guarded_harness.core.sessions import SessionStatus
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def test_feedback_changes_next_mock_action(tmp_path: Path):
    llm = MockLLM([
        '{"type":"run_shell","command":"git status --bad-option"}',
        '{"type":"finish","message":"changed action after command_error"}',
    ])
    loop = AgentLoop.for_workspace(
        tmp_path,
        llm,
        SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path),
        max_steps=3,
    )

    session = loop.run("recover from failure")
    events = loop.store.list_audit(session.id)

    assert session.status == SessionStatus.FINISHED
    assert any("command_error" in str(event.payload) for event in events)
    assert llm.contexts[1]["observations"][0]["feedback_kind"] == "command_error"


def test_write_file_success_message_reaches_next_llm_context(tmp_path: Path):
    llm = MockLLM([
        '{"type":"write_file","path":"notes.txt","content":"中文"}',
        '{"type":"finish","message":"write observed"}',
    ])
    loop = AgentLoop.for_workspace(
        tmp_path,
        llm,
        SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path),
        max_steps=3,
    )

    session = loop.run("write a note once")
    observation = llm.contexts[1]["observations"][0]

    assert session.status == SessionStatus.FINISHED
    assert observation["feedback_kind"] == "tool_success"
    assert "wrote notes.txt" in observation["message"]
    assert "2 characters" in observation["message"]
    assert "6 UTF-8 bytes" in observation["message"]
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "中文"
