import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))


def _store_for(store_path: Path | None) -> SQLiteStore:
    if store_path is None:
        workspace_root = Path.cwd().resolve()
        database_path = workspace_root / ".guarded-harness" / "state.sqlite3"
    else:
        database_path = Path(store_path).resolve()
        workspace_root = database_path.parent
    return SQLiteStore(database_path, workspace_root=workspace_root)


def _finish_loop(workspace_root: Path, store: SQLiteStore, message: str) -> AgentLoop:
    return AgentLoop.for_workspace(
        workspace_root,
        MockLLM([json.dumps({"type": "finish", "message": message})]),
        store,
    )


def create_app(store_path: Path | None = None) -> FastAPI:
    """Create a local, deterministic WebUI backed by a workspace-local store."""
    store = _store_for(store_path)
    app = FastAPI(title="Guarded Harness")
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    def index(request: Request):
        return _TEMPLATES.TemplateResponse(request, "index.html", {"title": "Guarded Harness"})

    @app.post("/sessions")
    def start_session(task: str = Form(...)):
        workspace_root = store.db_path.parent
        session = _finish_loop(workspace_root, store, "mock run completed").run(task)
        return RedirectResponse(url=f"/sessions/{session.id}", status_code=303)

    @app.get("/sessions/{session_id}")
    def show_session(request: Request, session_id: str):
        try:
            session = store.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session not found") from exc
        return _TEMPLATES.TemplateResponse(
            request,
            "session.html",
            {"title": "Session", "session": session, "events": store.list_audit(session_id)},
        )

    @app.get("/approvals")
    def approvals(request: Request):
        return _TEMPLATES.TemplateResponse(
            request,
            "approvals.html",
            {"title": "Approvals", "approvals": store.list_pending_approvals()},
        )

    @app.post("/approvals/{approval_id}/approve")
    def approve(approval_id: str):
        return _resume_approval(store, approval_id, approved=True)

    @app.post("/approvals/{approval_id}/deny")
    def deny(approval_id: str):
        return _resume_approval(store, approval_id, approved=False)

    return app


def _resume_approval(store: SQLiteStore, approval_id: str, approved: bool) -> RedirectResponse:
    try:
        approval = store.get_approval(approval_id)
        session = store.get_session(approval.session_id)
        resumed = _finish_loop(session.workspace, store, "approval resolved").resume_after_approval(approval_id, approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="approval not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RedirectResponse(url=f"/sessions/{resumed.id}", status_code=303)
