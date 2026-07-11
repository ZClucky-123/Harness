from pathlib import Path
from typing import Any

from guarded_harness.core.actions import Action, ActionType, parse_action
from guarded_harness.core.observations import FeedbackKind, Observation
from guarded_harness.core.sessions import SessionState, SessionStatus
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.governance.policies import DecisionType
from guarded_harness.llm.base import LLMProvider
from guarded_harness.memory.store import SQLiteStore
from guarded_harness.tools.dispatcher import ToolDispatcher


class AgentLoop:
    def __init__(
        self,
        workspace_root: Path,
        llm: LLMProvider,
        store: SQLiteStore,
        dispatcher: ToolDispatcher,
        guardrail: Guardrail,
        max_steps: int = 10,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.llm = llm
        self.store = store
        self.dispatcher = dispatcher
        self.guardrail = guardrail
        self.max_steps = max_steps

    @classmethod
    def for_workspace(
        cls,
        workspace_root: Path,
        llm: LLMProvider,
        store: SQLiteStore | None = None,
        max_steps: int = 10,
    ) -> "AgentLoop":
        root = Path(workspace_root).resolve()
        guardrail = Guardrail(root)
        return cls(
            root,
            llm,
            store or SQLiteStore(root / "state.sqlite3", workspace_root=root),
            ToolDispatcher(root, test_command=["pytest", "-q"], guardrail=guardrail),
            guardrail,
            max_steps,
        )

    def run(self, task: str) -> SessionState:
        session = self.store.create_session(task, self.workspace_root)
        self.store.append_audit(session.id, "session_started", {"task": task})
        return self._continue(session)

    def resume_after_approval(self, approval_id: str, approved: bool) -> SessionState:
        approval = self.store.get_approval(approval_id)
        if approval.status != "pending":
            raise ValueError("approval is already resolved")
        session = self.store.get_session(approval.session_id)
        if session.status is not SessionStatus.WAITING_APPROVAL or session.pending_approval_id != approval.id:
            raise ValueError("session is not waiting for this approval")

        resolved = self.store.resolve_approval(approval_id, approved)
        session.status = SessionStatus.RUNNING
        session.pending_approval_id = None
        self._persist_session(session)

        if resolved.status == "approved":
            self.store.append_audit(session.id, "approval_approved", {"approval_id": resolved.id})
            action = parse_action(resolved.action_json)
            self._record_observation(session, "resumed_tool_result", self.dispatcher.dispatch_approved(action))
        else:
            self._record_observation(
                session,
                "approval_denied",
                Observation(False, FeedbackKind.APPROVAL_DENIED, message=resolved.reason),
                {"approval_id": resolved.id},
            )
        return self._continue(session)

    def _continue(self, session: SessionState) -> SessionState:
        while session.step_count < self.max_steps:
            try:
                raw_action = self.llm.complete(self._context(session.task, session.observations))
            except Exception as exc:
                observation = Observation(False, FeedbackKind.COMMAND_ERROR, message=f"provider failure: {exc}")
                self._record_observation(session, "provider_failure", observation)
                session.status = SessionStatus.FAILED
                self._persist_session(session)
                return session

            session.step_count += 1
            self._persist_session(session)
            try:
                action = parse_action(raw_action)
            except ValueError as exc:
                observation = Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))
                self._record_observation(session, "parser_error", observation, {"raw_action": raw_action})
                continue

            self.store.append_audit(session.id, "action_parsed", {"type": action.type.value, "payload": action.payload})
            if action.type is ActionType.FINISH:
                session.status = SessionStatus.FINISHED
                self._persist_session(session)
                self.store.append_audit(session.id, "finished", {"message": action.payload.get("message", "")})
                return session

            decision = self.guardrail.evaluate(action)
            self.store.append_audit(
                session.id,
                f"policy_{decision.decision.value}",
                {"reason": decision.reason, "risk_level": decision.risk_level},
            )
            if decision.decision is DecisionType.DENY:
                self._record_observation(
                    session,
                    "policy_denied",
                    Observation(False, FeedbackKind.POLICY_DENIED, message=decision.reason),
                )
                continue
            if decision.decision is DecisionType.NEEDS_APPROVAL:
                approval = self.store.create_approval(session.id, action.raw_source_text or "", decision.reason)
                session.status = SessionStatus.WAITING_APPROVAL
                session.pending_approval_id = approval.id
                self._persist_session(session)
                self.store.append_audit(session.id, "approval_requested", {"approval_id": approval.id, "reason": decision.reason})
                return session

            self._record_observation(session, "tool_result", self.dispatcher.dispatch(action))

        session.status = SessionStatus.MAX_STEPS
        self._persist_session(session)
        self.store.append_audit(session.id, "max_steps", {"max_steps": self.max_steps})
        return session

    def _context(self, task: str, observations: list[Observation]) -> dict[str, Any]:
        return {
            "task": task,
            "memory": [
                {"kind": entry.kind, "content": entry.content, "tags": entry.tags}
                for entry in self.store.list_memory(limit=10)
            ],
            "observations": [self._observation_payload(observation) for observation in observations],
        }

    def _record_observation(
        self,
        session: SessionState,
        event_type: str,
        observation: Observation,
        extra: dict[str, Any] | None = None,
    ) -> None:
        session.observations.append(observation)
        payload = self._observation_payload(observation)
        if extra:
            payload.update(extra)
        self.store.append_audit(session.id, event_type, payload)

    def _persist_session(self, session: SessionState) -> None:
        self.store.update_session(session)

    @staticmethod
    def _observation_payload(observation: Observation) -> dict[str, Any]:
        return {
            "success": observation.success,
            "feedback_kind": observation.feedback_kind.value,
            "message": observation.message,
            "stdout": observation.stdout,
            "stderr": observation.stderr,
            "metadata": observation.metadata,
        }
