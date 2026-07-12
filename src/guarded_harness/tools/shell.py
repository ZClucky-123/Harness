import os
import subprocess
from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation
from guarded_harness.governance.shell_command import (
    argv_paths_within_workspace,
    parse_shell_argv,
    unsupported_direct_command_reason,
)


def run_shell(workspace_root: Path, command: object) -> Observation:
    if not isinstance(command, str) or not command:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="shell command is required")
    try:
        argv = parse_shell_argv(command)
    except ValueError as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    unsupported_reason = unsupported_direct_command_reason(argv)
    if unsupported_reason is not None:
        return Observation(False, FeedbackKind.POLICY_DENIED, message=unsupported_reason)
    if not argv_paths_within_workspace(argv, workspace_root):
        return Observation(False, FeedbackKind.POLICY_DENIED, message="shell path is outside workspace")
    if _has_external_helper_option(argv):
        return Observation(False, FeedbackKind.POLICY_DENIED, message="external helper options are denied")
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
    if executable == "git":
        return [
            argv[0],
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
            *(_safe_git_subcommand_argv(argv[1:])),
        ]
    return argv


def _safe_git_subcommand_argv(arguments: list[str]) -> list[str]:
    if arguments and arguments[0].lower() in {"diff", "show", "log"}:
        return [arguments[0], "--no-ext-diff", "--no-textconv", *arguments[1:]]
    return arguments


def _safe_execution_env(argv: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("RIPGREP_CONFIG_PATH", None)
    if argv and argv[0].lower() == "git":
        _clear_git_config_env(env)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_EXTERNAL_DIFF"] = ""
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env["GIT_PAGER"] = "cat"
    return env


def _has_external_helper_option(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = argv[0].lower()
    arguments = [argument.lower() for argument in argv[1:]]
    if executable == "rg":
        return any(
            argument == "--pre"
            or argument.startswith("--pre=")
            or argument == "--pre-glob"
            or argument.startswith("--pre-glob=")
            for argument in arguments
        )
    if executable != "git":
        return False
    return any(
        argument in {
            "--ext-diff",
            "--external-diff",
            "--textconv",
            "--no-textconv",
            "--paginate",
            "--no-pager",
            "--config",
            "-c",
        }
        or argument.startswith("--ext-diff=")
        or argument.startswith("--external-diff=")
        or argument.startswith("--textconv=")
        or argument.startswith("--no-textconv=")
        or argument.startswith("--paginate=")
        or argument.startswith("--pager=")
        or argument.startswith("--exec-path")
        or argument.startswith("--config=")
        for argument in arguments
    )


def _clear_git_config_env(env: dict[str, str]) -> None:
    for key in list(env):
        if key == "GIT_CONFIG_COUNT" or key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            env.pop(key, None)
