from pathlib import Path
import subprocess

import guarded_harness.tools.tests as test_tools
from guarded_harness.core.actions import Action, ActionType
from guarded_harness.core.observations import FeedbackKind
from guarded_harness.tools.dispatcher import ToolDispatcher


def test_write_and_read_file(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    write_obs = dispatcher.dispatch(Action(ActionType.WRITE_FILE, {"path": "hello.txt", "content": "hi"}))
    read_obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "hello.txt"}))

    assert write_obs.success is True
    assert read_obs.stdout == "hi"


def test_run_shell_success(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "python -c \"print('ok')\""}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert "ok" in obs.stdout


def test_run_shell_command_error(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "git status --bad-option"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.COMMAND_ERROR


def test_run_tests_uses_configured_command(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('tests ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is True
    assert obs.stdout.strip() == "tests ok"


def test_file_tool_errors_are_observations(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "../outside.txt"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.POLICY_DENIED


def test_dispatcher_denies_shell_path_outside_workspace_without_executing(tmp_path: Path):
    marker = tmp_path.parent / "dispatcher-should-not-execute.txt"
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": f"echo executed > ../{marker.name}"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.POLICY_DENIED
    assert "outside workspace" in obs.message
    assert not marker.exists()


def test_dispatcher_requires_approval_without_executing_shell(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    def fail_if_executed(*args, **kwargs):
        raise AssertionError("shell command must not execute")

    monkeypatch.setattr("guarded_harness.tools.dispatcher.run_shell", fail_if_executed)

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "git push origin main"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.APPROVAL_DENIED
    assert "approval" in obs.message


def test_run_tests_rejects_empty_configured_command_without_running(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=[])
    calls = []

    def record_execution(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(test_tools.subprocess, "run", record_execution)

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.COMMAND_ERROR
    assert "test command" in obs.message
    assert calls == []


def test_run_tests_rejects_malformed_configured_command_without_running(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", 42])
    calls = []

    def record_execution(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr(test_tools.subprocess, "run", record_execution)

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.COMMAND_ERROR
    assert "test command" in obs.message
    assert calls == []


def test_run_tests_uses_workspace_as_cwd(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    observed_cwds = []

    def successful_run(*args, **kwargs):
        observed_cwds.append(kwargs["cwd"])
        return subprocess.CompletedProcess(args[0], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(test_tools.subprocess, "run", successful_run)

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is True
    assert observed_cwds == [tmp_path.resolve()]


def test_run_tests_reports_timeout_as_observation(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output="partial", stderr="slow")

    monkeypatch.setattr(test_tools.subprocess, "run", timeout)

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.TEST_FAILURE
    assert obs.message == "test command timed out"
    assert obs.stdout == "partial"
    assert obs.stderr == "slow"
