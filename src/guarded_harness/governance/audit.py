from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    id: str
    session_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime
