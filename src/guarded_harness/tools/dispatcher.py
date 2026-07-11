from pathlib import Path

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.core.observations import FeedbackKind, Observation
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.governance.policies import DecisionType
from guarded_harness.governance.redaction import contains_secret
from guarded_harness.governance.shell_command import forbidden_interpreter_reason
from guarded_harness.tools.filesystem import read_file, write_file
from guarded_harness.tools.shell import run_shell
from guarded_harness.tools.tests import run_tests


class ToolDispatcher:
    def __init__(self, workspace_root: Path, test_command: list[str], guardrail: Guardrail | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        self.test_command = test_command
        self.guardrail = guardrail or Guardrail(self.workspace_root)

    def dispatch(self, action: Action) -> Observation:
        try:
            secret_observation = self._secret_observation(action)
            if secret_observation is not None:
                return secret_observation
            policy_observation = self._policy_observation(action)
            if policy_observation is not None:
                return policy_observation
            return self._execute(action)
        except Exception as exc:
            return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))

    def dispatch_approved(self, action: Action) -> Observation:
        try:
            secret_observation = self._secret_observation(action)
            if secret_observation is not None:
                return secret_observation
            if action.type is ActionType.RUN_SHELL:
                reason = forbidden_interpreter_reason(str(action.payload.get("command", "")))
                if reason is not None:
                    return Observation(False, FeedbackKind.POLICY_DENIED, message=reason)
            decision = self.guardrail.evaluate(action)
            if decision.decision is not DecisionType.NEEDS_APPROVAL:
                return Observation(False, FeedbackKind.POLICY_DENIED, message="action is not approval-gated")
            return self._execute(action)
        except Exception as exc:
            return Observation(False, FeedbackKind.COMMAND_ERROR, message=str(exc))

    def _execute(self, action: Action) -> Observation:
        if action.type is ActionType.READ_FILE:
            return read_file(self.workspace_root, action.payload.get("path"))
        if action.type is ActionType.WRITE_FILE:
            return write_file(
                self.workspace_root,
                action.payload.get("path"),
                action.payload.get("content"),
            )
        if action.type is ActionType.RUN_SHELL:
            return run_shell(self.workspace_root, action.payload.get("command"))
        if action.type is ActionType.RUN_TESTS:
            return run_tests(self.workspace_root, self.test_command)
        return Observation(False, FeedbackKind.COMMAND_ERROR, message="action is not a tool action")

    def _policy_observation(self, action: Action) -> Observation | None:
        decision = self.guardrail.evaluate(action)
        if decision.decision is DecisionType.DENY:
            return Observation(False, FeedbackKind.POLICY_DENIED, message=decision.reason)
        if decision.decision is DecisionType.NEEDS_APPROVAL:
            return Observation(False, FeedbackKind.APPROVAL_DENIED, message=f"approval required: {decision.reason}")
        return None

    def _secret_observation(self, action: Action) -> Observation | None:
        if contains_secret(action.payload):
            return Observation(
                False,
                FeedbackKind.POLICY_DENIED,
                message="action payload contains a secret; use keyring/secret reference instead",
            )
        return None
