# Task 4: Apply Ollama Visual System Report

## Scope

Applied the Ollama-style white, pill, and hairline visual system to the five web templates and shared stylesheet. The existing Jinja rendering, endpoints, form actions, and field names remain unchanged.

## Implementation

- Replaced the terminal visual language with the required `shell`, `site-header`, `brand`, `nav-links`, `hero`, `status-pills`, `pill`, `chat-panel`, `message`, `composer`, `terminal-card`, `traffic-lights`, `queue-grid`, and `queue-card` structures.
- Used narrow shells for the workspace, settings, and session pages, plus the wide shell for approvals and the direct-only guardrail demo.
- Kept `/guardrail` available without adding it to primary navigation.
- Retained API-key masking and the existing `pretty_json` rendering for readable Chinese JSON.
- Added the required integration assertions for chat workspace and approvals structure.

## TDD Evidence

1. Added the brief's new structural assertions to `tests/integration/test_web.py`.
2. Ran the focused tests before styling. The workspace assertion failed because `chat-panel` was not yet rendered; approvals already had `queue-grid`.
3. Implemented the template and CSS changes.
4. Ran the full integration test file. A regression in the approvals status heading was found and corrected by restoring `[pending]`, `[executing]`, and `[failed]` labels.

## Verification

Command:

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/test_web.py -q
```

Result: 20 passed, 1 existing TestClient deprecation warning.

## Self-Review

- `git diff --check` completed without whitespace errors.
- All required template classes are defined in `styles.css` and used by the affected pages.
- No API key values are rendered into templates.
- Existing form names and routes remain unchanged.

## Commit

Implementation: `0316f18 feat: apply ollama web ui styling`.

## Review Fix: Guardrail Shell Width

- Changed the direct `/guardrail` demo from `class="shell wide"` to `class="shell"`; the wide shell remains reserved for approvals.
- Added an integration assertion covering the direct guardrail page shell class.
- Verification: `.venv\\Scripts\\python.exe -m pytest tests/integration/test_web.py::test_primary_navigation_omits_guardrail_link_but_direct_page_loads -q` passed (1 passed).
- Verification: `.venv\\Scripts\\python.exe -m pytest tests/integration/test_web.py -q` passed (20 passed, 1 existing TestClient deprecation warning).
