import html
import json
from pathlib import Path
import re

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from guarded_harness.config.credentials import CredentialStore
from guarded_harness.config.loader import load_config
from guarded_harness.core.actions import Action, ActionType, parse_action
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
_TEMPLATES.env.filters["markdown"] = lambda value: Markup(_render_markdown(str(value)))
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


def _record_provider_settings(store: SQLiteStore, session_id: str, settings: dict[str, str]) -> None:
    store.append_audit(
        session_id,
        "provider_configured",
        {
            "mode": settings["mode"],
            "base_url": settings["base_url"],
            "model": settings["model"],
        },
    )


def _provider_settings_for_session(store: SQLiteStore, session_id: str) -> dict[str, str] | None:
    for event in reversed(store.list_audit(session_id)):
        if event.event_type != "provider_configured":
            continue
        payload = event.payload
        mode = payload.get("mode")
        base_url = payload.get("base_url")
        model = payload.get("model")
        if isinstance(mode, str) and isinstance(base_url, str) and isinstance(model, str):
            return {"mode": mode, "base_url": base_url, "model": model}
    return None


def _provider_status(settings: dict[str, str], credential_configured: bool) -> str:
    mode_label = "live" if settings["mode"] == "live" else "mock"
    key_label = "key configured" if credential_configured else "key missing"
    return f"{mode_label} · {settings['model']} · {key_label}"


def _status_label(status: str) -> str:
    return {
        "running": "running",
        "waiting_approval": "waiting approval",
        "finished": "finished",
        "failed": "failed",
        "max_steps": "max steps",
    }.get(status, status)


def _pending_approval_count(store: SQLiteStore) -> int:
    return len(store.list_pending_approvals())


def _sidebar_groups(items: list[dict[str, object]], current_session_id: str | None = None) -> list[dict[str, object]]:
    grouped_items = []
    for item in items:
        copy = dict(item)
        copy["active"] = item["id"] == current_session_id
        grouped_items.append(copy)
    return [{"label": "Today", "sessions": grouped_items}] if grouped_items else []


def _conversation_items(store: SQLiteStore, limit: int = 12) -> list[dict[str, object]]:
    return [_conversation_item(store, session) for session in store.list_sessions(limit)]


def _step_label(step_count: int) -> str:
    unit = "step" if step_count == 1 else "steps"
    return f"{step_count} {unit}"


def _conversation_item(store: SQLiteStore, session) -> dict[str, object]:
    events = store.list_audit(session.id)
    item = {
        "id": session.id,
        "task": redact_secrets(session.task),
        "status": session.status.value,
        "status_label": _status_label(session.status.value),
        "step_count": session.step_count,
        "step_label": _step_label(session.step_count),
        "summary": _session_summary(events),
        "trace_url": f"/sessions/{session.id}",
    }
    if session.pending_approval_id:
        try:
            approval = store.get_approval(session.pending_approval_id)
            item["approval"] = _approval_view(store, approval)
        except KeyError:
            item["approval"] = None
    else:
        item["approval"] = None
    return item


def _approval_view(store: SQLiteStore, approval) -> dict[str, object]:
    summary = _approval_summary(approval.action_json)
    session = store.get_session(approval.session_id)
    failure_reason = _approval_failure_reason(store, approval)
    approval_state, execution_state, state_title = _approval_state_labels(approval.status)
    return {
        "id": approval.id,
        "session_id": approval.session_id,
        "session_task": redact_secrets(session.task),
        "trace_url": f"/sessions/{approval.session_id}",
        "status": approval.status,
        "state_title": state_title,
        "approval_state": approval_state,
        "execution_state": execution_state,
        "reason": approval.redacted_reason,
        "display_reason": failure_reason or approval.redacted_reason,
        "action_json": approval.redacted_action_json,
        **summary,
    }


def _approval_state_labels(status: str) -> tuple[str, str, str]:
    if status == "pending":
        return "pending", "not started", "Pending approval"
    if status == "executing":
        return "approved", "executing", "Executing"
    if status == "failed":
        return "approved", "failed", "Execution failed"
    if status in {"executed", "approved"}:
        return "approved", "completed", "Completed"
    if status == "denied":
        return "denied", "not run", "Completed"
    return status, status, status.title()


def _approval_failure_reason(store: SQLiteStore, approval) -> str | None:
    if approval.status != "failed":
        return None
    for event in reversed(store.list_audit(approval.session_id)):
        if event.event_type != "approval_manually_failed":
            continue
        if event.payload.get("approval_id") != approval.id:
            continue
        reason = event.payload.get("reason")
        if isinstance(reason, str):
            return str(redact_secrets(reason))
    return None


def _approval_summary(action_json: str) -> dict[str, str]:
    try:
        action = parse_action(action_json)
    except ValueError:
        return {"tool": "unknown", "operation": "Unknown action", "target": "", "command": ""}
    if action.type is ActionType.WRITE_FILE:
        return {
            "tool": action.type.value,
            "operation": "Write file",
            "target": str(action.payload.get("path", "")),
            "command": "",
        }
    if action.type is ActionType.READ_FILE:
        return {
            "tool": action.type.value,
            "operation": "Read file",
            "target": str(action.payload.get("path", "")),
            "command": "",
        }
    if action.type is ActionType.RUN_TESTS:
        return {"tool": action.type.value, "operation": "Run tests", "target": "", "command": ""}
    if action.type is ActionType.RUN_SHELL:
        command = str(action.payload.get("command", ""))
        operation, target = _shell_operation_summary(command)
        return {"tool": action.type.value, "operation": operation, "target": target, "command": command}
    return {"tool": action.type.value, "operation": action.type.value, "target": "", "command": ""}


def _shell_operation_summary(command: str) -> tuple[str, str]:
    tokens = command.split()
    if len(tokens) >= 2 and tokens[0].lower() in {"rm", "del"}:
        return "Delete file", _strip_command_quotes(tokens[-1])
    if len(tokens) >= 2 and tokens[0].lower() in {"rd", "rmdir"}:
        return "Delete directory", _strip_command_quotes(tokens[-1])
    return "Run shell command", command


def _strip_command_quotes(value: str) -> str:
    return value.strip().strip('"').strip("'")


def _render_markdown(value: str) -> str:
    lines = value.splitlines() or [""]
    rendered: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("```"):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            if in_code:
                rendered.append(f"<pre><code>{''.join(code_lines)}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(f"{html.escape(line)}\n")
            index += 1
            continue
        if _is_table_start(lines, index):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            table_html, consumed = _render_table(lines[index:])
            rendered.append(table_html)
            index += consumed
            continue
        escaped = html.escape(line)
        heading = re.match(r"^(#{1,6})\s+(.+)$", escaped)
        if heading:
            if in_list:
                rendered.append("</ul>")
                in_list = False
            level = len(heading.group(1))
            rendered.append(f"<h{level}>{_render_inline_markdown(heading.group(2))}</h{level}>")
            index += 1
            continue
        if escaped.startswith("&gt; "):
            if in_list:
                rendered.append("</ul>")
                in_list = False
            rendered.append(f"<blockquote>{_render_inline_markdown(escaped[5:])}</blockquote>")
            index += 1
            continue
        if escaped.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{_render_inline_markdown(escaped[2:])}</li>")
            index += 1
            continue
        if in_list:
            rendered.append("</ul>")
            in_list = False
        if escaped.strip():
            rendered.append(f"<p>{_render_inline_markdown(escaped)}</p>")
        index += 1
    if in_list:
        rendered.append("</ul>")
    if in_code:
        rendered.append(f"<pre><code>{''.join(code_lines)}</code></pre>")
    return "".join(rendered)


def _render_inline_markdown(value: str) -> str:
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" rel="nofollow noopener">\1</a>',
        value,
    )
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", value)
    return value


def _is_table_start(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    return (
        lines[index].strip().startswith("|")
        and re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*", lines[index + 1]) is not None
    )


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _render_table(lines: list[str]) -> tuple[str, int]:
    headers = _table_cells(lines[0])
    rows: list[list[str]] = []
    index = 2
    while index < len(lines) and lines[index].strip().startswith("|"):
        rows.append(_table_cells(lines[index]))
        index += 1
    header_html = "".join(f"<th>{_render_inline_markdown(html.escape(cell))}</th>" for cell in headers)
    rows_html = "".join(
        "<tr>" + "".join(f"<td>{_render_inline_markdown(html.escape(cell))}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>", index


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
    live_session_keys: dict[str, str] = {}
    app = FastAPI(title="Guarded Harness")
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    def index(request: Request):
        settings = _load_provider_settings(root)
        credential_configured = _credential_store().status()
        conversation_items = _conversation_items(store)
        chat_items = list(reversed(conversation_items))
        return _TEMPLATES.TemplateResponse(
            request,
            "index.html",
            {
                "title": "Chat Workspace",
                "settings": settings,
                "credential_configured": credential_configured,
                "provider_status": _provider_status(settings, credential_configured),
                "conversation_items": chat_items,
                "sidebar_items": conversation_items,
                "sidebar_groups": _sidebar_groups(conversation_items),
                "pending_approval_count": _pending_approval_count(store),
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
                "pending_approval_count": _pending_approval_count(store),
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
        _record_provider_settings(
            store,
            session.id,
            {"mode": selected_mode, "base_url": selected_base_url, "model": selected_model},
        )
        if selected_mode == "live" and api_key.strip():
            live_session_keys[session.id] = api_key.strip()
        return RedirectResponse(url="/", status_code=303)

    @app.get("/sessions/{session_id}")
    def show_session(request: Request, session_id: str):
        try:
            session = store.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        conversation_items = _conversation_items(store)
        return _TEMPLATES.TemplateResponse(
            request,
            "session.html",
            {
                "title": "Session",
                "session": session,
                "display_task": redact_secrets(session.task),
                "status_label": _status_label(session.status.value),
                "pending_approval_count": _pending_approval_count(store),
                "sidebar_groups": _sidebar_groups(conversation_items, session.id),
                "events": store.list_audit(session_id),
            },
        )

    @app.get("/approvals")
    def approvals(request: Request):
        approvals = [_approval_view(store, approval) for approval in store.list_approvals()]
        grouped = {
            "pending": [approval for approval in approvals if approval["status"] == "pending"],
            "executing": [approval for approval in approvals if approval["status"] == "executing"],
            "completed": [
                approval
                for approval in approvals
                if approval["status"] in {"approved", "denied", "executed"}
            ],
            "failed": [approval for approval in approvals if approval["status"] == "failed"],
        }
        counts = {status: len(items) for status, items in grouped.items()}
        return _TEMPLATES.TemplateResponse(
            request,
            "approvals.html",
            {
                "title": "Approvals",
                "approvals": approvals,
                "approval_groups": grouped,
                "approval_counts": counts,
                "pending_approval_count": _pending_approval_count(store),
            },
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
        return _resume_approval(store, approval_id, approved=True, live_session_keys=live_session_keys)

    @app.post("/approvals/{approval_id}/deny")
    def deny(approval_id: str):
        return _resume_approval(store, approval_id, approved=False, live_session_keys=live_session_keys)

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


def _resume_approval(
    store: SQLiteStore,
    approval_id: str,
    approved: bool,
    live_session_keys: dict[str, str] | None = None,
) -> RedirectResponse:
    try:
        approval = store.get_approval(approval_id)
        session = store.get_session(approval.session_id)
        provider_settings = _provider_settings_for_session(store, session.id)
        if provider_settings is not None and provider_settings["mode"] == "live":
            session_key = (live_session_keys or {}).get(session.id, "")
            loop = _loop_for_provider(
                session.workspace,
                store,
                _live_provider(provider_settings["base_url"], provider_settings["model"], session_key, None),
            )
            continue_after_resolution = True
        else:
            loop = AgentLoop.for_workspace(session.workspace, MockLLM([]), store)
            continue_after_resolution = False
        resumed = loop.resume_after_approval(
            approval_id,
            approved,
            continue_after_resolution=continue_after_resolution,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/sessions/{resumed.id}", status_code=303)
