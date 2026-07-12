from pathlib import Path

import pytest

from guarded_harness.core.loop import AgentLoop
from guarded_harness.core.sessions import SessionStatus
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def _run_loop(tmp_path: Path, responses: list[str], max_steps: int = 2):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    loop = AgentLoop.for_workspace(tmp_path, MockLLM(responses), store, max_steps=max_steps)
    return loop.run("exercise terminal state"), store


def test_mock_llm_exhaustion_fails_and_audits_session(tmp_path: Path):
    session, store = _run_loop(tmp_path, [])

    persisted = store.get_session(session.id)
    events = store.list_audit(session.id)

    assert session.status is SessionStatus.FAILED
    assert persisted.status is SessionStatus.FAILED
    assert session.step_count == persisted.step_count == 0
    assert any(event.event_type == "provider_failure" for event in events)


def test_empty_llm_response_is_provider_failure_not_parser_error(tmp_path: Path):
    session, store = _run_loop(tmp_path, ["   "], max_steps=2)
    events = store.list_audit(session.id)

    assert session.status is SessionStatus.FAILED
    assert any(event.event_type == "provider_failure" for event in events)
    assert not any(event.event_type == "parser_error" for event in events)
    assert "empty" in str(events[-1].payload["message"])


@pytest.mark.parametrize(
    ("responses", "max_steps", "expected_status", "expected_steps", "has_pending_approval"),
    [
        (['{"type":"finish","message":"done"}'], 2, SessionStatus.FINISHED, 1, False),
        (['{"type":"run_shell","command":"rm src/app.py"}'], 2, SessionStatus.WAITING_APPROVAL, 1, True),
        (['not valid json'], 1, SessionStatus.MAX_STEPS, 1, False),
        ([], 2, SessionStatus.FAILED, 0, False),
    ],
    ids=["finished", "waiting_approval", "max_steps", "provider_failed"],
)
def test_terminal_session_state_is_persisted(
    tmp_path: Path,
    responses: list[str],
    max_steps: int,
    expected_status: SessionStatus,
    expected_steps: int,
    has_pending_approval: bool,
):
    session, store = _run_loop(tmp_path, responses, max_steps)

    persisted = store.get_session(session.id)

    assert persisted.status is expected_status
    assert persisted.step_count == expected_steps
    assert (persisted.pending_approval_id is not None) is has_pending_approval
    assert persisted.pending_approval_id == session.pending_approval_id


def test_secret_bearing_finish_action_is_rejected_before_audit(tmp_path: Path):
    session, store = _run_loop(
        tmp_path,
        ['{"type":"finish","message":"ghp_abcdefghijklmnopqrstuvwxyz123456"}'],
        max_steps=1,
    )
    events = store.list_audit(session.id)

    assert session.status is SessionStatus.MAX_STEPS
    assert any(event.event_type == "policy_denied" for event in events)
    assert all("ghp_" not in str(event.payload) for event in events)
