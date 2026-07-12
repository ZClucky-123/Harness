import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from guarded_harness.config.credentials import CredentialStore
from guarded_harness.config.loader import load_config
from guarded_harness.core.actions import Action, ActionType
from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.base import LLMProvider
from guarded_harness.llm.mock import MockLLM
from guarded_harness.llm.openai_compatible import OpenAICompatibleProvider
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.memory.store import SQLiteStore
from guarded_harness.governance.redaction import redact_secrets


_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))
_TEMPLATES.env.filters["pretty_json"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
_DEFAULT_BASE_URL = "https://njusehub.info/v1"
_DEFAULT_MODEL = "deepseek-v4-flash"
_VALID_MODES = {"mock", "live"}


def _credential_store() -> CredentialStore:
    return CredentialStore()


def _store_for(store_path: Path | None, workspace_root: Path | None) -> tuple[SQLiteStore, Path]:
    root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    if store_path is None:
        database_path = root / ".guarded-harness" / "state.sqlite3"
    else:
        database_path = Path(store_path).resolve()
        if workspace_root is None:
            root = database_path.parent
    return SQLiteStore(database_path, workspace_root=root), root


def _settings_path(root: Path) -> Path:
    return root / ".guarded-harness" / "provider.json"


def _default_provider_settings() -> dict[str, str]:
    config = load_config()
    return {
        "mode": "mock",
        "base_url": config.base_url if config.base_url != "https://api.openai.com/v1" else _DEFAULT_BASE_URL,
        "model": config.model if config.model != "gpt-4o-mini" else _DEFAULT_MODEL,
    }


def _load_provider_settings(root: Path) -> dict[str, str]:
    settings = _default_provider_settings()
    path = _settings_path(root)
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            settings.update(
                {
                    key: str(loaded[key])
                    for key in ("mode", "base_url", "model")
                    if key in loaded and loaded[key] is not None
                }
            )
    if settings["mode"] not in _VALID_MODES:
        settings["mode"] = "mock"
    return settings


def _save_provider_settings(root: Path, mode: str, base_url: str, model: str) -> dict[str, str]:
    settings = {
        "mode": mode if mode in _VALID_MODES else "mock",
        "base_url": base_url.strip() or _DEFAULT_BASE_URL,
        "model": model.strip() or _DEFAULT_MODEL,
    }
    path = _settings_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def _finish_loop(workspace_root: Path, store: SQLiteStore, message: str) -> AgentLoop:
    return AgentLoop.for_workspace(
        workspace_root,
        MockLLM([json.dumps({"type": "finish", "message": message})]),
        store,
    )


def _loop_for_provider(workspace_root: Path, store: SQLiteStore, provider: LLMProvider) -> AgentLoop:
    return AgentLoop.for_workspace(workspace_root, provider, store)


def _conversation_items(store: SQLiteStore, limit: int = 12) -> list[dict[str, object]]:
    return [_conversation_item(store, session) for session in store.list_sessions(limit)]


def _conversation_item(store: SQLiteStore, session) -> dict[str, object]:
    events = store.list_audit(session.id)
    return {
        "id": session.id,
        "task": redact_secrets(session.task),
        "status": session.status.value,
        "step_count": session.step_count,
        "summary": _session_summary(events),
        "trace_url": f"/sessions/{session.id}",
    }


def _session_summary(events) -> str:
    for event in reversed(events):
        if event.event_type == "finished":
            message = event.payload.get("message", "finished")
            return str(redact_secrets(message))
        if event.event_type == "approval_requested":
            return "waiting for human approval"
        if event.event_type == "guardrail_denied":
            return str(redact_secrets(event.payload.get("reason", "guardrail denied the action")))
        if event.event_type == "parser_error":
            return "model response could not be parsed as an action"
        if event.event_type == "max_steps":
            return "stopped after reaching max steps"
    return "session started"


def create_app(store_path: Path | None = None, workspace_root: Path | None = None) -> FastAPI:
    """Create a local, deterministic WebUI backed by a workspace-local store."""
    store, root = _store_for(store_path, workspace_root)
    app = FastAPI(title="Guarded Harness")
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    def index(request: Request):
        settings = _load_provider_settings(root)
        credential_configured = _credential_store().status()
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Chat Workspace",
                "settings": settings,
                "credential_configured": credential_configured,
                "conversation_items": _conversation_items(store),
            },
        )

    @app.get("/settings")
    def settings(request: Request):
        return _TEMPLATES.TemplateResponse(
            request,
            "settings.html",
            {
                "title": "Provider Settings",
                "settings": _load_provider_settings(root),
                "credential_configured": _credential_store().status(),
            },
        )

    @app.post("/settings")
    def save_settings(
        mode: str = Form("mock"),
        base_url: str = Form(_DEFAULT_BASE_URL),
        model: str = Form(_DEFAULT_MODEL),
        api_key: str = Form(""),
        save_api_key: str | None = Form(None),
    ):
        _save_provider_settings(root, mode, base_url, model)
        if api_key.strip() and save_api_key:
            _credential_store().set_key(api_key.strip())
        return RedirectResponse(url="/", status_code=303)

    @app.post("/sessions")
    def start_session(
        task: str = Form(...),
        mode: str | None = Form(None),
        base_url: str | None = Form(None),
        model: str | None = Form(None),
        api_key: str = Form(""),
        save_api_key: str | None = Form(None),
    ):
        settings = _load_provider_settings(root)
        selected_mode = mode or settings["mode"]
        selected_base_url = base_url or settings["base_url"]
        selected_model = model or settings["model"]
        if selected_mode == "live":
            provider = _live_provider(selected_base_url, selected_model, api_key, save_api_key)
            session = _loop_for_provider(root, store, provider).run(task)
        else:
            session = _finish_loop(root, store, "mock run completed").run(task)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/sessions/{session_id}")
    def show_session(request: Request, session_id: str):
        try:
            session = store.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        return _TEMPLATES.TemplateResponse(
            request,
            "session.html",
            {
                "title": "Session",
                "session": session,
                "display_task": redact_secrets(session.task),
                "events": store.list_audit(session_id),
            },
        )

    @app.get("/approvals")
    def approvals(request: Request):
        unfinished = store.list_unfinished_approvals()
        grouped = {
            status: [approval for approval in unfinished if approval.status == status]
            for status in ("pending", "executing", "failed")
        }
        return _TEMPLATES.TemplateResponse(
            request,
            "approvals.html",
            {"title": "Approvals", "approvals": unfinished, "approval_groups": grouped},
        )

    @app.get("/guardrail")
    def guardrail_demo(request: Request):
        return _TEMPLATES.TemplateResponse(
            request,
            "guardrail.html",
            {"title": "Guardrail Demo", "samples": _guardrail_samples(), "result": None},
        )

    @app.post("/guardrail")
    def evaluate_guardrail(request: Request, sample: str = Form(...)):
        samples = _guardrail_samples()
        action = samples.get(sample, samples["rm_root"])["action"]
        decision = Guardrail(root).evaluate(action)
        return _TEMPLATES.TemplateResponse(
            request,
            "guardrail.html",
            {
                "title": "Guardrail Demo",
                "samples": samples,
                "result": {"sample": sample, "decision": decision},
            },
        )

    @app.post("/approvals/{approval_id}/approve")
    def approve(approval_id: str):
        return _resume_approval(store, approval_id, approved=True)

    @app.post("/approvals/{approval_id}/deny")
    def deny(approval_id: str):
        return _resume_approval(store, approval_id, approved=False)

    @app.post("/approvals/{approval_id}/mark-failed")
    def mark_failed(approval_id: str, reason: str = Form(...)):
        try:
            approval = store.mark_approval_failed(approval_id, reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="approval not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(url=f"/sessions/{approval.session_id}", status_code=303)

    return app


def _live_provider(base_url: str, model: str, api_key: str, save_api_key: str | None) -> OpenAICompatibleProvider:
    credentials = _credential_store()
    resolved_key = api_key.strip() or credentials.get_key()
    if resolved_key is None:
        raise HTTPException(status_code=400, detail="API key is required for live mode")
    if api_key.strip() and save_api_key:
        credentials.set_key(api_key.strip())
    config = load_config()
    return OpenAICompatibleProvider(
        base_url.strip() or _DEFAULT_BASE_URL,
        model.strip() or _DEFAULT_MODEL,
        resolved_key,
        config.timeout,
    )


def _guardrail_samples() -> dict[str, dict[str, object]]:
    return {
        "rm_root": {
            "label": "Try rm -rf /",
            "action": Action(ActionType.RUN_SHELL, {"command": "rm -rf /"}),
        },
        "write_env": {
            "label": "Try write .env",
            "action": Action(ActionType.WRITE_FILE, {"path": ".env", "content": "MODE=prod"}),
        },
        "git_push": {
            "label": "Try git push",
            "action": Action(ActionType.RUN_SHELL, {"command": "git push origin main"}),
        },
        "safe_status": {
            "label": "Try git status",
            "action": Action(ActionType.RUN_SHELL, {"command": "git status"}),
        },
    }


def _resume_approval(store: SQLiteStore, approval_id: str, approved: bool) -> RedirectResponse:
    try:
        approval = store.get_approval(approval_id)
        session = store.get_session(approval.session_id)
        resumed = AgentLoop.for_workspace(session.workspace, MockLLM([]), store).resume_after_approval(
            approval_id,
            approved,
            continue_after_resolution=False,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/sessions/{resumed.id}", status_code=303)
