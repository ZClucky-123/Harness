from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FeedbackKind(str, Enum):
    TOOL_SUCCESS = "tool_success"
    TEST_FAILURE = "test_failure"
    LINT_FAILURE = "lint_failure"
    COMMAND_ERROR = "command_error"
    POLICY_DENIED = "policy_denied"
    APPROVAL_DENIED = "approval_denied"


@dataclass(frozen=True)
class Observation:
    success: bool
    feedback_kind: FeedbackKind
    message: str = ""
    stdout: str = ""
    stderr: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
