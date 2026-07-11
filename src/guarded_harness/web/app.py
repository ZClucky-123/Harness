import json
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore
from guarded_harness.governance.redaction import redact_secrets


_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES = Jinja2Templates(directory=str(_PACKAGE_DIR / "templates"))


def _store_for(store_path: Path | None, workspace_root: Path | None) -> tuple[SQLiteStore, Path]:
    root = Path(workspace_root).resolve() if workspace_root is not None else Path.cwd().resolve()
    if store_path is None:
        database_path = root / ".guarded-harness" / "state.sqlite3"
    else:
        database_path = Path(store_path).resolve()
        if workspace_root is None:
            root = database_path.parent
    return SQLiteStore(database_path, workspace_root=root), root


def _finish_loop(workspace_root: Path, store: SQLiteStore, message: str) -> AgentLoop:
    return AgentLoop.for_workspace(
        workspace_root,
        MockLLM([json.dumps({"type": "finish", "message": message})]),
        store,
    )


def create_app(store_path: Path | None = None, workspace_root: Path | None = None) -> FastAPI:
    """Create a local, deterministic WebUI backed by a workspace-local store."""
    store, root = _store_for(store_path, workspace_root)
    app = FastAPI(title="Guarded Harness")
    app.mount("/static", StaticFiles(directory=str(_PACKAGE_DIR / "static")), name="static")

    @app.get("/")
    def index(request: Request):
        return _TEMPLATES.TemplateResponse(request, "index.html", {"title": "Guarded Harness"})

    @app.post("/sessions")
    def start_session(task: str = Form(...)):
        session = _finish_loop(root, store, "mock run completed").run(task)
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
            {
                "title": "Session",
                "session": session,
                "display_task": redact_secrets(session.task),
                "events": store.list_audit(session_id),
            },
        )

    @app.get("/approvals")
    def approvals(request: Request):
        return _TEMPLATES.TemplateResponse(
            request,
            "approvals.html",
            {"title": "Approvals", "approvals": store.list_unfinished_approvals()},
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
