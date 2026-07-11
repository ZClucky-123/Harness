import json
import re
from typing import Any


_SECRET_VALUE_RE = re.compile(
    r"(?:\bsk-[A-Za-z0-9][A-Za-z0-9._-]*\b|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b|\b[A-Za-z0-9_-]{32,}\b)",
    re.IGNORECASE,
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|token|secret|password|authorization)\s*[=:]\s*)((?:Bearer\s+)?[^\s,;]+)"
)
_SECRET_KEYS = ("key", "token", "secret", "password", "authorization")


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if any(term in key.lower() for term in _SECRET_KEYS) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        redacted = _ASSIGNMENT_RE.sub(r"\1[REDACTED]", value)
        return _SECRET_VALUE_RE.sub("[REDACTED]", redacted)
    return value


def redact_action_json(action_json: str) -> str:
    try:
        action = json.loads(action_json)
    except (TypeError, ValueError):
        return str(redact_secrets(action_json))
    return json.dumps(redact_secrets(action), ensure_ascii=False, sort_keys=True)
