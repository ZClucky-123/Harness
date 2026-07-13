# Global Scroll Chat Follow-up Plan

## Task

- [x] Add failing tests for global page scrolling, provider status as a chat message, no role labels, compact composer, and oldest-to-newest message order.
- [x] Verify the tests fail against the inner-scroll layout.
- [x] Update the home template to remove the inner scroll container and role labels.
- [x] Move provider state into a system message in the chat stream.
- [x] Update CSS for global page scroll and a compact composer.
- [x] Run focused tests, full tests, diff check, compile check, review, and commit.

## Verification Commands

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_chat_workspace_css_uses_global_scroll_and_compact_composer tests/integration/test_web.py::test_index_lists_recent_sessions_as_conversation_items -q
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall src tests
git diff --check
```
