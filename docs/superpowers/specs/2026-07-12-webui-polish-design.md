# Web UI Polish Design

## Goal

Fix Chinese display in the Web UI and make the FastAPI pages visually align with the OpenCode-inspired design reference.

## Design

- Add a Jinja JSON display filter that uses `ensure_ascii=False` so trace payloads display Chinese text directly instead of `\uXXXX` escapes.
- Keep persistence unchanged; this is a rendering fix.
- Apply one visual language across the index, session, and approvals pages:
  - cream canvas,
  - monospace typography,
  - dark terminal hero panels,
  - ASCII bracket labels,
  - 4px form controls and buttons,
  - hairline bordered trace/approval rows.

## Acceptance Criteria

- A Chinese task and Chinese trace payload render as readable Chinese in the session page.
- Approval reasons and action JSON containing Chinese render as readable Chinese.
- Pages retain the existing task creation, live provider, session trace, and HITL approval workflows.
- Full pytest passes.

## Process Note

This change improves demonstration usability only. It does not alter the harness core, guardrails, HITL state machine, or credential storage semantics.
