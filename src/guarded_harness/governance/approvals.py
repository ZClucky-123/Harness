from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    session_id: str
    action_json: str
    reason: str
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
