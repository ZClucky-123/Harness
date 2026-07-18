# Fixed Composer Follow-up Plan

## Task

- [x] Add failing tests for fixed composer, composer provider status, circular submit button, and removed visible Task/Start task text.
- [x] Verify the tests fail against the previous normal-flow composer.
- [x] Move provider status from the chat stream into the composer.
- [x] Replace the visible submit text with a small circular submit control.
- [x] Shrink the textarea and composer footprint.
- [x] Run focused tests, full tests, compile check, diff check, review, and commit.

## Verification Commands

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_chat_workspace_css_uses_global_scroll_and_compact_composer -q
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m compileall src tests
git diff --check
```
