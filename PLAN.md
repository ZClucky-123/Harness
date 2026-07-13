# Guarded Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个 Python + FastAPI + Typer CLI 的本地 coding-agent harness，重点实现确定性治理护栏与 HITL 审批状态机。

**Architecture:** 同一套 `guarded_harness` 核心同时服务 CLI 和 WebUI。LLM 只输出结构化 action；agent loop 自己完成解析、策略判定、工具分发、反馈回灌、记忆和审计。核心机制必须能用 `MockLLM` 离线测试。

**Tech Stack:** Python 3.11+, FastAPI, Typer, pytest, SQLite, keyring optional, Docker, GitLab CI.

## Global Constraints

- 交付物不得基于 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex agent runner 或编码智能体 SDK 的高层循环。
- 核心机制必须可以替换为 mock/stub LLM 后确定性单测。
- 默认 mock 模式不得依赖网络和真实 LLM。
- API key 不得硬编码、不得提交、不得出现在日志、审计事件、CLI 输出或 WebUI 页面中。
- 所有文件和 shell action 必须受 workspace root 边界约束。
- Docker 是正式分发方式。
- `.gitlab-ci.yml` 必须包含名为 `unit-test` 的 job。
- WebUI 保持最小可用：任务输入、session trace、审批列表、approve/deny、最终结果。

---

## File Structure

```text
pyproject.toml
README.md
SPEC_PROCESS.md
AGENT_LOG.md
.gitignore
.gitlab-ci.yml
Dockerfile
src/guarded_harness/
  __init__.py
  cli.py
  core/
    __init__.py
    actions.py
    observations.py
    loop.py
    sessions.py
  llm/
    __init__.py
    base.py
    mock.py
    openai_compatible.py
  tools/
    __init__.py
    dispatcher.py
    filesystem.py
    shell.py
    tests.py
  governance/
    __init__.py
    guardrail.py
    policies.py
    approvals.py
    audit.py
  memory/
    __init__.py
    store.py
  config/
    __init__.py
    schema.py
    loader.py
    credentials.py
  web/
    __init__.py
    app.py
    templates/
      index.html
      session.html
      approvals.html
    static/
      styles.css
tests/
  unit/
  integration/
  fixtures/
demo/
  README.md
```

---

### Task 1: 项目骨架、依赖和基础类型

**Files:**
- Create: `pyproject.toml`
- Create: `src/guarded_harness/__init__.py`
- Create: `src/guarded_harness/core/actions.py`
- Create: `src/guarded_harness/core/observations.py`
- Create: `src/guarded_harness/core/sessions.py`
- Create: `tests/unit/test_actions.py`
- Create: `.gitignore`

**Interfaces:**
- Produces: `Action`, `ActionType`, `parse_action(raw: str) -> Action`
- Produces: `Observation`, `FeedbackKind`
- Produces: `SessionStatus`, `SessionState`

- [x] **Step 1: Write failing parser and model tests**

Create `tests/unit/test_actions.py`:

```python
import pytest

from guarded_harness.core.actions import ActionType, parse_action


def test_parse_read_file_action():
    action = parse_action('{"type":"read_file","path":"README.md"}')

    assert action.type == ActionType.READ_FILE
    assert action.payload == {"path": "README.md"}


def test_parse_unknown_action_fails_deterministically():
    with pytest.raises(ValueError, match="unknown action type"):
        parse_action('{"type":"teleport","path":"README.md"}')


def test_parse_invalid_json_fails_deterministically():
    with pytest.raises(ValueError, match="invalid action json"):
        parse_action("{not json")
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_actions.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'guarded_harness'`.

- [x] **Step 3: Add packaging and model implementation**

Create `pyproject.toml` with package metadata and dependencies:

```toml
[project]
name = "guarded-harness"
version = "0.1.0"
description = "A guarded local coding-agent harness with deterministic HITL governance."
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "typer>=0.12",
  "jinja2>=3.1",
  "python-multipart>=0.0.9",
  "keyring>=25.0",
  "httpx>=0.27",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
]

[project.scripts]
harness = "guarded_harness.cli:app"

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `.gitignore`:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
dist/
build/
*.egg-info/
.env
*.sqlite3
.guarded-harness/
```

Create `src/guarded_harness/core/actions.py` with `ActionType`, frozen `Action`, and `parse_action`.

Create `src/guarded_harness/core/observations.py` with `FeedbackKind` enum and frozen `Observation`.

Create `src/guarded_harness/core/sessions.py` with `SessionStatus` enum and `SessionState`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_actions.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/guarded_harness tests/unit/test_actions.py
git commit -m "feat: scaffold core action models"
```

---

### Task 2: SQLite 存储、审计日志、审批记录和记忆

**Files:**
- Create: `src/guarded_harness/governance/audit.py`
- Create: `src/guarded_harness/governance/approvals.py`
- Create: `src/guarded_harness/memory/store.py`
- Modify: `src/guarded_harness/core/sessions.py`
- Test: `tests/unit/test_store.py`

**Interfaces:**
- Consumes: `SessionState`, `SessionStatus`
- Produces: `SQLiteStore(db_path: Path)`
- Produces: `create_session(task: str, workspace: Path) -> SessionState`
- Produces: `append_audit(session_id: str, event_type: str, payload: dict) -> None`
- Produces: `create_approval(session_id: str, action_json: str, reason: str) -> ApprovalRequest`
- Produces: `resolve_approval(approval_id: str, approved: bool) -> ApprovalRequest`
- Produces: `add_memory(kind: str, content: str, tags: list[str]) -> MemoryEntry`

- [x] **Step 1: Write failing persistence tests**

Create `tests/unit/test_store.py`:

```python
from pathlib import Path

from guarded_harness.memory.store import SQLiteStore


def test_create_session_and_audit_event(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3")
    session = store.create_session("fix tests", tmp_path)

    store.append_audit(session.id, "session_created", {"task": "fix tests"})
    events = store.list_audit(session.id)

    assert session.task == "fix tests"
    assert events[0].event_type == "session_created"
    assert events[0].payload["task"] == "fix tests"


def test_create_and_resolve_approval(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3")
    session = store.create_session("publish", tmp_path)
    approval = store.create_approval(session.id, '{"type":"run_shell"}', "git push requires approval")

    resolved = store.resolve_approval(approval.id, approved=False)

    assert approval.status == "pending"
    assert resolved.status == "denied"


def test_memory_round_trip(tmp_path: Path):
    store = SQLiteStore(tmp_path / "state.sqlite3")
    store.add_memory("decision", "Never edit .env without approval", ["policy"])

    entries = store.list_memory(limit=5)

    assert entries[0].content == "Never edit .env without approval"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_store.py -q`

Expected: FAIL with `ModuleNotFoundError` or missing `SQLiteStore`.

- [x] **Step 3: Implement SQLite schema and dataclasses**

Implement tables in `SQLiteStore._init_schema()`:

```sql
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  task TEXT NOT NULL,
  workspace TEXT NOT NULL,
  status TEXT NOT NULL,
  step_count INTEGER NOT NULL,
  pending_approval_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  action_json TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS memory_entries (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  tags TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_store.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/governance src/guarded_harness/memory src/guarded_harness/core/sessions.py tests/unit/test_store.py
git commit -m "feat: add sqlite state store"
```

---

### Task 3: Guardrail 策略与 workspace 边界

**Files:**
- Create: `src/guarded_harness/governance/policies.py`
- Create: `src/guarded_harness/governance/guardrail.py`
- Test: `tests/unit/test_guardrail.py`

**Interfaces:**
- Consumes: `Action`, `ActionType`
- Produces: `DecisionType` enum: `ALLOW`, `DENY`, `NEEDS_APPROVAL`
- Produces: `PolicyDecision(decision: DecisionType, risk_level: str, reason: str)`
- Produces: `Guardrail(workspace_root: Path).evaluate(action: Action) -> PolicyDecision`

- [x] **Step 1: Write failing guardrail tests**

Create `tests/unit/test_guardrail.py`:

```python
from pathlib import Path

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.governance.guardrail import Guardrail
from guarded_harness.governance.policies import DecisionType


def test_deny_rm_rf_root(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "rm -rf /"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.DENY
    assert "destructive" in decision.reason


def test_require_approval_for_git_push(tmp_path: Path):
    action = Action(ActionType.RUN_SHELL, {"command": "git push origin main"})

    decision = Guardrail(tmp_path).evaluate(action)

    assert decision.decision == DecisionType.NEEDS_APPROVAL
    assert "approval" in decision.reason


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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_guardrail.py -q`

Expected: FAIL with missing `Guardrail`.

- [x] **Step 3: Implement policy rules**

Implement:

- command normalization with `shlex.split`
- destructive denies for `rm -rf /`, `format`, `mkfs`, `del /s`, `Remove-Item -Recurse -Force C:\`
- approval for `git push`, `pip install`, `npm install`, `twine upload`, `docker push`, file deletion inside workspace, `.env` modification
- path resolution with `Path.resolve()` and prefix check against `workspace_root.resolve()`

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_guardrail.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/governance/policies.py src/guarded_harness/governance/guardrail.py tests/unit/test_guardrail.py
git commit -m "feat: add deterministic guardrail policies"
```

---

### Task 4: Tool Dispatcher、文件工具、shell 工具与测试工具

**Files:**
- Create: `src/guarded_harness/tools/filesystem.py`
- Create: `src/guarded_harness/tools/shell.py`
- Create: `src/guarded_harness/tools/tests.py`
- Create: `src/guarded_harness/tools/dispatcher.py`
- Test: `tests/unit/test_dispatcher.py`

**Interfaces:**
- Consumes: `Action`, `Observation`
- Produces: `ToolDispatcher(workspace_root: Path, test_command: list[str])`
- Produces: `dispatch(action: Action) -> Observation`

- [x] **Step 1: Write failing dispatcher tests**

Create `tests/unit/test_dispatcher.py`:

```python
from pathlib import Path

from guarded_harness.core.actions import Action, ActionType
from guarded_harness.core.observations import FeedbackKind
from guarded_harness.tools.dispatcher import ToolDispatcher


def test_write_and_read_file(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    write_obs = dispatcher.dispatch(Action(ActionType.WRITE_FILE, {"path": "hello.txt", "content": "hi"}))
    read_obs = dispatcher.dispatch(Action(ActionType.READ_FILE, {"path": "hello.txt"}))

    assert write_obs.success is True
    assert read_obs.stdout == "hi"


def test_run_shell_success(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "python -c \"print('ok')\""}))

    assert obs.success is True
    assert obs.feedback_kind == FeedbackKind.TOOL_SUCCESS
    assert "ok" in obs.stdout


def test_run_shell_command_error(tmp_path: Path):
    dispatcher = ToolDispatcher(tmp_path, test_command=["python", "-c", "print('ok')"])

    obs = dispatcher.dispatch(Action(ActionType.RUN_SHELL, {"command": "python -c \"raise SystemExit(2)\""}))

    assert obs.success is False
    assert obs.feedback_kind == FeedbackKind.COMMAND_ERROR
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_dispatcher.py -q`

Expected: FAIL with missing dispatcher.

- [x] **Step 3: Implement tools**

Implement file read/write with workspace path resolution.

Implement shell execution with:

```python
subprocess.run(
    command,
    cwd=workspace_root,
    shell=True,
    text=True,
    capture_output=True,
    timeout=30,
)
```

Return `Observation(success=returncode == 0, feedback_kind=...)`.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_dispatcher.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/tools tests/unit/test_dispatcher.py
git commit -m "feat: add guarded tool dispatcher"
```

---

### Task 5: LLM 抽象、MockLLM 与 agent loop

**Files:**
- Create: `src/guarded_harness/llm/base.py`
- Create: `src/guarded_harness/llm/mock.py`
- Create: `src/guarded_harness/llm/openai_compatible.py`
- Create: `src/guarded_harness/core/loop.py`
- Test: `tests/integration/test_loop_guardrail.py`
- Test: `tests/integration/test_loop_feedback.py`

**Interfaces:**
- Consumes: `Guardrail`, `ToolDispatcher`, `SQLiteStore`
- Produces: `LLMProvider.complete(context: dict) -> str`
- Produces: `MockLLM(responses: list[str])`
- Produces: `AgentLoop.run(task: str) -> SessionState`
- Produces: `AgentLoop.resume_after_approval(approval_id: str, approved: bool) -> SessionState`

- [x] **Step 1: Write failing integration tests**

Create `tests/integration/test_loop_guardrail.py`:

```python
from pathlib import Path

from guarded_harness.core.sessions import SessionStatus
from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def test_loop_denies_dangerous_action(tmp_path: Path):
    llm = MockLLM(['{"type":"run_shell","command":"rm -rf /"}', '{"type":"finish","message":"stopped"}'])
    loop = AgentLoop.for_workspace(tmp_path, llm, SQLiteStore(tmp_path / "state.sqlite3"), max_steps=2)

    session = loop.run("try a dangerous command")
    events = loop.store.list_audit(session.id)

    assert session.status == SessionStatus.FINISHED
    assert any(event.event_type == "policy_denied" for event in events)
```

Create `tests/integration/test_loop_feedback.py`:

```python
from pathlib import Path

from guarded_harness.core.sessions import SessionStatus
from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def test_feedback_changes_next_mock_action(tmp_path: Path):
    llm = MockLLM([
        '{"type":"run_shell","command":"python -c \\"raise SystemExit(2)\\""}',
        '{"type":"finish","message":"changed action after command_error"}',
    ])
    loop = AgentLoop.for_workspace(tmp_path, llm, SQLiteStore(tmp_path / "state.sqlite3"), max_steps=3)

    session = loop.run("recover from failure")
    events = loop.store.list_audit(session.id)

    assert session.status == SessionStatus.FINISHED
    assert any("command_error" in str(event.payload) for event in events)
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_loop_guardrail.py tests/integration/test_loop_feedback.py -q`

Expected: FAIL with missing `AgentLoop`.

- [x] **Step 3: Implement loop**

Implement `AgentLoop.run()`:

1. create session
2. build context with task, memory, observations
3. call LLM
4. parse action
5. evaluate guardrail
6. execute or pause/deny
7. append audit events
8. stop on finish, waiting approval, failed, blocked, max steps

Implement `MockLLM` as an ordered response queue and store received contexts for assertions.

Implement `openai_compatible.py` as optional provider using `httpx`, reading key through credential layer later.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_loop_guardrail.py tests/integration/test_loop_feedback.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/llm src/guarded_harness/core/loop.py tests/integration
git commit -m "feat: add mockable agent loop"
```

---

### Task 6: HITL 审批暂停、恢复和拒绝回灌

**Files:**
- Modify: `src/guarded_harness/core/loop.py`
- Modify: `src/guarded_harness/governance/approvals.py`
- Modify: `src/guarded_harness/memory/store.py`
- Test: `tests/integration/test_hitl.py`

**Interfaces:**
- Consumes: `AgentLoop.run`, `AgentLoop.resume_after_approval`
- Produces: persisted pending approval state
- Produces: deny feedback as `approval_denied`

- [x] **Step 1: Write failing HITL tests**

Create `tests/integration/test_hitl.py`:

```python
from pathlib import Path

from guarded_harness.core.sessions import SessionStatus
from guarded_harness.core.loop import AgentLoop
from guarded_harness.llm.mock import MockLLM
from guarded_harness.memory.store import SQLiteStore


def test_git_push_pauses_for_approval(tmp_path: Path):
    llm = MockLLM(['{"type":"run_shell","command":"git push origin main"}'])
    loop = AgentLoop.for_workspace(tmp_path, llm, SQLiteStore(tmp_path / "state.sqlite3"), max_steps=2)

    session = loop.run("publish")
    approvals = loop.store.list_pending_approvals()

    assert session.status == SessionStatus.WAITING_APPROVAL
    assert len(approvals) == 1
    assert "git push" in approvals[0].action_json


def test_deny_approval_feeds_back_and_finishes(tmp_path: Path):
    llm = MockLLM([
        '{"type":"run_shell","command":"git push origin main"}',
        '{"type":"finish","message":"will not publish"}',
    ])
    loop = AgentLoop.for_workspace(tmp_path, llm, SQLiteStore(tmp_path / "state.sqlite3"), max_steps=3)

    waiting = loop.run("publish")
    approval = loop.store.list_pending_approvals()[0]
    session = loop.resume_after_approval(approval.id, approved=False)
    events = loop.store.list_audit(waiting.id)

    assert session.status == SessionStatus.FINISHED
    assert any("approval_denied" in str(event.payload) for event in events)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_hitl.py -q`

Expected: FAIL because resume or approval listing is incomplete.

- [x] **Step 3: Implement HITL persistence and resume**

Implement:

- `list_pending_approvals()`
- storing paused action JSON on approval creation
- session `pending_approval_id`
- `resume_after_approval(approval_id, approved=True)` executes paused action
- `resume_after_approval(approval_id, approved=False)` appends `approval_denied` observation and continues the LLM loop

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_hitl.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/core/loop.py src/guarded_harness/governance/approvals.py src/guarded_harness/memory/store.py tests/integration/test_hitl.py
git commit -m "feat: implement hitl approval state machine"
```

---

### Task 7: CLI、凭据管理和机制演示

**Files:**
- Create: `src/guarded_harness/cli.py`
- Create: `src/guarded_harness/config/credentials.py`
- Create: `src/guarded_harness/config/schema.py`
- Create: `src/guarded_harness/config/loader.py`
- Create: `demo/README.md`
- Test: `tests/integration/test_cli.py`

**Interfaces:**
- Consumes: `AgentLoop`, `SQLiteStore`
- Produces: Typer app `app`
- Produces: commands `demo guardrail`, `demo hitl`, `demo feedback`, `approvals list`, `approvals approve`, `approvals deny`
- Produces: `CredentialStore.set_key`, `CredentialStore.status`, `CredentialStore.clear_key`

- [x] **Step 1: Write failing CLI tests**

Create `tests/integration/test_cli.py`:

```python
from typer.testing import CliRunner

from guarded_harness.cli import app


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
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_cli.py -q`

Expected: FAIL with missing `cli.py`.

- [x] **Step 3: Implement CLI**

Implement Typer command groups:

- `demo guardrail`
- `demo hitl`
- `demo feedback`
- `approvals list`
- `approvals approve <id>`
- `approvals deny <id>`
- `credentials set`
- `credentials status`
- `credentials clear`
- `run "<task>"`
- `serve`

Credential status must print only configured/not configured, never key value.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_cli.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/cli.py src/guarded_harness/config demo/README.md tests/integration/test_cli.py
git commit -m "feat: add cli demos and credentials"
```

---

### Task 8: FastAPI WebUI

**Files:**
- Create: `src/guarded_harness/web/app.py`
- Create: `src/guarded_harness/web/templates/index.html`
- Create: `src/guarded_harness/web/templates/session.html`
- Create: `src/guarded_harness/web/templates/approvals.html`
- Create: `src/guarded_harness/web/static/styles.css`
- Test: `tests/integration/test_web.py`

**Interfaces:**
- Consumes: `AgentLoop`, `SQLiteStore`
- Produces: `create_app(store_path: Path | None = None) -> FastAPI`
- Produces: routes `GET /`, `POST /sessions`, `GET /sessions/{id}`, `GET /approvals`, `POST /approvals/{id}/approve`, `POST /approvals/{id}/deny`

- [x] **Step 1: Write failing WebUI tests**

Create `tests/integration/test_web.py`:

```python
from fastapi.testclient import TestClient

from guarded_harness.web.app import create_app


def test_index_loads():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "Guarded Harness" in response.text


def test_approvals_page_loads():
    client = TestClient(create_app())

    response = client.get("/approvals")

    assert response.status_code == 200
    assert "Approvals" in response.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_web.py -q`

Expected: FAIL with missing web app.

- [x] **Step 3: Implement minimal WebUI**

Implement simple server-rendered HTML pages:

- index with task form
- session page with trace
- approvals page with approve/deny buttons

Do not add a large frontend build system.

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_web.py -q`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guarded_harness/web tests/integration/test_web.py
git commit -m "feat: add minimal approval webui"
```

---

### Task 9: Docker、CI、README、过程文档和最终验证

**Files:**
- Modify: `README.md`
- Create: `.gitlab-ci.yml`
- Create: `Dockerfile`
- Create: `SPEC_PROCESS.md`
- Create: `AGENT_LOG.md`
- Modify: `PLAN.md`
- Modify: `docs/superpowers/plans/2026-07-10-guarded-harness.md`

**Interfaces:**
- Consumes: all previous tasks
- Produces: documented install/run/test/Docker/security instructions
- Produces: CI `unit-test` job

- [x] **Step 1: Write CI and Docker smoke expectations**

Create `.gitlab-ci.yml`:

```yaml
stages:
  - test
  - build

unit-test:
  stage: test
  image: python:3.11-slim
  script:
    - python -m pip install --upgrade pip
    - pip install -e ".[dev]"
    - pytest
    - python -m compileall src

docker-build:
  stage: build
  image: docker:27
  services:
    - docker:27-dind
  script:
    - docker build -t guarded-harness .
  rules:
    - if: '$CI_COMMIT_BRANCH'
```

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "guarded_harness.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [x] **Step 2: Update README**

README must include:

- project introduction
- installation
- local CLI run
- WebUI run
- Docker build/run
- mock mode demos
- credential setup and `.env` risk
- safety boundaries
- directory structure
- known limitations
- third-party licenses summary

- [x] **Step 3: Create process documents**

Create `SPEC_PROCESS.md` with:

- brainstorming key questions
- why Python + FastAPI + Typer was selected
- why governance + HITL became main contribution
- why Docker was selected
- at least 3 key iterations from this session
- cold-start validation section reserved for later results

Create `AGENT_LOG.md` with current entries:

- initial document reading
- brainstorming skill usage
- writing-plans skill usage
- design spec commits `5641349` and `969e4ff`

- [x] **Step 4: Run full local verification**

Run:

```bash
pytest
python -m compileall src
docker build -t guarded-harness .
```

Expected:

- all tests PASS
- compileall exits 0
- Docker image builds

- [x] **Step 5: Commit**

```bash
git add README.md .gitlab-ci.yml Dockerfile SPEC_PROCESS.md AGENT_LOG.md PLAN.md docs/superpowers/plans/2026-07-10-guarded-harness.md
git commit -m "docs: add distribution ci and process documentation"
```

---

## Execution Notes

- 每个 task 完成后更新 `PLAN.md` 对应 checkbox，并在 `AGENT_LOG.md` 记录技能、关键上下文、commit hash 和人工干预。
- 实现阶段必须先使用 `superpowers:using-git-worktrees` 检查隔离工作区。
- 实现每个 task 时必须使用 `superpowers:test-driven-development`，先写失败测试，再写实现。
- 完成每个 task 后使用 code review 流程检查：先 spec 合规，再代码质量。
- 正式实现前需进行课程要求的冷启动验证：让不同类型 agent 仅凭 `SPEC.md` + `PLAN.md` 尝试 1-2 个 task，并把结果记录到 `SPEC_PROCESS.md`。

---

## Task 12: ChatGPT-like WebUI Layout Polish

**Started:** 2026-07-13 01:26:06 +08:00

**Subagent:** Codex(main)

**Manual intervention:** User requested five screenshot-driven UI changes: simplify approval links, remove copy command, pin sidebar to the left with independent scrolling, align chat content and composer widths, and tune global horizontal spacing.

**Files:**
- Modify: `src/guarded_harness/web/templates/index.html`
- Modify: `src/guarded_harness/web/templates/session.html`
- Modify: `src/guarded_harness/web/templates/approvals.html`
- Modify: `src/guarded_harness/web/static/styles.css`
- Modify: `tests/integration/test_web.py`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

- [x] **Step 1: Record task start and workflow requirements**
  - Commit: `72877ec`
- [x] **Step 2: Add failing WebUI tests for links, fixed sidebar, aligned composer, and spacing**
  - Commit: `33ecf68`
- [x] **Step 3: Implement templates and CSS**
  - Commit: `33ecf68`
- [x] **Step 4: Run focused and full verification**
  - Commit: `33ecf68`
- [x] **Step 5: Record final commit hashes and lessons**
  - Commit: `543f6e1`
- [x] **Step 6: Push branch and open PR**
  - Status: blocked until user explicitly approves exporting branch `feature/guarded-harness-impl` to remote `https://github.com/ZClucky-123/Harness.git`
  - Commit: pending

---

## Task 13: Chat Conversation Order and Sidebar Header Polish

**Started:** 2026-07-13 01:44:24 +08:00

**Subagent:** Codex(main)

**Manual intervention:** User approved four screenshot-driven corrections: right-side conversation should show newest messages at the bottom, composer should be white and grow upward with send button at the lower-right, left sidebar needs an actual independent scroll area, and `Guarded Harness` should move into the sidebar header on session pages.

**Files:**
- Modify: `src/guarded_harness/web/app.py`
- Modify: `src/guarded_harness/web/templates/index.html`
- Modify: `src/guarded_harness/web/templates/session.html`
- Modify: `src/guarded_harness/web/static/styles.css`
- Modify: `tests/integration/test_web.py`
- Modify: `PLAN.md`
- Modify: `AGENT_LOG.md`

- [x] **Step 1: Record task start and workflow requirements**
  - Commit: `7e07cb7`
- [x] **Step 2: Add failing WebUI tests for conversation order, composer behavior, sidebar scroll, and sidebar brand**
  - Commit: `4534a00`
- [x] **Step 3: Implement view-model, templates, and CSS**
  - Commit: `4534a00`
- [x] **Step 4: Run focused and full verification**
  - Commit: `4534a00`
- [x] **Step 5: Record final commit hashes and lessons**
  - Commit: `385b0a5`
