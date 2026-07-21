# Chat App Shell Follow-up Plan

## Task

- [x] Add failing WebUI tests for app-shell classes, sticky composer marker, auto-scroll script, and oldest-to-newest session ordering.
- [x] Verify the tests fail against the previous layout and ordering.
- [x] Reverse home-page display order without changing store semantics.
- [x] Update `index.html` to use a scrollable chat app shell and native auto-scroll script.
- [x] Update CSS for sticky header/status area, scrollable messages, and sticky bottom composer.
- [x] Run focused tests, full tests, diff check, and commit.

## Verification Commands

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
.venv\Scripts\python.exe -m pytest -q
git diff --check
```
