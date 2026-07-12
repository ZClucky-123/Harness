from pathlib import Path
import subprocess

import pytest

import guarded_harness.tools.tests as test_tools
from guarded_harness.core.actions import Action, ActionType
from guarded_harness.core.observations import FeedbackKind
from guarded_harness.tools.dispatcher import ToolDispatcher
from guarded_harness.tools.shell import run_shell


def test_write_and_read_file(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    write_obs = dispatcher.dispatch(Action(ActionType.WRITE_FILE, {"path": "hello.txt", "content": "hi"}))
    read_obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "hello.txt"}))

    assert write_obs.success is True
    assert read_obs.stdout == "hi"


def test_write_file_reports_success_path_and_utf8_size(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.WRITE_FILE, {"path": "hello.txt", "content": "中文"}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert "wrote hello.txt" in obs.message
    assert "2 characters" in obs.message
    assert "6 UTF-8 bytes" in obs.message
    assert obs.metadata == {"path": "hello.txt", "characters": 2, "utf8_bytes": 6}


def test_read_file_reports_success_without_repeating_content_in_message(tmp_path: Path):
    (tmp_path / "hello.txt").write_text("中文", encoding="utf-8")
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "hello.txt"}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert obs.stdout == "中文"
    assert "read hello.txt" in obs.message
    assert "2 characters" in obs.message
    assert "6 UTF-8 bytes" in obs.message
    assert "中文" not in obs.message
    assert obs.metadata == {"path": "hello.txt", "characters": 2, "utf8_bytes": 6}


def test_read_file_reports_empty_file(tmp_path: Path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "empty.txt"}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert obs.stdout == ""
    assert obs.message == "read empty.txt: file is empty (0 characters, 0 UTF-8 bytes)"
    assert obs.metadata == {"path": "empty.txt", "characters": 0, "utf8_bytes": 0}


def test_run_shell_success(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "python -m compileall -q ."}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert obs.stderr == ""


def test_run_shell_command_error(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "git status --bad-option"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.COMMAND_ERROR


def test_run_shell_executes_structured_argv_without_shell(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    calls = []

    def record_execution(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("guarded_harness.tools.shell.subprocess.run", record_execution)

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "git status --bad-option"}))

    assert obs.success is True
    assert calls[0][0][0][:2] == ["git", "-c"]
    assert calls[0][0][0][-2:] == ["status", "--bad-option"]
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == tmp_path.resolve()


@pytest.mark.parametrize(
    "command",
    [
        "echo $(touch marker)",
        "echo `touch marker`",
        "echo safe\ntouch marker",
        "echo safe > marker",
        "echo safe | cat",
    ],
)
def test_run_shell_never_executes_shell_control_syntax(tmp_path: Path, monkeypatch, command: str):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    calls = []
    monkeypatch.setattr(
        "guarded_harness.tools.shell.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    obs = dispatcher.dispatch_approved(Action(ActionType.RUN_SHELL, {"command": command}))

    assert obs.success is False
    assert calls == []
    assert not (tmp_path / "marker").exists()


def test_approved_python_inline_code_is_denied_without_execution(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["pytest", "-q"])
    calls = []
    monkeypatch.setattr(
        "guarded_harness.tools.dispatcher.run_shell",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    action = Action(
        ActionType.RUN_SHELL,
        {
            "command": (
                'python -c "from pathlib import Path; '
                "Path.home().joinpath('x').write_text('bad')\""
            )
        },
    )

    observation = dispatcher.dispatch_approved(action)

    assert observation.success is False
    assert observation.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


@pytest.mark.parametrize("command", ["python workspace_script.py", "npm test", "make", "workspace_script.py"])
def test_approved_arbitrary_code_entrypoints_are_denied_without_execution(
    tmp_path: Path,
    monkeypatch,
    command: str,
):
    dispatcher = ToolDispatcher(tmp_path, test_command=["pytest", "-q"])
    calls = []
    monkeypatch.setattr(
        "guarded_harness.tools.dispatcher.run_shell",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    observation = dispatcher.dispatch_approved(Action(ActionType.RUN_SHELL, {"command": command}))

    assert observation.success is False
    assert observation.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


def test_run_shell_denies_symlink_path_escape_without_execution(tmp_path: Path, monkeypatch):
    outside = tmp_path.parent / "outside-dispatch-target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    calls = []
    monkeypatch.setattr(
        "guarded_harness.tools.shell.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(
        Action(ActionType.RUN_SHELL, {"command": "cat linked-outside/secret.txt"})
    )

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


def test_run_tests_uses_configured_command(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('tests ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is True
    assert obs.stdout.strip() == "tests ok"
    assert obs.message == "test command passed with exit code 0"


def test_run_tests_reports_failure_exit_code(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "import sys; print('bad'); sys.exit(3)"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_TESTS))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.TEST_FAILURE
    assert obs.stdout.strip() == "bad"
    assert obs.message == "test command failed with exit code 3"


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

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "rm src/app.py"}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.APPROVAL_DENIED
    assert "approval" in obs.message


def test_dispatcher_denies_external_helper_options_without_execution(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    calls = []

    monkeypatch.setattr(
        "guarded_harness.tools.shell.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    for command in (
        "rg --pre=./workspace-script pattern",
        "git diff --ext-diff",
        "git diff --textconv",
        "git diff --config",
    ):
        obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": command}))

        assert obs.success is False
        assert obs.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


@pytest.mark.parametrize(
    "command",
    [
        "rg --pre=./workspace-script pattern",
        "git diff --ext-diff",
        "git diff --textconv",
        "git --pager=./workspace-script diff",
        "git -c core.fsmonitor=./workspace-script status",
    ],
)
def test_run_shell_directly_rejects_external_helper_options(tmp_path: Path, monkeypatch, command: str):
    calls = []
    monkeypatch.setattr(
        "guarded_harness.tools.shell.subprocess.run",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    obs = run_shell(tmp_path, command)

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


def test_run_shell_sanitizes_safe_helper_configuration(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    calls = []
    monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(tmp_path / "ripgreprc"))
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(tmp_path / "helper"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(tmp_path / "helper"))

    def record_execution(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("guarded_harness.tools.shell.subprocess.run", record_execution)

    assert dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "rg pattern"})).success is True
    assert dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "git diff"})).success is True

    rg_argv, rg_kwargs = calls[0][0][0], calls[0][1]
    git_argv, git_kwargs = calls[1][0][0], calls[1][1]
    assert rg_argv == ["rg", "--no-config", "pattern"]
    assert "RIPGREP_CONFIG_PATH" not in rg_kwargs["env"]
    assert git_argv == [
        "git",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.pager=cat",
        "-c",
        "diff.external=",
        "-c",
        "pager.diff=false",
        "-c",
        "pager.show=false",
        "diff",
        "--no-ext-diff",
        "--no-textconv",
    ]
    assert git_kwargs["env"]["GIT_EXTERNAL_DIFF"] == ""
    assert git_kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert "GIT_CONFIG_COUNT" not in git_kwargs["env"]
    assert "GIT_CONFIG_KEY_0" not in git_kwargs["env"]
    assert "GIT_CONFIG_VALUE_0" not in git_kwargs["env"]
    assert git_kwargs["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert git_kwargs["env"]["GIT_PAGER"] == "cat"


def test_dispatcher_denies_secret_payloads_before_tools(tmp_path: Path, monkeypatch):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])
    calls = []

    monkeypatch.setattr(
        "guarded_harness.tools.dispatcher.write_file",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    obs = dispatcher.dispatch(
        Action(ActionType.WRITE_FILE, {"path": "out.txt", "content": "xoxb-123456789012-secret"})
    )

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.POLICY_DENIED
    assert calls == []


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
