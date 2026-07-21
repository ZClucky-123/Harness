import os
import json
from pathlib import Path

from guarded_harness.config.schema import HarnessConfig


def load_config(environ: dict[str, str] | None = None, workspace_root: Path | None = None) -> HarnessConfig:
    values = environ if environ is not None else os.environ
    file_config = _load_provider_file(workspace_root)
    mode = values.get("GUARDED_HARNESS_MODE", file_config.get("mode", HarnessConfig.mode))
    if mode not in {"mock", "live"}:
        mode = HarnessConfig.mode
    timeout = float(values.get("GUARDED_HARNESS_TIMEOUT", file_config.get("timeout", HarnessConfig.timeout)))
    return HarnessConfig(
        mode=mode,
        base_url=values.get("GUARDED_HARNESS_BASE_URL", file_config.get("base_url", HarnessConfig.base_url)),
        model=values.get("GUARDED_HARNESS_MODEL", file_config.get("model", HarnessConfig.model)),
        api_key=values.get("GUARDED_HARNESS_API_KEY") or None,
        timeout=timeout,
    )


def _load_provider_file(workspace_root: Path | None) -> dict[str, str | float]:
    if workspace_root is None:
        return {}
    path = Path(workspace_root).resolve() / ".guarded-harness" / "provider.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    result: dict[str, str | float] = {}
    for key in ("mode", "base_url", "model"):
        value = loaded.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    timeout = loaded.get("timeout")
    if isinstance(timeout, int | float):
        result["timeout"] = float(timeout)
    elif isinstance(timeout, str) and timeout.strip():
        try:
            result["timeout"] = float(timeout)
        except ValueError:
            pass
    return result
