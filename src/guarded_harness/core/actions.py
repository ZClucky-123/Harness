from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any


class ActionType(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    RUN_SHELL = "run_shell"
    RUN_TESTS = "run_tests"
    REMEMBER = "remember"
    FINISH = "finish"


@dataclass(frozen=True)
class Action:
    type: ActionType
    payload: dict[str, Any] = field(default_factory=dict)
    raw_source_text: str | None = None


def parse_action(raw: str) -> Action:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid action json") from exc

    if not isinstance(decoded, dict) or "type" not in decoded:
        raise ValueError("unknown action type")
    try:
        action_type = ActionType(decoded["type"])
    except (ValueError, TypeError) as exc:
        raise ValueError("unknown action type") from exc

    payload = {key: value for key, value in decoded.items() if key != "type"}
    return Action(action_type, payload, raw)
