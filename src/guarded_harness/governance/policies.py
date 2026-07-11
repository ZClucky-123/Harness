from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from guarded_harness.governance.shell_command import (
    argv_paths_within_workspace,
    contains_shell_control_syntax,
    forbidden_interpreter_reason,
    parse_shell_argv,
)


class DecisionType(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    NEEDS_APPROVAL = "needs_approval"


@dataclass(frozen=True)
class PolicyDecision:
    decision: DecisionType
    risk_level: str
    reason: str


def allow(reason: str = "action is within policy") -> PolicyDecision:
    return PolicyDecision(DecisionType.ALLOW, "low", reason)


def deny(reason: str) -> PolicyDecision:
    return PolicyDecision(DecisionType.DENY, "high", reason)


def needs_approval(reason: str) -> PolicyDecision:
    return PolicyDecision(DecisionType.NEEDS_APPROVAL, "medium", reason)


def classify_shell_command(command: str, workspace_root: Path) -> PolicyDecision:
    forbidden_reason = forbidden_interpreter_reason(command)
    if forbidden_reason is not None:
        return deny(forbidden_reason)
    has_control_syntax = contains_shell_control_syntax(command)
    if has_control_syntax and _has_path_outside_workspace(command, workspace_root):
        return deny("shell path is outside workspace")
    if has_control_syntax:
        return needs_approval("shell syntax requires approval and cannot be executed directly")
    for segment in re.split(r"(?:&&|\|\||;|\||&)", command):
        decision = _classify_shell_segment(segment, workspace_root)
        if decision.decision is not DecisionType.ALLOW:
            return decision
    return allow()


def _classify_shell_segment(command: str, workspace_root: Path) -> PolicyDecision:
    try:
        raw_tokens = parse_shell_argv(command)
        tokens = [_clean_token(token) for token in raw_tokens]
    except ValueError:
        return needs_approval("shell command could not be parsed and requires approval")

    if not tokens:
        return allow()

    executable = tokens[0]
    arguments = tokens[1:]
    if _is_destructive(executable, arguments):
        return deny("destructive shell command is denied")
    wrapper_command = _wrapper_command(executable, arguments)
    if wrapper_command is not None:
        return classify_shell_command(wrapper_command, workspace_root)
    if not argv_paths_within_workspace(raw_tokens, workspace_root) or _has_path_outside_workspace(command, workspace_root):
        return deny("shell path is outside workspace")
    if _writes_environment_file(command, executable, arguments):
        return needs_approval("modifying an environment file requires approval")
    if executable == "git" and (not arguments or arguments[0] not in {"status", "diff", "log", "show", "branch", "rev-parse"}):
        return deny("non-read-only git commands are denied and cannot be approved")
    if _requires_approval(executable, arguments):
        return needs_approval("shell command requires approval")
    if _is_known_safe_command(executable, arguments):
        return allow()
    return deny("shell command is not in the safe allowlist and cannot be approved")


def _is_destructive(executable: str, arguments: list[str]) -> bool:
    if executable in {"format", "del", "rd"} and (executable == "format" or "/s" in arguments):
        return True
    if executable == "mkfs" or executable.startswith("mkfs."):
        return True
    if executable == "rm" and "/" in arguments and _has_recursive_force(arguments):
        return True
    return executable == "remove-item" and _has_recursive_force(arguments) and any(
        argument.rstrip("\\/") in {"c:", "c"} for argument in arguments
    )


def _requires_approval(executable: str, arguments: list[str]) -> bool:
    if (executable, arguments[0] if arguments else "") in {
        ("git", "push"),
        ("pip", "install"),
        ("pip3", "install"),
        ("npm", "install"),
        ("npm", "ci"),
        ("twine", "upload"),
        ("docker", "push"),
    }:
        return True
    if executable in {"python", "python3"} and arguments[:3] == ["-m", "pip", "install"]:
        return True
    return executable in {"rm", "del", "remove-item"}


def _has_recursive_force(arguments: list[str]) -> bool:
    return any(arg in {"-recurse", "/s"} or arg.startswith("-") and "r" in arg for arg in arguments) and any(
        arg in {"-force", "/f"} or arg.startswith("-") and "f" in arg for arg in arguments
    )


def _clean_token(token: str) -> str:
    return token.strip().strip("\"'").lower()


def _wrapper_command(executable: str, arguments: list[str]) -> str | None:
    if executable in {"sh", "bash", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        for index, argument in enumerate(arguments[:-1]):
            if argument in {"-c", "-command"}:
                return arguments[index + 1]
    if executable in {"cmd", "cmd.exe"}:
        for index, argument in enumerate(arguments[:-1]):
            if argument == "/c":
                return arguments[index + 1]
    if executable == "sudo":
        index = 0
        while index < len(arguments) and arguments[index].startswith("-"):
            index += 2 if arguments[index] in {"-u", "--user", "-g", "--group"} else 1
        if index < len(arguments):
            return " ".join(arguments[index:])
    return None


def _has_path_outside_workspace(command: str, workspace_root: Path) -> bool:
    if has_environment_reference(command):
        return True
    return any(not _is_within_workspace(path, workspace_root) for path in _shell_path_references(command))


def _shell_path_references(command: str) -> list[str]:
    pattern = r"(?<![\w])(?:\$HOME[\\/][^\s\"']*|\$\{HOME\}[\\/][^\s\"']*|%USERPROFILE%[\\/][^\s\"']*|\$env:USERPROFILE[\\/][^\s\"']*|\.\.[\\/][^\s\"']*|[a-zA-Z]:[\\/][^\s\"']*|\\[^\s\"']*|/[^\s\"']*|~/[^\s\"']*)"
    return [match.rstrip(",;:)]}") for match in re.findall(pattern, command, flags=re.IGNORECASE)]


def _is_within_workspace(value: str, workspace_root: Path) -> bool:
    if has_environment_reference(value) or value.startswith(("\\", "//", "~/", "~\\")):
        return False
    path = Path(value)
    if not path.is_absolute():
        path = workspace_root / path
    elif value.startswith("/") and not value.startswith("//"):
        path = Path(Path.cwd().anchor) / value.lstrip("/")
    try:
        path.resolve().relative_to(workspace_root.resolve())
    except ValueError:
        return False
    return True


def has_environment_reference(value: str) -> bool:
    return re.search(
        r"(?:\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$env:[A-Za-z_][A-Za-z0-9_]*|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%)",
        value,
    ) is not None


def _writes_environment_file(command: str, executable: str, arguments: list[str]) -> bool:
    target = _redirect_target(command)
    if target is not None and Path(target).name.lower().startswith(".env"):
        return True
    return executable in {"tee", "set-content", "out-file", "cp", "copy", "mv", "move"} and any(
        Path(argument).name.lower().startswith(".env") for argument in arguments
    )


def _is_known_safe_command(executable: str, arguments: list[str]) -> bool:
    if executable in {"cat", "type", "dir", "ls", "pwd", "whoami", "findstr", "get-content", "get-childitem"}:
        return True
    if executable == "rg":
        return _is_safe_rg_argv(arguments)
    if executable == "pytest":
        return _is_safe_pytest_argv(arguments)
    if executable == "git":
        return _is_safe_git_argv(arguments)
    if executable in {"python", "python3"}:
        return arguments[:2] == ["-m", "compileall"]
    return executable == "echo"


def _is_safe_rg_argv(arguments: list[str]) -> bool:
    return not any(
        argument == "--pre"
        or argument.startswith("--pre=")
        or argument == "--pre-glob"
        or argument.startswith("--pre-glob=")
        for argument in arguments
    )


def _is_safe_git_argv(arguments: list[str]) -> bool:
    if not arguments or arguments[0] not in {"status", "diff", "log", "show", "branch", "rev-parse"}:
        return False
    return not any(
        argument == "--ext-diff"
        or argument.startswith("--ext-diff=")
        or argument == "--external-diff"
        or argument.startswith("--external-diff=")
        or argument == "--textconv"
        or argument == "--no-textconv"
        or argument.startswith("--textconv=")
        or argument.startswith("--no-textconv=")
        or argument == "--paginate"
        or argument.startswith("--paginate=")
        or argument == "--no-pager"
        or argument.startswith("--pager=")
        or argument.startswith("--exec-path")
        or argument == "--config"
        or argument.startswith("--config=")
        or argument == "-c"
        for argument in arguments
    )


def _is_safe_pytest_argv(arguments: list[str]) -> bool:
    value_options = {"-k", "-m", "--maxfail", "--tb"}
    flag_options = {
        "-q",
        "-x",
        "--collect-only",
        "--disable-warnings",
        "--ff",
        "--lf",
        "--strict-config",
        "--strict-markers",
    }
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if not argument.startswith("-"):
            index += 1
            continue
        if argument in flag_options or argument.startswith(("--maxfail=", "--tb=")):
            index += 1
            continue
        if argument in value_options and index + 1 < len(arguments):
            index += 2
            continue
        return False
    return True


def _redirect_target(command: str) -> str | None:
    match = re.search(r">>?(?:\s*)[\"']?([^\s\"']+)", command)
    return _clean_token(match.group(1)) if match is not None else None
