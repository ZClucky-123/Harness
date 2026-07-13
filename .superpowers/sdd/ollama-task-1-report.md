# Task 1 Report: Store Recent Sessions

## Status

DONE_WITH_CONCERNS

## Requirements

- Added `SQLiteStore.list_sessions(limit: int = 20) -> list[SessionState]`.
- Ordered sessions by `updated_at DESC, created_at DESC`.
- Added WebUI conversation item helpers and session summaries.
- Updated the home page context to use `title: "Chat Workspace"` and recent conversation items.
- Rendered persisted sessions, summaries, status, step count, and trace links in `index.html`.
- Added the required integration test for recent-session rendering and newest-first ordering.

## TDD Evidence

The required test was added before the production changes and initially failed because the home page did not contain `Chat Workspace` or persisted sessions. After the store, route, helper, and template changes, the same focused test passed.

Focused command:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
```

Result: `1 passed, 1 warning`.

## Broader Test Result

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Result: `17 passed, 1 failed, 1 warning`.

The failing pre-existing `test_index_loads` expects `deepseek-v4-flash`, but this worktree contains `.guarded-harness/provider.json` configured with model `glm-5.2`. The home page renders the persisted provider setting, and no provider-setting behavior was changed for this task. The warning is the existing Starlette/httpx deprecation warning.

## Commit

The implementation and this report are committed in the task commit returned with the completion status.

## Review Fixes

- Redacted recent-session finished and guardrail-denial summaries before rendering them on the home page.
- Removed `/guardrail` from the home page primary navigation while keeping the route covered and working.
- Isolated `test_index_loads` with `tmp_path` and updated it for Chat Workspace expectations.
- Added coverage proving a secret in a finished-session summary is absent from `/` and `[REDACTED]` is present.

Focused review-fix tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
```

Result: `2 passed, 1 warning`.

Full web integration tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Result: `19 passed, 1 warning`.

## Task 1 Re-review Fix

- Removed `/guardrail` from the primary navigation in the settings, approvals, and session templates.
- Kept direct `/guardrail` access available.
- Added integration coverage proving those three primary navigations omit the link while direct `/guardrail` still loads.

Focused re-review tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_provider_settings_page_loads_defaults tests/integration/test_web.py::test_approvals_page_loads tests/integration/test_web.py::test_session_page_preserves_chinese_text_in_task_and_trace tests/integration/test_web.py::test_guardrail_demo_page_evaluates_sample_actions -q
```

Result: `4 passed, 1 warning`.

Full web integration tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Result: `20 passed, 1 warning`.
