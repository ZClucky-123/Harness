# Issue Backlog Fixes Design

## Context

`issue.md` lists remaining backend and WebUI defects after the initial guarded harness implementation. This batch continues after the explicit tool feedback fix.

## Scope

This batch covers:

- Live web approval resume should reuse the original live provider settings and continue the loop.
- Windows cmd built-ins such as `dir`, `type`, `del`, and `rd` must not pass guardrails when `shell=False` cannot execute them.
- OpenAI-compatible provider failures should be classified without leaking API keys or provider response bodies.
- Empty model responses should be treated as provider failures before ordinary action JSON parsing.
- The WebUI should use Chinese labels, a session sidebar, pending approval count, safe Markdown rendering, and chat-stream approval cards.

## Design Notes

- Provider metadata stored in audit events includes only mode, base URL, and model. API keys are not persisted in SQLite and are recovered through the credential store.
- Unsupported direct shell commands are identified by a shared helper in `governance.shell_command`, used by both policy and executor layers.
- Provider error messages are intentionally high-level and sanitized.
- Markdown rendering escapes HTML first and supports a conservative subset of inline/list syntax.
- Approval cards use real approval action JSON and reason from the backend, without inventing tool types.
