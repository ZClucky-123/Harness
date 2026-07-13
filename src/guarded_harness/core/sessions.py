from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SessionStatus(str, Enum):
    RUNNING = "running"
    FINISHED = "finished"
    WAITING_APPROVAL = "waiting_approval"
    BLOCKED = "blocked"
    FAILED = "failed"
    MAX_STEPS = "max_steps"


@dataclass
class SessionState:
    id: str
    task: str
    status: SessionStatus
    workspace: Path | None = None
    step_count: int = 0
    pending_approval_id: str | None = None
    observations: list[Any] = field(default_factory=list)
