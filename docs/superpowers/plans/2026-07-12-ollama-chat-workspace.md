# Ollama Chat Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the WebUI home page into an Ollama-styled Chat Workspace that stays on `/`, displays persisted interaction history, hides Guardrail Demo from primary navigation, and keeps existing provider, approval, trace, and demo functionality intact.

**Architecture:** Add a small store query for recent sessions, a WebUI view-model helper that summarizes audit events into conversation items, and update Jinja/CSS to render a white, pill-based Ollama interface. Form submission continues to use synchronous FastAPI POST, but redirects back to `/` so the saved session appears in the workspace history.

**Tech Stack:** Python 3.11, FastAPI, Jinja2 templates, SQLiteStore, pytest TestClient, static CSS only.

## Global Constraints

- Use Jinja + CSS only; do not introduce a frontend build system, JavaScript framework, WebSocket, or remote font.
- Do not change the live provider protocol or agent loop semantics.
- Do not add real multi-turn memory; conversation history is a persisted session summary.
- Do not echo API keys in HTML, sessions, audit events, or provider config files.
- Keep `/guardrail` available, but remove it from primary navigation and the home page.
- Preserve readable Chinese output with `ensure_ascii=False`.
- Run `.venv\Scripts\python.exe -m pytest -q` before completion.

---

## File Structure

- Modify `src/guarded_harness/memory/store.py`: add `list_sessions(limit: int = 20) -> list[SessionState]`.
- Modify `src/guarded_harness/web/app.py`: add conversation summary helpers, pass conversation items to `/`, redirect `/sessions` POST back to `/`.
- Modify `src/guarded_harness/web/templates/index.html`: replace Dashboard cards with Chat Workspace.
- Modify `src/guarded_harness/web/templates/settings.html`: remove terminal wording and apply Ollama layout classes.
- Modify `src/guarded_harness/web/templates/session.html`: apply Ollama terminal-card layout.
- Modify `src/guarded_harness/web/templates/approvals.html`: remove Guardrail Demo nav link and apply Ollama queue cards.
- Modify `src/guarded_harness/web/templates/guardrail.html`: keep direct page available but align visual style.
- Modify `src/guarded_harness/web/static/styles.css`: replace OpenCode terminal style with Ollama-inspired tokens.
- Modify `tests/integration/test_web.py`: update old Dashboard assertions and add Chat Workspace/history behavior.

---

### Task 1: Store Recent Sessions

**Files:**
- Modify: `src/guarded_harness/memory/store.py`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Produces: `SQLiteStore.list_sessions(limit: int = 20) -> list[SessionState]`, ordered newest first by `updated_at`.
- Consumes: Existing `SessionState` constructor and `SessionStatus`.

- [x] **Step 1: Write the failing test**

Add this test near the Web index tests in `tests/integration/test_web.py`:

```python
def test_index_lists_recent_sessions_as_conversation_items(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    first = store.create_session("first task", tmp_path)
    store.append_audit(first.id, "finished", {"message": "first done"})
    second = store.create_session("second task", tmp_path)
    store.append_audit(second.id, "finished", {"message": "second done"})
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "first task" in response.text
    assert "second task" in response.text
    assert "first done" in response.text
    assert "second done" in response.text
    assert response.text.index("second task") < response.text.index("first task")
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
```

Expected: FAIL because the home page does not read sessions and `Chat Workspace` is absent.

- [x] **Step 3: Add store query**

Add this method to `SQLiteStore` after `get_session`:

```python
    def list_sessions(self, limit: int = 20) -> list[SessionState]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT * FROM sessions
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SessionState(
                row["id"],
                row["task"],
                SessionStatus(row["status"]),
                Path(row["workspace"]),
                row["step_count"],
                row["pending_approval_id"],
            )
            for row in rows
        ]
```

- [x] **Step 4: Add WebUI conversation helpers**

In `src/guarded_harness/web/app.py`, add helpers above `create_app`:

```python
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
            return str(message)
        if event.event_type == "approval_requested":
            return "waiting for human approval"
        if event.event_type == "guardrail_denied":
            return str(event.payload.get("reason", "guardrail denied the action"))
        if event.event_type == "parser_error":
            return "model response could not be parsed as an action"
        if event.event_type == "max_steps":
            return "stopped after reaching max steps"
    return "session started"
```

Then update the `/` route context:

```python
                "title": "Chat Workspace",
                "conversation_items": _conversation_items(store),
```

- [x] **Step 5: Update index template minimally**

In `index.html`, include `Chat Workspace` and loop over `conversation_items` so the test can pass before full styling:

```html
<h1>Chat Workspace</h1>
{% for item in conversation_items %}
  <article class="conversation-item">
    <p>{{ item.task }}</p>
    <p>{{ item.summary }}</p>
    <p>{{ item.status }} · {{ item.step_count }} steps</p>
    <a href="{{ item.trace_url }}">View trace</a>
  </article>
{% endfor %}
```

- [x] **Step 6: Run test to verify it passes**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
```

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add src/guarded_harness/memory/store.py src/guarded_harness/web/app.py src/guarded_harness/web/templates/index.html tests/integration/test_web.py
git commit -m "feat: show recent sessions in web workspace"
```

---

### Task 2: Keep Task Submission on Home Page

**Files:**
- Modify: `src/guarded_harness/web/app.py`
- Modify: `src/guarded_harness/web/templates/index.html`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Consumes: `_conversation_items(store)`.
- Changes: `POST /sessions` returns `RedirectResponse(url="/", status_code=303)` on success.

- [x] **Step 1: Replace the old redirect test**

Replace `test_starting_task_redirects_to_session_trace` with:

```python
def test_starting_task_returns_to_workspace_with_saved_conversation(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post("/sessions", data={"task": "inspect the repository"}, follow_redirects=True)

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "inspect the repository" in response.text
    assert "mock run completed" in response.text
    assert "View trace" in response.text
    assert "session_started" not in response.text
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_starting_task_returns_to_workspace_with_saved_conversation -q
```

Expected: FAIL because `POST /sessions` redirects to `/sessions/{id}`.

- [x] **Step 3: Change redirect**

In `start_session`, replace:

```python
        return RedirectResponse(url=f"/sessions/{session.id}", status_code=303)
```

with:

```python
        return RedirectResponse(url="/", status_code=303)
```

- [x] **Step 4: Run targeted tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_starting_task_returns_to_workspace_with_saved_conversation tests/integration/test_web.py::test_starting_task_uses_saved_live_settings_without_retyping_key -q
```

Expected: PASS or live-settings test failure only from old assertion expecting session-page trace text.

- [x] **Step 5: Update live-mode assertions**

If needed, update live tests to assert workspace conversation output:

```python
    assert "Chat Workspace" in response.text
    assert "live done" in response.text
```

and:

```python
    assert "Chat Workspace" in response.text
    assert "2" in response.text
```

- [x] **Step 6: Commit**

```bash
git add src/guarded_harness/web/app.py tests/integration/test_web.py
git commit -m "feat: keep web tasks in chat workspace"
```

---

### Task 3: Hide Guardrail Demo from Primary UI

**Files:**
- Modify: `src/guarded_harness/web/templates/index.html`
- Modify: `src/guarded_harness/web/templates/settings.html`
- Modify: `src/guarded_harness/web/templates/session.html`
- Modify: `src/guarded_harness/web/templates/approvals.html`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Keeps: `GET /guardrail` and `POST /guardrail`.
- Removes: Main navigation links to `/guardrail`.

- [x] **Step 1: Write failing navigation test**

Update `test_index_loads` into:

```python
def test_index_loads_chat_workspace_without_guardrail_nav():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "Provider Settings" in response.text
    assert "Approvals" in response.text
    assert "Guardrail Demo" not in response.text
    assert "Change configuration" not in response.text
    assert "deepseek-v4-flash" in response.text
    assert 'name="api_key"' not in response.text
```

- [x] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav -q
```

Expected: FAIL while old index still contains Guardrail Demo or Change configuration.

- [x] **Step 3: Remove primary guardrail links**

In primary nav templates, use:

```html
<nav class="nav-links">
  <a href="/">Workspace</a>
  <a href="/settings">Provider Settings</a>
  <a href="/approvals">Approvals</a>
</nav>
```

For `approvals.html`, omit the self-link only if desired, but never include `/guardrail`.

- [x] **Step 4: Keep direct guardrail test**

Keep `test_guardrail_demo_page_evaluates_sample_actions` unchanged so the hidden page remains verified.

- [x] **Step 5: Run targeted tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_guardrail_demo_page_evaluates_sample_actions -q
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/guarded_harness/web/templates tests/integration/test_web.py
git commit -m "feat: hide guardrail demo from primary web ui"
```

---

### Task 4: Apply Ollama Visual System

**Files:**
- Modify: `src/guarded_harness/web/templates/index.html`
- Modify: `src/guarded_harness/web/templates/settings.html`
- Modify: `src/guarded_harness/web/templates/session.html`
- Modify: `src/guarded_harness/web/templates/approvals.html`
- Modify: `src/guarded_harness/web/templates/guardrail.html`
- Modify: `src/guarded_harness/web/static/styles.css`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Produces CSS classes: `shell`, `site-header`, `brand`, `nav-links`, `hero`, `status-pills`, `pill`, `chat-panel`, `message`, `message-user`, `message-agent`, `composer`, `button-primary`, `terminal-card`, `traffic-lights`, `queue-grid`, `queue-card`.

- [ ] **Step 1: Write structure assertions**

Add to `test_index_loads_chat_workspace_without_guardrail_nav`:

```python
    assert 'class="chat-panel"' in response.text
    assert 'class="composer"' in response.text
    assert 'class="status-pills"' in response.text
```

Add to `test_approvals_page_loads`:

```python
    assert 'class="queue-grid"' in response.text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_approvals_page_loads -q
```

Expected: FAIL until templates use the new classes.

- [ ] **Step 3: Replace `styles.css` with Ollama tokens**

Use CSS tokens:

```css
:root {
  color: #000;
  background: #fff;
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
body { margin: 0; background: #fff; }
.shell { max-width: 760px; margin: 0 auto; padding: 24px; }
.shell.wide { max-width: 1040px; }
.site-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 56px; }
.brand { color: #000; font-weight: 600; text-decoration: none; }
.nav-links { display: flex; gap: 16px; flex-wrap: wrap; }
.nav-links a, .muted-link { color: #737373; text-decoration: none; }
.nav-links a:hover, .muted-link:hover { color: #000; text-decoration: underline; text-underline-offset: 4px; }
.hero { margin: 72px 0 32px; text-align: center; }
h1 { margin: 0; font-size: 36px; line-height: 1.11; font-weight: 500; letter-spacing: 0; }
h2 { margin: 0 0 16px; font-size: 24px; line-height: 1.33; font-weight: 600; letter-spacing: 0; }
p { color: #737373; line-height: 1.5; }
.status-pills { display: flex; justify-content: center; gap: 8px; flex-wrap: wrap; margin-top: 24px; }
.pill, .mode-option { border: 1px solid #e5e5e5; border-radius: 9999px; padding: 8px 16px; background: #fafafa; color: #000; font-size: 14px; }
.chat-panel, .panel, .queue-card, .terminal-card { border: 1px solid #e5e5e5; border-radius: 12px; background: #fff; }
.chat-panel { padding: 16px; }
.message { padding: 16px; border-bottom: 1px solid #e5e5e5; }
.message:last-child { border-bottom: 0; }
.message-user strong, .message-agent strong { color: #000; font-weight: 500; }
.composer { margin: 24px 0 64px; padding: 16px; border: 1px solid #e5e5e5; border-radius: 24px; background: #fafafa; }
label { display: block; margin: 14px 0 6px; font-weight: 500; color: #000; }
input[type="text"], input:not([type]), input[type="password"], textarea { box-sizing: border-box; width: 100%; border: 1px solid #e5e5e5; border-radius: 9999px; padding: 10px 16px; background: #fff; color: #000; font: inherit; }
textarea { min-height: 112px; border-radius: 24px; resize: vertical; }
button, .button-primary { border: 0; border-radius: 9999px; background: #000; color: #fff; padding: 10px 20px; font: inherit; font-weight: 500; cursor: pointer; text-decoration: none; }
button.deny { background: #fff; color: #991b1b; border: 1px solid #fecaca; }
pre { overflow-x: auto; white-space: pre-wrap; border-radius: 12px; background: #fafafa; padding: 16px; color: #000; }
.traffic-lights { display: flex; gap: 6px; margin-bottom: 12px; }
.traffic-lights span { width: 12px; height: 12px; border-radius: 9999px; display: inline-block; }
.traffic-lights span:nth-child(1) { background: #ff5f56; }
.traffic-lights span:nth-child(2) { background: #ffbd2e; }
.traffic-lights span:nth-child(3) { background: #27c93f; }
.queue-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.queue-card, .panel { padding: 24px; }
@media (max-width: 760px) {
  .shell { padding: 18px; }
  .site-header { align-items: flex-start; flex-direction: column; }
  .queue-grid { grid-template-columns: 1fr; }
  h1 { font-size: 30px; }
}
```

- [ ] **Step 4: Update templates**

Apply these structural rules:

- Replace `<main>` with `<main class="shell">` or `<main class="shell wide">` for approvals.
- Replace `<header class="topbar">` with `<header class="site-header">`.
- Replace `<pre class="wordmark">` with `<a class="brand" href="/">Guarded Harness</a>`.
- Use `.hero`, `.status-pills`, `.chat-panel`, `.composer`, `.terminal-card`, `.queue-card`.
- Keep all form `name` attributes unchanged.

- [ ] **Step 5: Run targeted web tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/guarded_harness/web/templates src/guarded_harness/web/static/styles.css tests/integration/test_web.py
git commit -m "feat: apply ollama web ui styling"
```

---

### Task 5: Final Verification and Documentation

**Files:**
- Modify: `AGENT_LOG.md` if it already tracks verification notes.
- Modify: `docs/superpowers/plans/2026-07-12-ollama-chat-workspace.md` checkboxes as work is completed.

**Interfaces:**
- Produces: A clean commit series with passing tests.

- [ ] **Step 1: Run compile check**

Run:

```powershell
.venv\Scripts\python.exe -m compileall src tests
```

Expected: no syntax errors.

- [ ] **Step 2: Run full test suite**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass, currently expected baseline is about `198 passed, 2 skipped`.

- [ ] **Step 3: Inspect diff and status**

Run:

```bash
git status --short
git diff --stat
```

Expected: only intended files changed before the final commit.

- [ ] **Step 4: Commit final verification note if files changed**

If `AGENT_LOG.md` or plan checkboxes are updated:

```bash
git add AGENT_LOG.md docs/superpowers/plans/2026-07-12-ollama-chat-workspace.md
git commit -m "docs: record ollama web ui verification"
```

- [ ] **Step 5: Final report**

Report:

- Commit hashes.
- Tests run and results.
- How to start the server.
- Note that `/guardrail` still exists but is hidden from primary UI.

## Self-Review

- Spec coverage: Chat Workspace, hidden Guardrail Demo entry, saved conversation display, home-page redirect, Ollama visual style, provider settings, approvals, session trace, and direct guardrail route are each mapped to tasks.
- Placeholder scan: no TBD/TODO/implement-later language.
- Type consistency: `SQLiteStore.list_sessions(limit: int = 20)` is introduced in Task 1 and consumed by `_conversation_items(store, limit: int = 12)`.

