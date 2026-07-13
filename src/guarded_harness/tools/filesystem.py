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


def _workspace_relative_path(workspace_root: Path, path: Path) -> str:
    return path.relative_to(Path(workspace_root).resolve()).as_posix()


def _size_metadata(workspace_root: Path, path: Path, content: str) -> dict[str, int | str]:
    return {
        "path": _workspace_relative_path(workspace_root, path),
        "characters": len(content),
        "utf8_bytes": len(content.encode("utf-8")),
    }


def read_file(workspace_root: Path, path: object) -> Observation:
    try:
        target = _workspace_path(workspace_root, path)
        content = target.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    metadata = _size_metadata(workspace_root, target, content)
    if content:
        message = (
            f"read {metadata['path']}: {metadata['characters']} characters, "
            f"{metadata['utf8_bytes']} UTF-8 bytes"
        )
    else:
        message = f"read {metadata['path']}: file is empty (0 characters, 0 UTF-8 bytes)"
    return Observation(True, FeedbackKind.TOOL_SUCCESS, message=message, stdout=content, metadata=metadata)


def write_file(workspace_root: Path, path: object, content: object) -> Observation:
    try:
        target = _workspace_path(workspace_root, path)
        if not isinstance(content, str):
            raise ValueError("file content must be a string")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except (OSError, ValueError) as exc:
        return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
    metadata = _size_metadata(workspace_root, target, content)
    message = (
        f"wrote {metadata['path']}: {metadata['characters']} characters, "
        f"{metadata['utf8_bytes']} UTF-8 bytes"
    )
    return Observation(True, FeedbackKind.TOOL_SUCCESS, message=message, metadata=metadata)
