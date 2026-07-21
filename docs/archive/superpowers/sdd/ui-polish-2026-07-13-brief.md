# UI Polish Task Brief — 2026-07-13

## Scope

Fix multiple WebUI usability and layout issues discovered during visual testing.

## Requirements

1. **Chat session truncation**: sessions beyond 12 disappear from sidebar and conversation panel.
2. **Composer layout**: send button overlays textarea; composer misaligned with chat content; vertical spacing too tall.
3. **Message styling**: agent messages have unwanted gray background; text wraps prematurely with right-side whitespace; paragraph top/bottom spacing asymmetric.
4. **Cross-page layout**: nav links shift position when navigating between Chat / Settings / Approvals / Guardrail.
5. **Approvals page**: uses custom `approval-board` design inconsistent with other pages' `.hero` + `.panel` style.
6. **Fixed header**: "Chat Workspace" hero covered by fixed-position header.

## Files

- `src/guarded_harness/web/app.py` — `_conversation_items` limit; route context for sidebar.
- `src/guarded_harness/web/static/styles.css` — layout, composer, message, header, approvals styles.
- `src/guarded_harness/web/templates/index.html` — composer HTML structure, "Recent Sessions" heading.
- `src/guarded_harness/web/templates/settings.html` — layout conversion to chat-page.
- `src/guarded_harness/web/templates/approvals.html` — layout conversion + redesign.
- `src/guarded_harness/web/templates/guardrail.html` — layout conversion to chat-page.
- `tests/integration/test_web.py` — CSS and template assertions.

## Verification

- `git diff --check` passes.
- Test assertions updated to match new CSS values.
- Cross-page visual consistency achieved via shared `chat-page` skeleton.
