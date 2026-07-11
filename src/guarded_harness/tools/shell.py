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
    try:
        result = subprocess.run(
            argv,
            cwd=workspace_root,
            shell=False,
            text=True,
            capture_output=True,
            timeout=30,
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
