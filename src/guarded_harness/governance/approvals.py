from dataclasses import dataclass
from datetime import datetime

from guarded_harness.governance.redaction import redact_action_json, redact_secrets


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    session_id: str
    action_json: str
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None

    @property
    def redacted_action_json(self) -> str:
        return redact_action_json(self.action_json)

    @property
    def redacted_reason(self) -> str:
        redacted = redact_secrets(self.reason)
        return redacted if isinstance(redacted, str) else "[REDACTED]"
