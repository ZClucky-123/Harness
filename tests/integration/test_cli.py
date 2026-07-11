from typer.testing import CliRunner

from guarded_harness.cli import app
from guarded_harness.config.credentials import CredentialStore, InMemoryKeyring


runner = CliRunner()


def test_guardrail_demo_command():
    result = runner.invoke(app, ["demo", "guardrail"])

    assert result.exit_code == 0
    assert "policy_denied" in result.stdout


def test_feedback_demo_command():
    result = runner.invoke(app, ["demo", "feedback"])

    assert result.exit_code == 0
    assert "command_error" in result.stdout
    assert "changed action" in result.stdout


def test_hitl_demo_command():
    result = runner.invoke(app, ["demo", "hitl"])

    assert result.exit_code == 0
    assert "waiting_approval" in result.stdout
    assert "approval_approved" in result.stdout


def test_credentials_status_never_prints_configured_key(monkeypatch):
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    credentials.set_key("sk-test-secret-value")
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)

    result = runner.invoke(app, ["credentials", "status"])

    assert result.exit_code == 0
    assert "configured" in result.stdout
    assert "sk-test-secret-value" not in result.stdout


def test_approvals_list_and_approve_resume_demo_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    waiting = runner.invoke(app, ["demo", "hitl", "--wait-only"])
    approval_id = waiting.stdout.split("approval_id=")[1].splitlines()[0]

    listed = runner.invoke(app, ["approvals", "list"])
    approved = runner.invoke(app, ["approvals", "approve", approval_id])

    assert listed.exit_code == 0
    assert approval_id in listed.stdout
    assert approved.exit_code == 0
    assert "finished" in approved.stdout
