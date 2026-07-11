import json
import re
from typing import Any


_OPENAI_SECRET_RE = re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9][A-Za-z0-9._-]*", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[^\s\"',;]+", re.IGNORECASE)
_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:database_url|db_url|[A-Za-z0-9_-]*(?:key|token|secret|password|authorization)[A-Za-z0-9_-]*)\s*[=:]\s*)((?:Bearer\s+)?[^\s,;]+)"
)
_URL_USERINFO_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9+.-]*://)([^\s/@:]+):([^\s/@]+)@")
_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN ((?:[A-Z0-9]+ )?PRIVATE KEY)-----.*?-----END \1-----",
    re.IGNORECASE | re.DOTALL,
)
_PEM_PRIVATE_KEY_MARKER_RE = re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----", re.IGNORECASE)
_SECRET_KEY_RE = re.compile(r"(?:^|[_-])(?:key|token|secret|password|authorization)(?:$|[_-])", re.IGNORECASE)
_CAMEL_SECRET_KEY_RE = re.compile(r"(?:Key|Token|Secret|Password|Authorization)$")
_SECRET_ERROR = "contains a secret; use keyring/secret reference instead"


def _is_secret_key(key: object) -> bool:
    text = str(key)
    return _SECRET_KEY_RE.search(text) is not None or _CAMEL_SECRET_KEY_RE.search(text) is not None


def contains_secret(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_is_secret_key(key) or contains_secret(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(contains_secret(item) for item in value)
    if not isinstance(value, str):
        return False
    if value.lstrip().startswith(("{", "[")):
        try:
            structured = json.loads(value)
        except (TypeError, ValueError):
            structured = None
        if isinstance(structured, (dict, list)) and contains_secret(structured):
            return True
    return any(
        pattern.search(value) is not None
        for pattern in (
            _OPENAI_SECRET_RE,
            _BEARER_RE,
            _ASSIGNMENT_RE,
            _URL_USERINFO_RE,
            _PEM_PRIVATE_KEY_RE,
            _PEM_PRIVATE_KEY_MARKER_RE,
        )
    )


def reject_secrets(value: Any, field_name: str) -> None:
    if contains_secret(value):
        raise ValueError(f"{field_name} {_SECRET_ERROR}")


def redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        redacted = _ASSIGNMENT_RE.sub(r"\1[REDACTED]", value)
        redacted = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", redacted)
        redacted = _PEM_PRIVATE_KEY_RE.sub("[REDACTED]", redacted)
        redacted = _PEM_PRIVATE_KEY_MARKER_RE.sub("[REDACTED]", redacted)
        redacted = _BEARER_RE.sub("[REDACTED]", redacted)
        return _OPENAI_SECRET_RE.sub("[REDACTED]", redacted)
    return value


def redact_action_json(action_json: str) -> str:
    try:
        action = json.loads(action_json)
    except (TypeError, ValueError):
        return str(redact_secrets(action_json))
    return json.dumps(redact_secrets(action), ensure_ascii=False, sort_keys=True)
