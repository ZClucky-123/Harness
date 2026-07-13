from pathlib import Path

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.governance.redaction import contains_secret
from guarded_harness.governance.policies import (
    PolicyDecision,
    allow,
    classify_shell_command,
    deny,
    has_environment_reference,
    needs_approval,
)


class Guardrail:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root).resolve()

    def evaluate(self, action: Action) -> PolicyDecision:
        if contains_secret(action.payload):
            return deny("action payload contains a secret; use keyring/secret reference instead")
        if action.type is ActionType.RUN_SHELL:
            return classify_shell_command(str(action.payload.get("command", "")), self.workspace_root)
        if action.type in {ActionType.READ_FILE, ActionType.WRITE_FILE}:
            return self._evaluate_file_action(action)
        return allow()

    def _evaluate_file_action(self, action: Action) -> PolicyDecision:
        path = self._resolve_path(action.payload.get("path"))
        if path is None or not self._is_within_workspace(path):
            return deny("file path is outside workspace")
        if action.type is ActionType.WRITE_FILE and path.name.lower().startswith(".env"):
            return needs_approval("modifying an environment file requires approval")
        return allow()

    def _resolve_path(self, value: object) -> Path | None:
        if not isinstance(value, str) or not value:
            return None
        if has_environment_reference(value):
            return None
        path = Path(value)
        return (path if path.is_absolute() else self.workspace_root / path).resolve()

    def _is_within_workspace(self, path: Path) -> bool:
        try:
            path.relative_to(self.workspace_root)
        except ValueError:
            return False
        return True
