from pathlib import Path

from guarded_harness.core.loop import AgentLoop
from guarded_harness.core.sessions import SessionStatus
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def test_loop_denies_dangerous_action(tmp_path: Path):
    llm = MockLLM(['{"type":"run_shell","command":"rm -rf /"}', '{"type":"finish","message":"stopped"}'])
    loop = AgentLoop.for_workspace(
        tmp_path,
        llm,
        SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path),
        max_steps=2,
    )

    session = loop.run("try a dangerous command")
    events = loop.store.list_audit(session.id)

    assert session.status == SessionStatus.FINISHED
    assert any(event.event_type == "policy_denied" for event in events)
    assert llm.contexts[1]["observations"][0]["feedback_kind"] == "policy_denied"
