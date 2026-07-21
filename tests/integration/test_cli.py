import json

from typer.testing import CliRunner
import httpx

from guarded_harness.cli import app
from guarded_harness.config.credentials import CredentialStore, InMemoryKeyring
from guarded_harness.core.sessions import SessionStatus
from guarded_harness.memory.store import SQLiteStore


runner = CliRunner()


def test_guardrail_demo_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["demo", "guardrail"])

    assert result.exit_code == 0
    assert "policy_denied" in result.stdout


def test_feedback_demo_command_reports_real_command_error_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["demo", "feedback"])

    assert result.exit_code == 0
    assert "tool_result" in result.stdout
    assert "feedback_kind=command_error" in result.stdout
    assert "finished: changed action after command_error" in result.stdout


def test_hitl_demo_command_uses_temporary_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["demo", "hitl"])

    assert result.exit_code == 0
    assert "waiting_approval" in result.stdout
    assert "approval_approved" in result.stdout
    assert not (tmp_path / ".env").exists()


def test_credentials_status_never_prints_configured_key(monkeypatch):
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    credentials.set_key("sk-test-secret-value")
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)

    result = runner.invoke(app, ["credentials", "status"])

    assert result.exit_code == 0
    assert "configured" in result.stdout
    assert "sk-test-secret-value" not in result.stdout


def test_credentials_set_never_prints_supplied_key(monkeypatch):
    supplied_key = "sk-supplied-secret-value"
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)

    result = runner.invoke(app, ["credentials", "set"], input=f"{supplied_key}\n{supplied_key}\n")

    assert result.exit_code == 0
    assert credentials.get_key() == supplied_key
    assert "credential stored" in result.stdout
    assert supplied_key not in result.stdout


def test_credentials_clear_never_prints_supplied_key(monkeypatch):
    supplied_key = "sk-supplied-secret-value"
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    credentials.set_key(supplied_key)
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)

    result = runner.invoke(app, ["credentials", "clear"])

    assert result.exit_code == 0
    assert credentials.get_key() is None
    assert "credential cleared" in result.stdout
    assert supplied_key not in result.stdout


def test_config_init_creates_provider_file_for_new_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["config", "init"])

    provider_file = tmp_path / ".guarded-harness" / "provider.json"
    assert result.exit_code == 0
    assert provider_file.exists()
    assert json.loads(provider_file.read_text(encoding="utf-8")) == {
        "mode": "live",
        "base_url": "https://njusehub.info/v1",
        "model": "deepseek-v4-flash",
        "timeout": 30,
    }
    assert "provider config written" in result.stdout
    assert "API key" in result.stdout


def test_config_init_refuses_to_overwrite_existing_provider_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider_dir = tmp_path / ".guarded-harness"
    provider_dir.mkdir()
    provider_file = provider_dir / "provider.json"
    provider_file.write_text('{"mode":"mock","model":"custom"}', encoding="utf-8")

    result = runner.invoke(app, ["config", "init"])

    assert result.exit_code != 0
    assert json.loads(provider_file.read_text(encoding="utf-8")) == {"mode": "mock", "model": "custom"}
    assert "already exists" in result.stdout


def test_config_init_force_overwrites_existing_provider_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    provider_dir = tmp_path / ".guarded-harness"
    provider_dir.mkdir()
    provider_file = provider_dir / "provider.json"
    provider_file.write_text('{"mode":"mock","model":"custom"}', encoding="utf-8")

    result = runner.invoke(app, ["config", "init", "--force"])

    assert result.exit_code == 0
    assert json.loads(provider_file.read_text(encoding="utf-8"))["model"] == "deepseek-v4-flash"


def test_live_run_uses_configured_provider_and_finishes(tmp_path, monkeypatch):
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    credentials.set_key("live-secret")

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        request = httpx.Request("POST", args[0])
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": '```json\n{"type":"finish","message":"2"}\n```'}}]},
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GUARDED_HARNESS_BASE_URL", "https://njusehub.info/v1")
    monkeypatch.setenv("GUARDED_HARNESS_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    result = runner.invoke(app, ["run", "回复1+1+?", "--live"])

    assert result.exit_code == 0
    assert "finished: 2" in result.stdout
    assert "status=finished" in result.stdout
    assert calls[0][0][0] == "https://njusehub.info/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer live-secret"
    assert calls[0][1]["json"]["model"] == "deepseek-v4-flash"
    assert "live-secret" not in result.stdout


def test_live_run_uses_provider_config_file_when_environment_is_unset(tmp_path, monkeypatch):
    credentials = CredentialStore(keyring_backend=InMemoryKeyring())
    credentials.set_key("file-config-secret")
    config_dir = tmp_path / ".guarded-harness"
    config_dir.mkdir()
    (config_dir / "provider.json").write_text(
        '{"mode":"live","base_url":"https://file-config.example/v1","model":"file-model","timeout":17}',
        encoding="utf-8",
    )
    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        request = httpx.Request("POST", args[0])
        return httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": '{"type":"finish","message":"from file config"}'}}]},
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GUARDED_HARNESS_BASE_URL", raising=False)
    monkeypatch.delenv("GUARDED_HARNESS_MODEL", raising=False)
    monkeypatch.setattr("guarded_harness.cli._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.llm.openai_compatible.httpx.post", fake_post)

    result = runner.invoke(app, ["run", "use shared provider config"])

    assert result.exit_code == 0
    assert "finished: from file config" in result.stdout
    assert calls[0][0][0] == "https://file-config.example/v1/chat/completions"
    assert calls[0][1]["json"]["model"] == "file-model"
    assert calls[0][1]["timeout"] == 17
    assert "file-config-secret" not in result.stdout


def test_run_without_task_starts_interactive_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["run"], input="summarize this repo\n:mode\n:approvals\n:exit\n")

    assert result.exit_code == 0
    assert "Guarded Harness interactive mode" in result.stdout
    assert "finished: mock run completed" in result.stdout
    assert "mode: mock" in result.stdout
    assert "no pending approvals" in result.stdout


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


def test_approvals_list_prints_redacted_action(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    import sqlite3

    with sqlite3.connect(store.db_path) as db:
        db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-cli-secret",
                session.id,
                '{"type":"write_file","path":".env","content":"sk-cli-secret Bearer cli-bearer password=hunter2"}',
                "approval required",
                "pending",
                "2026-07-11T00:00:00+00:00",
                None,
            ),
        )
    monkeypatch.setattr("guarded_harness.cli._store", lambda: store)

    result = runner.invoke(app, ["approvals", "list"])

    assert result.exit_code == 0
    assert "[REDACTED]" in result.stdout
    assert "sk-cli-secret" not in result.stdout
    assert "cli-bearer" not in result.stdout
    assert "hunter2" not in result.stdout


def test_approvals_mark_failed_recovers_executing_approval(tmp_path, monkeypatch):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    approval = store.create_approval(session.id, '{"type":"write_file","path":".env","content":"ok"}', "approval")
    session.status = SessionStatus.WAITING_APPROVAL
    session.pending_approval_id = approval.id
    store.update_session(session)
    store.begin_approval_resolution(approval.id, approved=True)
    monkeypatch.setattr("guarded_harness.cli._store", lambda: store)

    result = runner.invoke(app, ["approvals", "mark-failed", approval.id, "crashed worker"])

    assert result.exit_code == 0
    assert store.get_approval(approval.id).status == "failed"
    assert "marked failed" in result.stdout
