import json
import shutil
import tempfile
from pathlib import Path

import typer

from guarded_harness.config.credentials import CredentialStore
from guarded_harness.config.loader import load_config
from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.llm.openai_compatible import OpenAICompatibleProvider
from guarded_harness.memory.store import SQLiteStore


app = typer.Typer(help="Guarded local coding-agent harness.")
demo_app = typer.Typer(help="Run deterministic mechanism demonstrations.")
approvals_app = typer.Typer(help="Inspect and resolve pending approvals.")
credentials_app = typer.Typer(help="Manage the API credential in the OS keyring.")
config_app = typer.Typer(help="Initialize and inspect local provider configuration.")
app.add_typer(demo_app, name="demo")
app.add_typer(approvals_app, name="approvals")
app.add_typer(credentials_app, name="credentials")
app.add_typer(config_app, name="config")


DEFAULT_PROVIDER_CONFIG = {
    "mode": "live",
    "base_url": "https://njusehub.info/v1",
    "model": "deepseek-v4-flash",
    "timeout": 30,
}


def _workspace() -> Path:
    return Path.cwd().resolve()


def _store() -> SQLiteStore:
    root = _workspace()
    return SQLiteStore(root / ".guarded-harness" / "state.sqlite3", workspace_root=root)


def _credential_store() -> CredentialStore:
    return CredentialStore()


def _print_events(loop: AgentLoop, session_id: str) -> None:
    for event in loop.store.list_audit(session_id):
        typer.echo(event.event_type)
        feedback_kind = event.payload.get("feedback_kind")
        if feedback_kind:
            typer.echo(f"feedback_kind={feedback_kind}")
        if event.event_type == "finished":
            typer.echo(f"finished: {event.payload.get('message', '')}")


def _print_approvals() -> None:
    approvals = _store().list_unfinished_approvals()
    if not approvals:
        typer.echo("no pending approvals")
        return
    for approval in approvals:
        typer.echo(f"{approval.id} {approval.status}: {approval.redacted_reason}")
        typer.echo(approval.redacted_action_json)


def _demo_loop(
    responses: list[str],
    workspace: Path | None = None,
    store: SQLiteStore | None = None,
) -> AgentLoop:
    root = workspace or _workspace()
    return AgentLoop.for_workspace(root, MockLLM(responses), store or _store(), max_steps=len(responses) + 1)


@demo_app.command("guardrail")
def demo_guardrail() -> None:
    loop = _demo_loop([
        json.dumps({"type": "run_shell", "command": "rm -rf /"}),
        json.dumps({"type": "finish", "message": "stopped by policy"}),
    ])
    session = loop.run("Demonstrate guardrail rejection")
    _print_events(loop, session.id)
    typer.echo(f"status={session.status.value}")


@demo_app.command("feedback")
def demo_feedback() -> None:
    loop = _demo_loop([
        json.dumps({"type": "run_shell", "command": "git status --bad-option"}),
        json.dumps({"type": "finish", "message": "changed action after command_error"}),
    ])
    session = loop.run("Demonstrate feedback-driven recovery")
    _print_events(loop, session.id)
    typer.echo(f"status={session.status.value}")


@demo_app.command("hitl")
def demo_hitl(wait_only: bool = typer.Option(False, "--wait-only", help="Leave the demo approval pending.")) -> None:
    demo_workspace = Path(tempfile.mkdtemp(prefix="guarded-harness-hitl-"))
    loop = _demo_loop([
        json.dumps({"type": "write_file", "path": ".env", "content": "HARNESS_DEMO=approved\n"}),
        json.dumps({"type": "finish", "message": "approved action completed"}),
    ], workspace=demo_workspace)
    waiting = loop.run("Demonstrate human approval")
    typer.echo(f"status={waiting.status.value}")
    approval_id = waiting.pending_approval_id
    if approval_id is None:
        raise typer.Exit(code=1)
    typer.echo(f"approval_id={approval_id}")
    if wait_only:
        return
    try:
        session = loop.resume_after_approval(approval_id, approved=True)
        _print_events(loop, session.id)
        typer.echo(f"status={session.status.value}")
    finally:
        shutil.rmtree(demo_workspace, ignore_errors=True)


@approvals_app.command("list")
def list_approvals() -> None:
    _print_approvals()


def _resume_approval(approval_id: str, approved: bool) -> None:
    store = _store()
    approval = store.get_approval(approval_id)
    session = store.get_session(approval.session_id)
    loop = AgentLoop.for_workspace(
        session.workspace or _workspace(),
        MockLLM([]),
        store,
    )
    resumed = loop.resume_after_approval(
        approval_id,
        approved=approved,
        continue_after_resolution=False,
    )
    _print_events(loop, resumed.id)
    typer.echo(f"status={resumed.status.value}")


@approvals_app.command("approve")
def approve_approval(approval_id: str) -> None:
    _resume_approval(approval_id, approved=True)


@approvals_app.command("deny")
def deny_approval(approval_id: str) -> None:
    _resume_approval(approval_id, approved=False)


@approvals_app.command("mark-failed")
def mark_approval_failed(approval_id: str, reason: str) -> None:
    try:
        approval = _store().mark_approval_failed(approval_id, reason)
    except KeyError as exc:
        raise typer.BadParameter("approval not found") from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"approval {approval.id} marked failed")


@credentials_app.command("set")
def set_credential() -> None:
    key = typer.prompt("API key", hide_input=True, confirmation_prompt=True)
    _credential_store().set_key(key)
    typer.echo("credential stored")


@credentials_app.command("status")
def credential_status() -> None:
    state = "configured" if _credential_store().status() else "not configured"
    typer.echo(f"credential status: {state}")


@credentials_app.command("clear")
def clear_credential() -> None:
    _credential_store().clear_key()
    typer.echo("credential cleared")


@config_app.command("init")
def init_config(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing provider config file."),
) -> None:
    provider_file = _workspace() / ".guarded-harness" / "provider.json"
    if provider_file.exists() and not force:
        typer.echo(f"provider config already exists: {provider_file}")
        raise typer.Exit(code=1)
    provider_file.parent.mkdir(parents=True, exist_ok=True)
    provider_file.write_text(json.dumps(DEFAULT_PROVIDER_CONFIG, indent=2) + "\n", encoding="utf-8")
    typer.echo(f"provider config written: {provider_file}")
    typer.echo("API key is not stored in this file; run 'harness credentials set' to save it in the OS keyring.")


@app.command("run")
def run_task(
    task: str | None = typer.Argument(None),
    live: bool = typer.Option(False, "--live", help="Use the configured OpenAI-compatible provider."),
) -> None:
    if task is None:
        _interactive_run(force_live=live)
        return
    _run_single_task(task, force_live=live)


def _run_single_task(task: str, force_live: bool = False) -> None:
    store = _store()
    config = load_config(workspace_root=_workspace())
    llm = _llm_for_config(config, force_live=force_live)
    session = AgentLoop.for_workspace(_workspace(), llm, store).run(task)
    _print_events(AgentLoop.for_workspace(_workspace(), MockLLM([]), store), session.id)
    typer.echo(f"status={session.status.value}")


def _llm_for_config(config, force_live: bool = False):
    use_live = force_live or config.mode == "live"
    if not use_live:
        return MockLLM([json.dumps({"type": "finish", "message": "mock run completed"})])
    key = _credential_store().get_key() or config.api_key
    if key is None:
        raise typer.BadParameter("no credential configured; run 'harness credentials set' first")
    return OpenAICompatibleProvider(config.base_url, config.model, key, config.timeout)


def _interactive_run(force_live: bool = False) -> None:
    config = load_config(workspace_root=_workspace())
    mode = "live" if force_live or config.mode == "live" else "mock"
    typer.echo("Guarded Harness interactive mode")
    typer.echo(f"mode: {mode} | model: {config.model}")
    typer.echo("Type :help for commands, :exit to quit.")
    while True:
        try:
            line = typer.prompt(">")
        except (EOFError, KeyboardInterrupt):
            typer.echo()
            break
        task = line.strip()
        if not task:
            continue
        if task in {":exit", ":quit"}:
            break
        if task == ":help":
            typer.echo(":help, :mode, :approvals, :exit, :quit")
            continue
        if task == ":mode":
            config = load_config(workspace_root=_workspace())
            mode = "live" if force_live or config.mode == "live" else "mock"
            typer.echo(f"mode: {mode} | model: {config.model}")
            continue
        if task == ":approvals":
            _print_approvals()
            continue
        _run_single_task(task, force_live=force_live)


@app.command("serve")
def serve() -> None:
    import uvicorn

    uvicorn.run("guarded_harness.web.app:create_app", factory=True, host="127.0.0.1", port=8000)
