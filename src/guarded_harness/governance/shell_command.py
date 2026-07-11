import re
import shlex
from pathlib import Path


_SHELL_CONTROL_RE = re.compile(r"(?:\r|\n|`|\$\(|[|&;<>])")
_INLINE_INTERPRETER_FLAGS = {
    "python": {"-c"},
    "python3": {"-c"},
    "py": {"-c"},
    "pypy": {"-c"},
    "pypy3": {"-c"},
    "node": {"-e", "--eval"},
    "nodejs": {"-e", "--eval"},
    "ruby": {"-e"},
    "perl": {"-e"},
    "php": {"-r"},
    "lua": {"-e"},
}
_SHELL_WRAPPER_FLAGS = {
    "sh": {"-c"},
    "bash": {"-c"},
    "zsh": {"-c"},
    "powershell": {"-command", "-encodedcommand", "-ec"},
    "pwsh": {"-command", "-encodedcommand", "-ec"},
    "cmd": {"/c", "/k"},
}


def contains_shell_control_syntax(command: str) -> bool:
    return _SHELL_CONTROL_RE.search(command) is not None


def forbidden_interpreter_reason(command: str) -> str | None:
    """Identify argv forms that can hide arbitrary code from path validation."""
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not tokens:
        return None
    normalized_tokens = [token.strip("\"'") for token in tokens]
    executable = normalized_tokens[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable.endswith(".exe"):
        executable = executable[:-4]
    if executable == "env":
        return "process wrapper commands are denied and cannot be approved"
    arguments = {token.lower() for token in normalized_tokens[1:]}
    interpreter_flags = _INLINE_INTERPRETER_FLAGS.get(executable, set())
    if re.fullmatch(r"python\d*(?:\.\d+)*", executable):
        interpreter_flags = {"-c"}
    if arguments.intersection(interpreter_flags):
        return "inline interpreter code is denied and cannot be approved"
    if executable in _SHELL_WRAPPER_FLAGS:
        return "shell wrapper commands are denied as potentially destructive and cannot be approved"
    return None


def parse_shell_argv(command: str) -> list[str]:
    if contains_shell_control_syntax(command):
        raise ValueError("shell control syntax is not supported")
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError as exc:
        raise ValueError("shell command could not be parsed") from exc
    if not tokens:
        raise ValueError("shell command is required")
    return [_strip_matching_quotes(token) for token in tokens]


def argv_paths_within_workspace(argv: list[str], workspace_root: Path) -> bool:
    root = Path(workspace_root).resolve()
    for value in _path_candidates(argv, root):
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        try:
            path.resolve().relative_to(root)
        except (OSError, ValueError):
            return False
    return True


def _path_candidates(argv: list[str], workspace_root: Path):
    skip_inline_code = len(argv) >= 2 and argv[0].lower() in {"python", "python3"} and argv[1] == "-c"
    for index, argument in enumerate(argv[1:], start=1):
        if skip_inline_code and index == 2:
            continue
        value = argument.split("=", 1)[1] if argument.startswith("-") and "=" in argument else argument
        if value.startswith("-"):
            continue
        if _looks_like_path(value, workspace_root):
            yield value


def _looks_like_path(value: str, workspace_root: Path) -> bool:
    if not value or value in {".", ".."}:
        return bool(value)
    if value.startswith(("/", "\\", "~", ".\\", "./", "..\\", "../")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", value):
        return True
    if "/" in value or "\\" in value:
        return True
    try:
        return (workspace_root / value).exists() or (workspace_root / value).is_symlink()
    except OSError:
        return True


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
