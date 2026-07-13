import os
import shutil
import subprocess
from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation
from guarded_harness.governance.shell_command import (
    argv_paths_within_workspace,
    parse_shell_argv,
    unsupported_direct_command_reason,
)


_PSEUDO_READ_COMMANDS = {"ls", "dir", "pwd", "cat", "type", "echo"}
_PSEUDO_DELETE_COMMANDS = {"rm", "del", "rd", "rmdir"}


def run_shell(workspace_root: Path, command: object, approved: bool = False) -> Observation:
    if not isinstance(command, str) or not command:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="shell command is required")
    try:
        argv = parse_shell_argv(command)
    except ValueError as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    pseudo_observation = _run_pseudo_shell(Path(workspace_root).resolve(), argv, approved)
    if pseudo_observation is not None:
        return pseudo_observation
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
            encoding="utf-8",
            errors="replace",
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


def _run_pseudo_shell(workspace_root: Path, argv: list[str], approved: bool) -> Observation | None:
    if not argv:
        return None
    executable = _pseudo_executable(argv[0])
    if executable in _PSEUDO_READ_COMMANDS:
        return _run_pseudo_read(workspace_root, executable, argv[1:])
    if executable in _PSEUDO_DELETE_COMMANDS:
        if not approved:
            return Observation(False, FeedbackKind.APPROVAL_DENIED, message="approval required: shell delete requires approval")
        return _run_pseudo_delete(workspace_root, executable, argv[1:])
    return None


def _pseudo_executable(value: str) -> str:
    executable = value.replace("\\", "/").rsplit("/", 1)[-1].strip("\"'").lower()
    return executable[:-4] if executable.endswith(".exe") else executable


def _run_pseudo_read(workspace_root: Path, executable: str, arguments: list[str]) -> Observation:
    if executable in {"ls", "dir"}:
        return _pseudo_list_dir(workspace_root, arguments)
    if executable == "pwd":
        if arguments:
            return Observation(False, FeedbackKind.COMMAND_ERROR, message="pwd does not accept arguments")
        return Observation(True, FeedbackKind.TOOL_SUCCESS, message="printed workspace path", stdout=str(workspace_root))
    if executable in {"cat", "type"}:
        return _pseudo_cat(workspace_root, arguments)
    if executable == "echo":
        text = " ".join(arguments)
        return Observation(True, FeedbackKind.TOOL_SUCCESS, message="echoed text", stdout=f"{text}\n")
    return None


def _pseudo_list_dir(workspace_root: Path, arguments: list[str]) -> Observation:
    targets = [argument for argument in arguments if not argument.startswith("-")]
    if len(targets) > 1:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="ls accepts at most one path")
    try:
        target = _workspace_path(workspace_root, targets[0] if targets else ".")
        if target.is_dir():
            entries = []
            for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                suffix = "/" if child.is_dir() else ""
                entries.append(f"{child.name}{suffix}")
        elif target.exists() or target.is_symlink():
            entries = [target.name + ("/" if target.is_dir() else "")]
        else:
            return Observation(False, FeedbackKind.COMMAND_ERROR, message="ls target does not exist")
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    display_path = _workspace_relative_path(workspace_root, target)
    return Observation(
        True,
        FeedbackKind.TOOL_SUCCESS,
        message=f"listed {display_path}",
        stdout="\n".join(entries) + ("\n" if entries else ""),
        metadata={"path": display_path, "entries": len(entries)},
    )


def _pseudo_cat(workspace_root: Path, arguments: list[str]) -> Observation:
    if len(arguments) != 1:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="cat requires exactly one file path")
    try:
        target = _workspace_path(workspace_root, arguments[0])
        if not target.is_file():
            return Observation(False, FeedbackKind.COMMAND_ERROR, message="cat target is not a file")
        content = target.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    display_path = _workspace_relative_path(workspace_root, target)
    return Observation(
        True,
        FeedbackKind.TOOL_SUCCESS,
        message=f"read {display_path}",
        stdout=content,
        metadata={"path": display_path, "characters": len(content), "utf8_bytes": len(content.encode("utf-8"))},
    )


def _run_pseudo_delete(workspace_root: Path, executable: str, arguments: list[str]) -> Observation:
    recursive = executable in {"rd", "rmdir"}
    force = False
    targets: list[str] = []
    for argument in arguments:
        lowered = argument.lower()
        if executable == "rm" and lowered.startswith("-"):
            recursive = recursive or "r" in lowered
            force = force or "f" in lowered
            continue
        if executable in {"del", "rd", "rmdir"} and lowered.startswith("/"):
            recursive = recursive or "s" in lowered
            force = force or "q" in lowered or "f" in lowered
            continue
        targets.append(argument)
    if len(targets) != 1:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=f"{executable} requires exactly one target")
    try:
        target = _workspace_path(workspace_root, targets[0])
        if target == workspace_root:
            return Observation(False, FeedbackKind.POLICY_DENIED, message="refusing to delete workspace root")
        if not target.exists() and not target.is_symlink():
            if force:
                return Observation(True, FeedbackKind.TOOL_SUCCESS, message=f"deleted {_display_target(workspace_root, target)}")
            return Observation(False, FeedbackKind.COMMAND_ERROR, message="delete target does not exist")
        if target.is_dir() and not target.is_symlink():
            if not recursive:
                return Observation(False, FeedbackKind.COMMAND_ERROR, message="directory delete requires recursive flag")
            shutil.rmtree(target)
        else:
            target.unlink()
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    return Observation(True, FeedbackKind.TOOL_SUCCESS, message=f"deleted {_display_target(workspace_root, target)}")


def _workspace_path(workspace_root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("path is required")
    path = Path(value)
    target = (path if path.is_absolute() else workspace_root / path).resolve()
    try:
        target.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("shell path is outside workspace") from exc
    return target


def _workspace_relative_path(workspace_root: Path, path: Path) -> str:
    value = path.relative_to(workspace_root).as_posix()
    return value if value else "."


def _display_target(workspace_root: Path, path: Path) -> str:
    try:
        return _workspace_relative_path(workspace_root, path)
    except ValueError:
        return str(path)


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
