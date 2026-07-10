from pathlib import Path

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.governance.policies import DecisionType


def test_deny_rm_rf_root(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "rm -rf /"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "destructive" in decision.reason


def test_require_approval_for_git_push(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "git push origin main"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


def test_deny_write_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"
    action = Action(ActionType.WRITE_FILE, {"path": str(outside), "content": "x"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "outside workspace" in decision.reason


def test_allow_write_inside_workspace(tmp_path: Path):
    action = Action(ActionType.WRITE_FILE, {"path": "src/app.py", "content": "print('ok')"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.ALLOW


def test_require_approval_to_modify_env_file(tmp_path: Path):
    action = Action(ActionType.WRITE_FILE, {"path": ".env", "content": "TOKEN=value"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


def test_require_approval_to_modify_uppercase_env_file(tmp_path: Path):
    action = Action(ActionType.WRITE_FILE, {"path": ".ENV", "content": "TOKEN=value"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


def test_require_approval_for_workspace_file_deletion(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "rm src/app.py"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


def test_deny_windows_root_deletion(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "Remove-Item -Recurse -Force C:\\"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "destructive" in decision.reason


def test_deny_quoted_destructive_root_targets(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": 'rm -rf "/"'})).decision == DecisionType.DENY
    assert (
        guardrail.evaluate(
            Action(ActionType.RUN_SHELL, {"command": 'Remove-Item -Recurse -Force "C:\\"'})
        ).decision
        == DecisionType.DENY
    )


def test_deny_shell_paths_outside_workspace(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("cat /etc/passwd", r"type C:\Windows\win.ini", "echo x > /tmp/x", "rm /tmp/x"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_allow_shell_command_without_path_side_effects(tmp_path: Path):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": "git status"}))

    assert decision.decision == DecisionType.ALLOW


def test_deny_destructive_compound_and_wrapper_commands(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in (
        "echo ok && rm -rf /",
        'sh -c "rm -rf /"',
        'bash -c "rm -rf /"',
        'powershell -Command "Remove-Item -Recurse -Force C:\\"',
    ):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_deny_destructive_commands_hidden_by_shell_wrappers(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in (
        'cmd /c "rd /s /q C:\\\\"',
        'cmd.exe /c "rd /s /q C:\\\\"',
        'powershell.exe -Command "Remove-Item -Recurse -Force C:\\\\"',
        "sudo rm -rf /",
    ):
        decision = guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

        assert decision.decision == DecisionType.DENY
        assert "destructive" in decision.reason


def test_split_single_ampersand_shell_commands(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "echo ok & rm src/app.py"})).decision
        == DecisionType.NEEDS_APPROVAL
    )
    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "echo ok & unknown-command"})).decision
        == DecisionType.NEEDS_APPROVAL
    )


def test_deny_root_relative_unc_and_home_relative_shell_paths(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in (r"type \Windows\win.ini", r"cat \\server\share\file", "cat ~/secret"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_deny_environment_expanded_shell_paths(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in (
        "cat $HOME",
        "cat $HOME/secret",
        "cat $TMP/secret",
        r"cat %TEMP%\secret",
        "echo x > $HOME/outside",
        r"cat $env:USERPROFILE\secret",
        "rm -rf $HOME",
    ):
        decision = guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

        assert decision.decision == DecisionType.DENY
        assert "outside workspace" in decision.reason


def test_deny_environment_variable_file_paths(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for action_type in (ActionType.READ_FILE, ActionType.WRITE_FILE):
        for path in ("$HOME", "$TMP/secret", r"%TEMP%\secret", "$env:HOME/secret"):
            decision = guardrail.evaluate(Action(action_type, {"path": path, "content": "x"}))

            assert decision.decision == DecisionType.DENY
            assert "outside workspace" in decision.reason


def test_require_approval_for_alternative_dependency_installs(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("pip3 install example", "python -m pip install example", "npm ci"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.NEEDS_APPROVAL


def test_require_approval_for_shell_env_file_write(tmp_path: Path):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": "echo TOKEN=x > .env"}))

    assert decision.decision == DecisionType.NEEDS_APPROVAL


def test_deny_relative_shell_paths_outside_workspace(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("cat ../outside.txt", "rm ../outside.txt", "echo x > ../outside.txt"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_deny_embedded_traversal_shell_paths_outside_workspace(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("cat src/../../outside", "echo x > build/../../outside", "rm tmp/../../outside"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_deny_sudo_options_before_destructive_command(tmp_path: Path):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": "sudo -u root rm -rf /"}))

    assert decision.decision == DecisionType.DENY
    assert "destructive" in decision.reason


def test_fail_closed_for_unknown_filesystem_capable_commands(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": 'python -c "open(\'/tmp/x\', \'w\')"'})).decision == DecisionType.DENY
    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "powershell Get-Content ../secret"})).decision
        == DecisionType.DENY
    )
    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": 'python -c "print(open(\'local\', \'w\'))"'})).decision
        == DecisionType.NEEDS_APPROVAL
    )
    assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "unknown-command"})).decision == DecisionType.NEEDS_APPROVAL


def test_require_approval_for_shell_env_file_writers(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("tee .env", "Set-Content .env value", "cp source .env"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.NEEDS_APPROVAL
