from pathlib import Path

import pytest

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.governance.policies import DecisionType


def test_deny_rm_rf_root(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "rm -rf /"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "destructive" in decision.reason


def test_deny_git_push(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "git push origin main"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "cannot be approved" in decision.reason


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
    action = Action(ActionType.WRITE_FILE, {"path": ".env", "content": "MODE=local"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


def test_require_approval_to_modify_uppercase_env_file(tmp_path: Path):
    action = Action(ActionType.WRITE_FILE, {"path": ".ENV", "content": "MODE=local"})

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


def test_deny_alternative_dependency_installs(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("pip3 install example", "python -m pip install example", "npm ci"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.DENY


def test_require_approval_for_shell_env_file_write(tmp_path: Path):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": "echo MODE=local > .env"}))

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
        == DecisionType.DENY
    )
    assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "unknown-command"})).decision == DecisionType.DENY


@pytest.mark.parametrize(
    "command",
    [
        'python -c "from pathlib import Path; Path.home().joinpath(\'x\').write_text(\'bad\')"',
        'python3 -c "print(\'hello\')"',
        'python3.11 -c "print(\'hello\')"',
        'env python -c "print(\'hello\')"',
        'env -u TOKEN python -c "print(\'hello\')"',
        'sh -c "echo hello"',
        'bash -c "echo hello"',
        "bash script.sh",
        'powershell -Command "Get-Content README.md"',
        'pwsh -Command "Get-Content README.md"',
        'cmd /c "type README.md"',
    ],
)
def test_deny_inline_interpreters_and_shell_wrappers_even_when_payload_looks_safe(tmp_path: Path, command: str):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

    assert decision.decision == DecisionType.DENY
    assert "interpreter" in decision.reason or "wrapper" in decision.reason


@pytest.mark.parametrize(
    "command",
    [
        "python workspace_script.py",
        "python3 workspace_script.py",
        "py workspace_script.py",
        "node workspace_script.js",
        "ruby workspace_script.rb",
        "perl workspace_script.pl",
        "php workspace_script.php",
        "lua workspace_script.lua",
        "npm test",
        "yarn test",
        "pnpm test",
        "npx pytest",
        "cargo test",
        "make",
        "workspace_script.py",
        "git push origin main",
    ],
)
def test_deny_arbitrary_code_and_build_entrypoints(tmp_path: Path, command: str):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

    assert decision.decision == DecisionType.DENY
    assert "cannot be approved" in decision.reason


def test_safe_python_module_and_regular_argv_remain_supported(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "python -m compileall -q src"})).decision
        == DecisionType.ALLOW
    )
    assert (
        guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "git status --bad-option"})).decision
        == DecisionType.ALLOW
    )
    assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": "pytest -q tests"})).decision == DecisionType.ALLOW


def test_pytest_rejects_non_allowlisted_plugin_argv(tmp_path: Path):
    decision = Guardrail(tmp_path).evaluate(
        Action(ActionType.RUN_SHELL, {"command": "pytest -p workspace_plugin tests"})
    )

    assert decision.decision == DecisionType.DENY


def test_deny_external_helper_options_for_safe_shell_commands(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in (
        "rg --pre=./workspace-script pattern",
        "rg --pre ./workspace-script pattern",
        "git diff --ext-diff",
        "git -c core.pager=./workspace-script diff",
    ):
        decision = guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

        assert decision.decision == DecisionType.DENY


def test_deny_secret_bearing_action_payloads(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for action in (
        Action(ActionType.WRITE_FILE, {"path": "out.txt", "content": "ghp_abcdefghijklmnopqrstuvwxyz123456"}),
        Action(ActionType.FINISH, {"message": "AKIAABCDEFGHIJKLMNOP"}),
        Action(ActionType.RUN_SHELL, {"command": "echo AIzaabcdefghijklmnopqrstuvwxyz1234567"}),
    ):
        decision = guardrail.evaluate(action)

        assert decision.decision == DecisionType.DENY


def test_require_approval_for_shell_env_file_writers(tmp_path: Path):
    guardrail = Guardrail(tmp_path)

    for command in ("tee .env", "Set-Content .env value", "cp source .env"):
        assert guardrail.evaluate(Action(ActionType.RUN_SHELL, {"command": command})).decision == DecisionType.NEEDS_APPROVAL


@pytest.mark.parametrize(
    "command",
    [
        "echo $(rm file)",
        "echo `rm file`",
        "echo safe\nrm file",
        "echo safe > output.txt",
        "echo safe | cat",
        "echo safe && git status",
    ],
)
def test_shell_control_syntax_is_never_allowlisted(tmp_path: Path, command: str):
    decision = Guardrail(tmp_path).evaluate(Action(ActionType.RUN_SHELL, {"command": command}))

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "shell syntax" in decision.reason


def test_deny_shell_path_through_symlink_outside_workspace(tmp_path: Path):
    outside = tmp_path.parent / "outside-shell-target"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "linked-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    decision = Guardrail(tmp_path).evaluate(
        Action(ActionType.RUN_SHELL, {"command": "cat linked-outside/secret.txt"})
    )

    assert decision.decision == DecisionType.DENY
    assert "outside workspace" in decision.reason
