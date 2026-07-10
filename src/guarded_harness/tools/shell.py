import subprocess
from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation


def run_shell(workspace_root: Path, command: object) -> Observation:
    if not isinstance(command, str) or not command:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="shell command is required")
    try:
        result = subprocess.run(
            command,
            cwd=workspace_root,
            shell=True,
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
