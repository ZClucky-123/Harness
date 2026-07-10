from pathlib import Path

from guarded_harness.core.observations import FeedbackKind, Observation


def _workspace_path(workspace_root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("file path is required")
    root = Path(workspace_root).resolve()
    path = (Path(value) if Path(value).is_absolute() else root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("file path is outside workspace") from exc
    return path


def read_file(workspace_root: Path, path: object) -> Observation:
    try:
        content = _workspace_path(workspace_root, path).read_text()
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    return Observation(True, FeedbackKind.TOOL_SUCCESS, stdout=content)


def write_file(workspace_root: Path, path: object, content: object) -> Observation:
    try:
        target = _workspace_path(workspace_root, path)
        if not isinstance(content, str):
            raise ValueError("file content must be a string")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    return Observation(True, FeedbackKind.TOOL_SUCCESS)
