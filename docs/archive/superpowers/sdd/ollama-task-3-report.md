# Task 3 Report: Hide Guardrail Demo from Primary UI

## Status

COMPLETE

## Requirements

- Verified `GET /guardrail` and `POST /guardrail` remain available.
- Verified the primary navigation in `index.html`, `settings.html`, `session.html`, and `approvals.html` contains no `/guardrail` link.
- Removed the index dashboard `Change configuration` CTA required by the task's explicit home-page contract.
- Renamed and expanded the home-page integration test to cover the required Chat Workspace, Provider Settings, Approvals, hidden Guardrail Demo, hidden configuration CTA, model, and API-key assertions.
- Kept direct guardrail demo evaluation coverage unchanged.

## TDD Evidence

The updated home-page test initially failed because `Change configuration` was still rendered in `index.html`. After removing that CTA, the focused test passed.

## Test Results

Targeted command:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py::test_index_loads_chat_workspace_without_guardrail_nav tests/integration/test_web.py::test_guardrail_demo_page_evaluates_sample_actions -q
```

Result: `2 passed, 1 warning`.

Full web integration:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Result: `20 passed, 1 warning`.

The warning is the existing Starlette/httpx deprecation warning.

## Commit

`e143b47 feat: hide guardrail demo from primary web ui`
