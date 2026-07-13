from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore
from guarded_harness.web.app import create_app


def test_index_loads_chat_workspace_without_guardrail_nav(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert "styles.css?v=" in response.text
    assert "Chat Workspace" in response.text
    assert "Provider Settings" in response.text
    assert "Approvals" in response.text
    assert "Guardrail Demo" not in response.text
    assert "Change configuration" not in response.text
    assert "Recent Sessions" not in response.text
    assert "New session" not in response.text
    assert 'class="app-layout"' in response.text
    assert 'class="session-sidebar"' in response.text
    assert 'class="sidebar-brand"' in response.text
    assert "/guardrail" not in response.text
    assert "mode:" in response.text
    assert "deepseek-v4-flash" in response.text
    assert 'name="api_key"' not in response.text
    assert "chat-page" in response.text
    assert "composer-status" in response.text
    assert "message-system" not in response.text
    assert "mock · deepseek-v4-flash · key missing" in response.text
    assert "chat-scroll" not in response.text
    assert 'id="chat-scroll"' not in response.text
    assert "composer-fixed" in response.text
    assert "composer-submit" in response.text
    assert 'class="status-pills"' not in response.text
    assert '<h2>Provider</h2>' not in response.text
    assert "<strong>You</strong>" not in response.text
    assert "<strong>Harness</strong>" not in response.text
    assert "window.scrollTo" in response.text
    assert ">Task<" not in response.text
    assert ">Start task<" not in response.text
    assert 'aria-label="Start task"' in response.text
    assert "↑" in response.text
    assert "鈫" not in response.text
    assert " 路 " not in response.text
    assert response.text.index('placeholder="Message Guarded Harness..."') < response.text.index("mock · deepseek-v4-flash · key missing")


def test_chat_workspace_css_uses_global_scroll_and_compact_composer():
    client = TestClient(create_app())

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    assert ".chat-page" in response.text
    assert ".chat-page .site-header { position: fixed; left: var(--sidebar-width);" in response.text
    assert ".chat-panel { border: 0" in response.text
    assert ".composer-fixed" in response.text
    assert ".composer-submit" in response.text
    assert ".composer-status" in response.text
    assert "--sidebar-width: 320px" in response.text
    assert "--content-width: 860px" in response.text
    assert ".chat-page { min-height: 100vh; padding: 56px 32px 100px var(--sidebar-width); }" in response.text
    assert ".chat-main { width: min(var(--content-width), 100%); margin: 0 auto; min-width: 0; }" in response.text
    assert ".composer-fixed { position: fixed; left: calc(var(--sidebar-width) + (100vw - var(--sidebar-width) - 32px) / 2); bottom: 16px; z-index: 20; width: min(var(--content-width), calc(100vw - var(--sidebar-width) - 32px));" in response.text
    assert ".session-sidebar { position: fixed; left: 0; top: 0; width: var(--sidebar-width); height: 100vh; box-sizing: border-box; border-right: 1px solid #e5e5e5; background: #fff; }" in response.text
    assert ".sidebar-brand" in response.text
    assert ".sidebar-scroll { height: calc(100vh - 72px); overflow-y: auto; padding: 16px 24px 24px; }" in response.text
    assert ".sidebar-item { min-width: 0" in response.text
    assert ".sidebar-item span, .sidebar-item small { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }" in response.text
    assert ".composer, .settings-card { margin: 24px 0 64px; padding: 8px 8px 6px 8px; border: 1px solid #e5e5e5; border-radius: 24px; background: #fff; }" in response.text
    assert ".composer-row { display: grid; grid-template-columns: 1fr; align-items: end; }" in response.text
    assert ".composer-submit { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; padding: 0; border-radius: 9999px; line-height: 1; }" in response.text
    assert ".composer-stop-icon { display: block; width: 10px; height: 10px; border-radius: 2px; background: #fff; }" in response.text
    assert ".composer-submit:disabled { opacity: 1; background: #000; cursor: default; }" in response.text
    assert ".composer-submit:disabled .composer-stop-icon { background: #fff; }" in response.text
    assert ".loading-placeholder { font-size: 28px; line-height: 1; letter-spacing: 0; color: #737373; }" in response.text
    assert "textarea { min-height: 36px; max-height: 180px; border-radius: 22px; resize: none; overflow-y: auto; }" in response.text
    assert ".composer-sticky" not in response.text
    assert ".chat-scroll" not in response.text


def test_composer_matches_borderless_input_with_submit_in_status_row():
    client = TestClient(create_app())

    html = client.get("/").text
    css = client.get("/static/styles.css").text

    assert ".composer-status { display: flex; align-items: center; justify-content: space-between;" in css
    assert ".composer-row textarea { border: 0; outline: 0; padding: 4px 14px; overflow-y: hidden; }" in css
    assert ".composer-row textarea:focus { box-shadow: none; }" in css
    assert 'taskInput.style.overflowY = taskInput.scrollHeight > 180 ? "auto" : "hidden";' in html
    assert 'class="composer-status"' in html
    assert html.index("composer-submit") > html.index("composer-status")


def test_composer_submit_clears_input_and_prevents_duplicate_submits():
    client = TestClient(create_app())

    html = client.get("/").text

    assert "let isSubmitting = false;" in html
    assert 'const submitButton = document.querySelector(".composer-submit");' in html
    assert 'const conversationList = document.querySelector(".conversation-list");' in html
    assert 'const taskSubmitValue = document.querySelector("#task-submit-value");' in html
    assert "function appendOptimisticUserMessage(text) {" in html
    assert 'article.className = "conversation-item conversation-item-pending";' in html
    assert 'message.className = "message message-user";' in html
    assert "paragraph.textContent = text;" in html
    assert "conversationList.append(article);" in html
    assert "function appendOptimisticAgentMessage() {" in html
    assert 'article.className = "conversation-item conversation-item-pending conversation-item-loading";' in html
    assert 'message.className = "message message-agent";' in html
    assert 'body.className = "markdown-body loading-placeholder";' in html
    assert 'body.textContent = "...";' in html
    assert 'composerForm?.addEventListener("submit", (event) => {' in html
    assert "if (isSubmitting) {" in html
    assert "event.preventDefault();" in html
    assert 'taskSubmitValue.name = "task";' in html
    assert "const submittedTask = taskInput.value;" in html
    assert "taskSubmitValue.value = submittedTask;" in html
    assert 'taskInput.removeAttribute("name");' in html
    assert "isSubmitting = true;" in html
    assert "taskInput.value = \"\";" in html
    assert "appendOptimisticUserMessage(submittedTask);" in html
    assert "appendOptimisticAgentMessage();" in html
    assert "taskInput.disabled = true;" not in html
    assert "submitButton.disabled = true;" in html
    assert 'submitButton.textContent = "";' in html
    assert 'stopIcon.className = "composer-stop-icon";' in html
    assert 'stopIcon.setAttribute("aria-hidden", "true");' in html
    assert "submitButton.append(stopIcon);" in html
    assert 'submitButton.setAttribute("aria-label", "Task is running");' in html
    assert 'submitButton.setAttribute("aria-busy", "true");' in html


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
    conversation_html = response.text[response.text.index('class="conversation-list"'):]
    assert conversation_html.index("first task") < conversation_html.index("second task")
    assert response.text.count('class="message message-user"') == 2
    assert response.text.count('class="message message-agent"') == 2
    assert "<strong>You</strong>" not in response.text
    assert "<strong>Harness</strong>" not in response.text
    assert "running" in response.text
    assert "0 steps" in response.text
    assert response.text.count('class="muted-link"') == 2


def test_sidebar_uses_latest_first_and_singular_step_label(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    older = store.create_session("older one-step task", tmp_path)
    older.step_count = 1
    store.update_session(older)
    newer = store.create_session("newer two-step task", tmp_path)
    newer.step_count = 2
    store.update_session(newer)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    sidebar_start = response.text.index('class="sidebar-list"')
    conversation_start = response.text.index('class="conversation-list"')
    sidebar_html = response.text[sidebar_start:conversation_start]
    conversation_html = response.text[conversation_start:]
    assert sidebar_html.index("newer two-step task") < sidebar_html.index("older one-step task")
    assert conversation_html.index("older one-step task") < conversation_html.index("newer two-step task")
    assert "finished · 1 step" in response.text or "running · 1 step" in response.text
    assert "running · 2 steps" in response.text


def test_sidebar_groups_recent_sessions_and_session_page_marks_current(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("current task", tmp_path)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    index_response = client.get("/")
    session_response = client.get(f"/sessions/{session.id}")

    assert index_response.status_code == 200
    assert "Today" in index_response.text
    assert 'class="sidebar-group"' in index_response.text
    assert session_response.status_code == 200
    assert 'class="sidebar-item active"' in session_response.text
    assert "current task" in session_response.text
    assert session_response.text.index('class="sidebar-brand"') < session_response.text.index('class="sidebar-list"')


def test_index_redacts_recent_session_summary_secrets(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("finished task", tmp_path)
    store.append_audit(session.id, "finished", {"message": "finished password=summary-secret"})
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "summary-secret" not in response.text
    assert "[REDACTED]" in response.text


def test_index_renders_markdown_summary_safely(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("markdown task", tmp_path)
    store.append_audit(session.id, "finished", {"message": "**完成**\n- <script>alert(1)</script>"})
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "<strong>完成</strong>" in response.text
    assert "<li>&lt;script&gt;alert(1)&lt;/script&gt;</li>" in response.text
    assert "<script>alert(1)</script>" not in response.text


def test_index_renders_common_markdown_blocks_safely(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("markdown blocks", tmp_path)
    store.append_audit(
        session.id,
        "finished",
        {
            "message": (
                "# 标题\n"
                "> 引用\n"
                "[链接](https://example.test)\n"
                "| A | B |\n"
                "| --- | --- |\n"
                "| 1 | 2 |\n"
                "```python\n"
                "print('<safe>')\n"
                "```"
            )
        },
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "<h1>标题</h1>" in response.text
    assert "<blockquote>引用</blockquote>" in response.text
    assert '<a href="https://example.test" rel="nofollow noopener">链接</a>' in response.text
    assert "<table>" in response.text
    assert "<th>A</th>" in response.text
    assert "<td>1</td>" in response.text
    assert "<pre><code>print(&#x27;&lt;safe&gt;&#x27;)" in response.text
    assert "<safe>" not in response.text


def test_waiting_approval_session_shows_approval_card_in_chat(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="approval-card"' in response.text
    assert "Approval required" in response.text
    assert "Tool: write_file" in response.text
    assert "Action: Write file" in response.text
    assert "Target: .env" in response.text
    assert "modifying an environment file requires approval" in response.text
    assert waiting.pending_approval_id in response.text


def test_approval_card_submit_switches_to_processing_state(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    html = client.get("/").text

    assert f'data-approval-card="{waiting.pending_approval_id}"' in html
    assert 'data-approval-title' in html
    assert 'data-approval-status' in html
    assert 'data-approval-submit="approve"' in html
    assert 'data-approval-submit="deny-action"' in html
    assert 'data-approval-submit="stop-task"' in html
    assert "Deny action" in html
    assert "Stop task" in html
    assert "document.querySelectorAll(\"[data-approval-card]\").forEach" in html
    assert 'const action = form.dataset.approvalSubmit;' in html
    assert 'title.textContent = approvalProcessingTitle(action);' in html
    assert 'status.textContent = approvalProcessingStatus(action);' in html
    assert 'card.querySelectorAll("button").forEach((button) => {' in html
    assert 'button.disabled = true;' in html
    assert "let approvalSubmitting = false;" in html
    assert "event.preventDefault();" in html
    assert "fetch(form.action, {" in html
    assert 'method: form.method || "POST",' in html
    assert "body: new FormData(form)," in html
    assert 'credentials: "same-origin",' in html
    assert 'redirect: "follow",' in html
    assert "if (response.redirected && response.url) {" in html
    assert "window.location.assign(response.url);" in html
    assert "window.location.reload();" in html
    assert 'title.textContent = "Approval failed";' in html
    assert 'button.disabled = false;' in html


def test_run_shell_approval_card_uses_real_tool_summary(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("remove generated file", tmp_path)
    store.create_approval_and_pause_session(
        session,
        '{"type":"run_shell","command":"rm build/output.txt"}',
        "shell command requires approval",
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    assert "Tool: run_shell" in response.text
    assert "Action: Delete file" in response.text
    assert "Target: build/output.txt" in response.text


def test_provider_settings_page_loads_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.get("/settings")

    assert response.status_code == 200
    assert "Provider Settings" in response.text
    assert "https://njusehub.info/v1" in response.text
    assert "deepseek-v4-flash" in response.text
    assert "key missing" in response.text


def test_primary_navigation_omits_guardrail_link_but_direct_page_loads(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("navigation check", tmp_path)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    for path in ("/settings", "/approvals", f"/sessions/{session.id}"):
        response = client.get(path)
        assert response.status_code == 200
        assert "/guardrail" not in response.text

    guardrail = client.get("/guardrail")
    assert guardrail.status_code == 200
    assert "Guardrail Demo" in guardrail.text
    assert 'class="chat-page"' in guardrail.text


def test_history_restore_refreshes_chat_page_and_partially_updates_other_pages(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("history refresh check", tmp_path)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    chat_response = client.get("/")
    assert chat_response.status_code == 200
    assert 'data-history-refresh="reload"' in chat_response.text
    assert 'window.addEventListener("pageshow", (event) => {' in chat_response.text
    assert 'if (historyRefreshMode === "reload") {' in chat_response.text
    assert "window.location.reload();" in chat_response.text

    for path in ("/settings", "/approvals", "/guardrail", f"/sessions/{session.id}"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'data-history-refresh="partial"' in response.text
        assert 'window.addEventListener("pageshow", (event) => {' in response.text
        assert "event.persisted" in response.text
        assert 'performance.getEntriesByType("navigation")[0]?.type === "back_forward"' in response.text
        assert 'fetch(window.location.href, { cache: "no-store" })' in response.text
        assert 'replacePageRegion(nextDocument, ".site-header");' in response.text
        assert 'replacePageRegion(nextDocument, ".session-sidebar");' in response.text
        assert 'replacePageRegion(nextDocument, ".chat-main");' in response.text
        assert "const formState = captureFormState();" in response.text
        assert "const detailsState = captureDetailsState();" in response.text
        assert "restoreFormState(formState);" in response.text
        assert "restoreDetailsState(detailsState);" in response.text
        assert "window.scrollTo(scrollX, scrollY);" in response.text


def test_provider_settings_save_updates_dashboard_without_persisting_key(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials(None)
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/settings",
        data={
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "qwen-turbo",
            "api_key": "settings-secret",
            "save_api_key": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "live" in response.text
    assert "qwen-turbo" in response.text
    assert "key configured" in response.text
    assert credentials.key == "settings-secret"
    assert "settings-secret" not in response.text
    assert "settings-secret" not in (tmp_path / ".guarded-harness" / "provider.json").read_text()


def test_starting_task_returns_to_workspace_with_saved_conversation(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post("/sessions", data={"task": "inspect the repository"}, follow_redirects=True)

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "inspect the repository" in response.text
    assert "mock run completed" in response.text
    assert "View trace" in response.text
    assert "session_started" not in response.text


def test_starting_task_uses_saved_live_settings_without_retyping_key(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials("stored-live-secret")
    captured = {}

    class FakeProvider:
        def __init__(self, base_url: str, model: str, api_key: str, timeout: float):
            captured.update({"base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout})

        def complete(self, context):
            return '{"type":"finish","message":"live done"}'

    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", FakeProvider)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))
    client.post(
        "/settings",
        data={"mode": "live", "base_url": "https://njusehub.info/v1", "model": "deepseek-v4-flash"},
    )

    response = client.post("/sessions", data={"task": "use saved provider"}, follow_redirects=True)

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "live done" in response.text
    assert captured == {
        "base_url": "https://njusehub.info/v1",
        "model": "deepseek-v4-flash",
        "api_key": "stored-live-secret",
        "timeout": 30.0,
    }


def test_session_page_preserves_chinese_text_in_task_and_trace(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("回复1+1+?", tmp_path)
    store.append_audit(session.id, "finished", {"message": "答案是2"})
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get(f"/sessions/{session.id}")

    assert response.status_code == 200
    assert "回复1+1+?" in response.text
    assert "答案是2" in response.text
    assert "\\u56de" not in response.text
    assert "\\u7b54" not in response.text


def test_approvals_page_preserves_chinese_text_in_reason_and_action(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("配置中文文件", tmp_path)
    store.create_approval(
        session.id,
        '{"type":"write_file","path":"notes.txt","content":"中文内容"}',
        "需要人工审批",
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "需要人工审批" in response.text
    assert "中文内容" in response.text
    assert "\\u4e2d" not in response.text
    assert "\\u9700" not in response.text


def test_web_live_mode_requires_api_key_when_keyring_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
        },
    )

    assert response.status_code == 400
    assert "API key is required" in response.text


def test_web_live_mode_uses_submitted_provider_config_without_persisting_key(tmp_path: Path, monkeypatch):
    captured = {}

    class FakeProvider:
        def __init__(self, base_url: str, model: str, api_key: str, timeout: float):
            captured.update({"base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout})

        def complete(self, context):
            return '{"type":"finish","message":"2"}'

    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", FakeProvider)
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: _FakeCredentials(None))
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
            "api_key": "njusehub-secret",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "Chat Workspace" in response.text
    assert "2" in response.text
    assert captured == {
        "base_url": "https://njusehub.info/v1",
        "model": "deepseek-v4-flash",
        "api_key": "njusehub-secret",
        "timeout": 30.0,
    }
    assert "njusehub-secret" not in response.text
    assert "njusehub-secret" not in (tmp_path / "state.sqlite3").read_bytes().decode("utf-8", errors="ignore")


def test_web_live_mode_can_save_submitted_key_to_keyring(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials(None)
    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", _FinishingProvider)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.post(
        "/sessions",
        data={
            "task": "reply 1+1",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "deepseek-v4-flash",
            "api_key": "stored-secret",
            "save_api_key": "on",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert credentials.key == "stored-secret"


def test_approvals_page_loads(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "Approvals" in response.text
    assert "No approval records yet." in response.text
    assert 'class="panel"' not in response.text


def test_approvals_page_shows_failed_operation_summary_and_actions(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("delete test.md", tmp_path)
    approval = store.create_approval_and_pause_session(
        session,
        '{"type":"run_shell","command":"del D:\\\\code\\\\Harness\\\\Harness\\\\.worktrees\\\\guarded-harness-impl\\\\test.md"}',
        "shell command requires approval",
    )
    store.begin_approval_resolution(approval.id, approved=True)
    store.mark_approval_failed(approval.id, "del is a cmd built-in command and cannot be run directly by this executor")
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "Execution failed" in response.text
    assert "Delete file" in response.text
    assert "Task: delete test.md" in response.text
    assert "Tool: run_shell" in response.text
    assert "Target: D:\\code\\Harness\\Harness\\.worktrees\\guarded-harness-impl\\test.md" in response.text
    assert "del is a cmd built-in command and cannot be run directly by this executor" in response.text
    assert "View task" not in response.text
    assert response.text.count("View trace") == 1
    assert "Details" in response.text
    assert 'class="approval-text-link"' in response.text
    assert 'class="button-secondary"' not in response.text


def test_guardrail_demo_page_evaluates_sample_actions(tmp_path: Path):
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))

    page = client.get("/guardrail")
    response = client.post("/guardrail", data={"sample": "rm_root"})

    assert page.status_code == 200
    assert "Guardrail Demo" in page.text
    assert "Try rm -rf /" in page.text
    assert response.status_code == 200
    assert "decision: deny" in response.text
    assert "destructive" in response.text


def test_denying_approval_resumes_session(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    approval_id = waiting.pending_approval_id
    client = TestClient(create_app(store.db_path))

    response = client.post(f"/approvals/{approval_id}/deny", follow_redirects=True)

    assert response.status_code == 200
    assert "approval_denied" in response.text
    assert store.get_approval(approval_id).status == "denied"


def test_denying_live_approval_continues_provider_with_feedback(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials("stored-live-secret")
    contexts = []

    class ContinuingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def complete(self, context):
            contexts.append(context)
            return '{"type":"finish","message":"continued after denial"}'

    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", ContinuingProvider)
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    store.append_audit(
        waiting.id,
        "provider_configured",
        {"mode": "live", "base_url": "https://njusehub.info/v1", "model": "glm-5.2"},
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(f"/approvals/{waiting.pending_approval_id}/deny", follow_redirects=True)
    events = store.list_audit(waiting.id)

    assert response.status_code == 200
    assert "continued after denial" in response.text
    assert contexts[0]["observations"][0]["feedback_kind"] == "approval_denied"
    assert any(event.event_type == "approval_denied" for event in events)
    assert not any(event.event_type == "approval_recovery_ended" for event in events)
    assert store.get_approval(waiting.pending_approval_id).status == "denied"


def test_stopping_live_approval_ends_without_calling_provider(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials("stored-live-secret")
    constructed = []

    class ContinuingProvider:
        def __init__(self, *args, **kwargs):
            constructed.append({"args": args, "kwargs": kwargs})

        def complete(self, context):
            return '{"type":"finish","message":"continued unexpectedly"}'

    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", ContinuingProvider)
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    store.append_audit(
        waiting.id,
        "provider_configured",
        {"mode": "live", "base_url": "https://njusehub.info/v1", "model": "glm-5.2"},
    )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(f"/approvals/{waiting.pending_approval_id}/stop", follow_redirects=True)
    events = store.list_audit(waiting.id)

    assert response.status_code == 200
    assert constructed == []
    assert "continued unexpectedly" not in response.text
    assert any(event.event_type == "approval_denied" for event in events)
    assert any(event.event_type == "approval_recovery_ended" for event in events)
    assert store.get_approval(waiting.pending_approval_id).status == "denied"


def test_approvals_page_redacts_secrets_from_pending_action(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("configure", tmp_path)
    with sqlite3.connect(store.db_path) as db:
        db.execute(
            "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-secret-approval",
                session.id,
                '{"type":"write_file","path":".env","content":"sk-web-secret Bearer web-bearer password=hunter2"}',
                "environment write requires approval",
                "pending",
                "2026-07-11T00:00:00+00:00",
                None,
            ),
        )
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "[REDACTED]" in response.text
    assert "sk-web-secret" not in response.text
    assert "web-bearer" not in response.text
    assert "hunter2" not in response.text


def test_session_page_redacts_legacy_secret_task_and_trace(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    session = store.create_session("safe task", tmp_path)
    with sqlite3.connect(store.db_path) as db:
        db.execute("UPDATE sessions SET task = ? WHERE id = ?", ("password=legacy-task-secret", session.id))
        db.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            (
                "legacy-secret-event",
                session.id,
                "legacy_event",
                '{"detail":"postgres://alice:shortpw@db/prod"}',
                "2026-07-11T00:00:00+00:00",
            ),
        )

    response = TestClient(create_app(store.db_path, workspace_root=tmp_path)).get(f"/sessions/{session.id}")

    assert response.status_code == 200
    assert "[REDACTED]" in response.text
    assert "legacy-task-secret" not in response.text
    assert "shortpw" not in response.text


def test_approving_action_executes_it_and_ends_recovery_round(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(f"/approvals/{waiting.pending_approval_id}/approve", follow_redirects=True)

    assert response.status_code == 200
    assert "approval_recovery_ended" in response.text
    assert (tmp_path / ".env").read_text() == "MODE=prod"


def test_live_approval_resume_reuses_saved_provider_and_continues_loop(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials("stored-live-secret")
    constructed = []
    responses = [
        '{"type":"write_file","path":".env","content":"MODE=prod"}',
        '{"type":"finish","message":"live approval completed"}',
    ]

    class FakeProvider:
        def __init__(self, base_url: str, model: str, api_key: str, timeout: float):
            constructed.append({"base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout})

        def complete(self, context):
            return responses.pop(0)

    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", FakeProvider)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))
    client.post(
        "/settings",
        data={"mode": "live", "base_url": "https://njusehub.info/v1", "model": "glm-5.2"},
    )
    waiting_response = client.post(
        "/sessions",
        data={"task": "configure production"},
        follow_redirects=True,
    )
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = store.list_sessions()[0]

    response = client.post(f"/approvals/{waiting.pending_approval_id}/approve", follow_redirects=True)

    assert waiting_response.status_code == 200
    assert response.status_code == 200
    assert "live approval completed" in response.text
    assert "approval_recovery_ended" not in response.text
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "MODE=prod"
    assert constructed == [
        {
            "base_url": "https://njusehub.info/v1",
            "model": "glm-5.2",
            "api_key": "stored-live-secret",
            "timeout": 30.0,
        },
        {
            "base_url": "https://njusehub.info/v1",
            "model": "glm-5.2",
            "api_key": "stored-live-secret",
            "timeout": 30.0,
        },
    ]


def test_live_approval_resume_reuses_unsaved_submitted_key_without_persisting_it(tmp_path: Path, monkeypatch):
    credentials = _FakeCredentials(None)
    constructed = []
    responses = [
        '{"type":"write_file","path":".env","content":"MODE=prod"}',
        '{"type":"finish","message":"unsaved key resumed"}',
    ]

    class FakeProvider:
        def __init__(self, base_url: str, model: str, api_key: str, timeout: float):
            constructed.append({"base_url": base_url, "model": model, "api_key": api_key, "timeout": timeout})

        def complete(self, context):
            return responses.pop(0)

    monkeypatch.setattr("guarded_harness.web.app._credential_store", lambda: credentials)
    monkeypatch.setattr("guarded_harness.web.app.OpenAICompatibleProvider", FakeProvider)
    client = TestClient(create_app(tmp_path / "state.sqlite3", workspace_root=tmp_path))
    waiting_response = client.post(
        "/sessions",
        data={
            "task": "configure production",
            "mode": "live",
            "base_url": "https://njusehub.info/v1",
            "model": "glm-5.2",
            "api_key": "temporary-live-secret",
        },
        follow_redirects=True,
    )
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = store.list_sessions()[0]

    response = client.post(f"/approvals/{waiting.pending_approval_id}/approve", follow_redirects=True)

    assert waiting_response.status_code == 200
    assert response.status_code == 200
    assert "unsaved key resumed" in response.text
    assert credentials.key is None
    assert "temporary-live-secret" not in response.text
    assert "temporary-live-secret" not in (tmp_path / "state.sqlite3").read_bytes().decode("utf-8", errors="ignore")
    assert constructed == [
        {
            "base_url": "https://njusehub.info/v1",
            "model": "glm-5.2",
            "api_key": "temporary-live-secret",
            "timeout": 30.0,
        },
        {
            "base_url": "https://njusehub.info/v1",
            "model": "glm-5.2",
            "api_key": "temporary-live-secret",
            "timeout": 30.0,
        },
    ]


def test_web_can_mark_executing_approval_failed(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3", workspace_root=tmp_path)
    waiting = AgentLoop.for_workspace(
        tmp_path,
        MockLLM(['{"type":"write_file","path":".env","content":"MODE=prod"}']),
        store,
    ).run("configure production")
    store.begin_approval_resolution(waiting.pending_approval_id, approved=True)
    client = TestClient(create_app(store.db_path, workspace_root=tmp_path))

    response = client.post(
        f"/approvals/{waiting.pending_approval_id}/mark-failed",
        data={"reason": "crashed worker"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert store.get_approval(waiting.pending_approval_id).status == "failed"
    assert "approval_manually_failed" in response.text


class _FakeCredentials:
    def __init__(self, key: str | None):
        self.key = key

    def get_key(self) -> str | None:
        return self.key

    def set_key(self, key: str) -> None:
        self.key = key

    def status(self) -> bool:
        return self.key is not None


class _FinishingProvider:
    def __init__(self, *args, **kwargs):
        pass

    def complete(self, context):
        return '{"type":"finish","message":"done"}'
