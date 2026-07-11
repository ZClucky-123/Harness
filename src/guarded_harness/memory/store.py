import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from guarded_harness.core.sessions import SessionState, SessionStatus
from guarded_harness.governance.approvals import ApprovalRequest
from guarded_harness.governance.audit import AuditEvent
from guarded_harness.governance.redaction import redact_secrets, reject_secrets


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    kind: str
    content: str
    tags: list[str]
    created_at: datetime


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_db_path(db_path: Path, workspace_root: Path | None) -> Path:
    path = Path(db_path)
    if ".." in path.parts:
        raise ValueError("database path must not contain traversal")

    if workspace_root is None and path.is_absolute():
        raise ValueError("absolute database paths require a workspace root")

    resolved_path = path.resolve()
    if resolved_path.parent == resolved_path:
        raise ValueError("database path must not be a filesystem root")

    sensitive_roots = (
        Path.home() / ".aws",
        Path.home() / ".config",
        Path.home() / ".gnupg",
        Path.home() / ".ssh",
        Path("/bin"),
        Path("/etc"),
        Path("/sbin"),
        Path("/usr"),
        Path("/var"),
        Path(os.environ.get("ProgramData", "C:/ProgramData")),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")),
        Path(os.environ.get("SystemRoot", "C:/Windows")),
    )
    if any(_is_within(resolved_path, root.resolve()) for root in sensitive_roots):
        raise ValueError("database path is in a sensitive or system location")

    trusted_root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    if not _is_within(resolved_path, trusted_root):
        raise ValueError("database path must be inside the workspace root")

    return resolved_path


class SQLiteStore:
    def __init__(self, db_path: Path, workspace_root: Path | None = None):
        self.db_path = _validate_db_path(db_path, workspace_root)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, task TEXT NOT NULL, workspace TEXT NOT NULL,
              status TEXT NOT NULL, step_count INTEGER NOT NULL,
              pending_approval_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, event_type TEXT NOT NULL,
              payload TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, action_json TEXT NOT NULL,
              reason TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT
            );
            CREATE TABLE IF NOT EXISTS memory_entries (
              id TEXT PRIMARY KEY, kind TEXT NOT NULL, content TEXT NOT NULL,
              tags TEXT NOT NULL, created_at TEXT NOT NULL
            );
            """)

    def create_session(self, task: str, workspace: Path) -> SessionState:
        reject_secrets(task, "session task")
        session_id = str(uuid4())
        timestamp = _now()
        with self._connect() as db:
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (session_id, task, str(workspace), SessionStatus.RUNNING.value, 0, None, timestamp, timestamp))
        return SessionState(session_id, task, SessionStatus.RUNNING, Path(workspace))

    def get_session(self, session_id: str) -> SessionState:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(session_id)
        return SessionState(
            row["id"],
            row["task"],
            SessionStatus(row["status"]),
            Path(row["workspace"]),
            row["step_count"],
            row["pending_approval_id"],
        )

    def update_session(self, session: SessionState) -> None:
        with self._connect() as db:
            result = db.execute(
                """
                UPDATE sessions
                SET status = ?, step_count = ?, pending_approval_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    session.status.value,
                    session.step_count,
                    session.pending_approval_id,
                    _now(),
                    session.id,
                ),
            )
        if result.rowcount == 0:
            raise KeyError(session.id)

    def append_audit(self, session_id: str, event_type: str, payload: dict) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                       (str(uuid4()), session_id, event_type, json.dumps(redact_secrets(payload)), _now()))

    def list_audit(self, session_id: str) -> list[AuditEvent]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM audit_events WHERE session_id = ? ORDER BY created_at", (session_id,)).fetchall()
        return [AuditEvent(row["id"], row["session_id"], row["event_type"], redact_secrets(json.loads(row["payload"])), datetime.fromisoformat(row["created_at"])) for row in rows]

    def create_approval(self, session_id: str, action_json: str, reason: str) -> ApprovalRequest:
        reject_secrets(action_json, "approval action")
        reject_secrets(reason, "approval reason")
        approval_id = str(uuid4())
        timestamp = _now()
        with self._connect() as db:
            db.execute("INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (approval_id, session_id, action_json, reason, "pending", timestamp, None))
        return ApprovalRequest(approval_id, session_id, action_json, reason, "pending", datetime.fromisoformat(timestamp))

    def create_approval_and_pause_session(
        self,
        session: SessionState,
        action_json: str,
        reason: str,
    ) -> ApprovalRequest:
        reject_secrets(action_json, "approval action")
        reject_secrets(reason, "approval reason")
        approval_id = str(uuid4())
        timestamp = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
                (approval_id, session.id, action_json, reason, "pending", timestamp, None),
            )
            result = db.execute(
                """
                UPDATE sessions
                SET status = ?, step_count = ?, pending_approval_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    SessionStatus.WAITING_APPROVAL.value,
                    session.step_count,
                    approval_id,
                    timestamp,
                    session.id,
                ),
            )
            if result.rowcount == 0:
                raise KeyError(session.id)
        session.status = SessionStatus.WAITING_APPROVAL
        session.pending_approval_id = approval_id
        return ApprovalRequest(
            approval_id,
            session.id,
            action_json,
            reason,
            "pending",
            datetime.fromisoformat(timestamp),
        )

    def resolve_approval(self, approval_id: str, approved: bool) -> ApprovalRequest:
        status = "approved" if approved else "denied"
        timestamp = _now()
        with self._connect() as db:
            result = db.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = ?",
                (status, timestamp, approval_id, "pending"),
            )
            row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        if result.rowcount == 0:
            raise ValueError("approval is already resolved")
        return ApprovalRequest(row["id"], row["session_id"], row["action_json"], row["reason"], row["status"], datetime.fromisoformat(row["created_at"]), datetime.fromisoformat(row["resolved_at"]))

    def begin_approval_resolution(
        self,
        approval_id: str,
        approved: bool,
    ) -> tuple[ApprovalRequest, SessionState]:
        approval_status = "executing" if approved else "denied"
        timestamp = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            approval_row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if approval_row is None:
                raise KeyError(approval_id)
            if approval_row["status"] != "pending":
                raise ValueError("approval is already resolved")
            session_row = db.execute("SELECT * FROM sessions WHERE id = ?", (approval_row["session_id"],)).fetchone()
            if session_row is None:
                raise KeyError(approval_row["session_id"])
            if (
                session_row["status"] != SessionStatus.WAITING_APPROVAL.value
                or session_row["pending_approval_id"] != approval_id
            ):
                raise ValueError("session is not waiting for this approval")
            db.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ?",
                (approval_status, timestamp, approval_id),
            )
            db.execute(
                "UPDATE sessions SET status = ?, pending_approval_id = NULL, updated_at = ? WHERE id = ?",
                (SessionStatus.RUNNING.value, timestamp, approval_row["session_id"]),
            )

        approval = ApprovalRequest(
            approval_row["id"],
            approval_row["session_id"],
            approval_row["action_json"],
            approval_row["reason"],
            approval_status,
            datetime.fromisoformat(approval_row["created_at"]),
            datetime.fromisoformat(timestamp),
        )
        return approval, self.get_session(approval.session_id)

    def finalize_approval_execution(self, approval_id: str, succeeded: bool) -> ApprovalRequest:
        status = "executed" if succeeded else "failed"
        with self._connect() as db:
            result = db.execute(
                "UPDATE approvals SET status = ? WHERE id = ? AND status = ?",
                (status, approval_id, "executing"),
            )
            row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        if result.rowcount == 0:
            raise ValueError("approval is not executing")
        return ApprovalRequest(
            row["id"],
            row["session_id"],
            row["action_json"],
            row["reason"],
            row["status"],
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["resolved_at"]),
        )

    def mark_approval_failed(self, approval_id: str, reason: str) -> ApprovalRequest:
        timestamp = _now()
        event_id = str(uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                raise KeyError(approval_id)
            if row["status"] != "executing":
                raise ValueError("approval is not executing")
            db.execute("UPDATE approvals SET status = ? WHERE id = ?", ("failed", approval_id))
            db.execute(
                "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
                (SessionStatus.FAILED.value, timestamp, row["session_id"]),
            )
            db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (
                    event_id,
                    row["session_id"],
                    "approval_manually_failed",
                    json.dumps(redact_secrets({"approval_id": approval_id, "reason": reason})),
                    timestamp,
                ),
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        with self._connect() as db:
            row = db.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return ApprovalRequest(
            row["id"],
            row["session_id"],
            row["action_json"],
            row["reason"],
            row["status"],
            datetime.fromisoformat(row["created_at"]),
            datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )

    def list_pending_approvals(self) -> list[ApprovalRequest]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM approvals WHERE status = ? ORDER BY created_at",
                ("pending",),
            ).fetchall()
        return [
            ApprovalRequest(
                row["id"],
                row["session_id"],
                row["action_json"],
                row["reason"],
                row["status"],
                datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def list_unfinished_approvals(self) -> list[ApprovalRequest]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM approvals WHERE status IN (?, ?, ?) ORDER BY created_at",
                ("pending", "executing", "failed"),
            ).fetchall()
        return [
            ApprovalRequest(
                row["id"],
                row["session_id"],
                row["action_json"],
                row["reason"],
                row["status"],
                datetime.fromisoformat(row["created_at"]),
                datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            )
            for row in rows
        ]

    def add_memory(self, kind: str, content: str, tags: list[str]) -> MemoryEntry:
        reject_secrets(kind, "memory kind")
        reject_secrets(content, "memory content")
        reject_secrets(tags, "memory tags")
        entry_id = str(uuid4())
        timestamp = _now()
        with self._connect() as db:
            db.execute("INSERT INTO memory_entries VALUES (?, ?, ?, ?, ?)", (entry_id, kind, content, json.dumps(tags), timestamp))
        return MemoryEntry(entry_id, kind, content, tags, datetime.fromisoformat(timestamp))

    def list_memory(self, limit: int) -> list[MemoryEntry]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM memory_entries ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [MemoryEntry(row["id"], row["kind"], row["content"], json.loads(row["tags"]), datetime.fromisoformat(row["created_at"])) for row in rows]
