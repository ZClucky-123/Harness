import os
import subprocess
from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation
from guarded_harness.governance.shell_command import argv_paths_within_workspace, parse_shell_argv


def run_shell(workspace_root: Path, command: object) -> Observation:
    if not isinstance(command, str) or not command:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="shell command is required")
    try:
        argv = parse_shell_argv(command)
    except ValueError as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    if not argv_paths_within_workspace(argv, workspace_root):
        return Observation(False, FeedbackKind.POLICY_DENIED, message="shell path is outside workspace")
    argv = _safe_execution_argv(argv)
    env = _safe_execution_env(argv)
    try:
        result = subprocess.run(
            argv,
            cwd=workspace_root,
            shell=False,
            text=True,
            capture_output=True,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return Observation(
            False,
            FeedbackKind.COMMAND_ERROR,
            message="command timed out",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
    except OSError as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))

    return Observation(
        result.returncode == 0,
        FeedbackKind.TOOL_SUCCESS if result.returncode == 0 else FeedbackKind.COMMAND_ERROR,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _safe_execution_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    executable = argv[0].lower()
    if executable == "rg" and "--no-config" not in argv[1:]:
        return [argv[0], "--no-config", *argv[1:]]
    if executable == "git" and len(argv) > 1 and argv[1].lower() in {"diff", "show", "log"}:
        return [argv[0], argv[1], "--no-ext-diff", "--no-textconv", *argv[2:]]
    return argv


def _safe_execution_env(argv: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("RIPGREP_CONFIG_PATH", None)
    if argv and argv[0].lower() == "git":
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_EXTERNAL_DIFF"] = ""
        env["GIT_PAGER"] = "cat"
    return env
