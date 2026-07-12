import subprocess
from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation


def run_tests(workspace_root: Path, command: object) -> Observation:
    if not _is_valid_command(command):
        return Observation(
            False,
            FeedbackKind.COMMAND_ERROR,
            message="test command must be a non-empty list of non-empty strings",
        )
    try:
        result = subprocess.run(
            command,
            cwd=workspace_root,
            text=True,
            capture_output=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        return Observation(
            False,
            FeedbackKind.TEST_FAILURE,
            message="test command timed out",
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
    except OSError as exc:
        return Observation(False, FeedbackKind.TEST_FAILURE, message=str(exc))

    return Observation(
        result.returncode == 0,
        FeedbackKind.TOOL_SUCCESS if result.returncode == 0 else FeedbackKind.TEST_FAILURE,
        message=(
            f"test command passed with exit code {result.returncode}"
            if result.returncode == 0
            else f"test command failed with exit code {result.returncode}"
        ),
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _is_valid_command(command: object) -> bool:
    return isinstance(command, list) and bool(command) and all(
        isinstance(part, str) and bool(part.strip()) for part in command
    )
