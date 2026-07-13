# Issue Backlog Fixes Plan

## Checklist

- [x] Re-read `issue.md` and identify unresolved priorities.
- [x] Add and verify failing test for live web approval resume.
- [x] Persist non-secret provider metadata and resume live approvals with the saved provider.
- [x] Add and verify failing tests for unsupported Windows cmd built-ins.
- [x] Deny unsupported cmd built-ins consistently in guardrail and executor layers.
- [x] Add and verify failing tests for provider HTTP errors, timeout, invalid JSON, and empty content.
- [x] Classify provider errors and stop empty responses before parser errors.
- [x] Add regression coverage for write-file feedback reaching the next LLM context.
- [x] Add and verify failing WebUI tests for Chinese UI, session sidebar, Markdown, and approval cards.
- [x] Update WebUI templates and CSS for Chinese labels, sidebar layout, pending approval counts, safe Markdown, and chat approval cards.
- [x] Address review feedback for live approval resume with unsaved in-process API keys.
- [x] Extend safe Markdown rendering for headings, blockquotes, links, code blocks, and simple tables.
- [x] Add sidebar session grouping and active session highlighting.
- [x] Add structured approval summaries for tool, operation, and target.
- [x] Add cross-platform pseudo-shell support for `ls`/`dir`/`pwd`/`cat`/`type`/`echo` and approval-gated `rm`/`del`/`rd`/`rmdir`.
- [x] Fix shell subprocess UTF-8 output decoding on Windows.
- [x] Run full project verification.
- [ ] Commit the batch.

## Remaining Known Gaps

This batch improves the broad WebUI and backend defects. The sidebar now exposes grouped sessions with active-session state, and approval cards show real tool, operation, target, reason, and action JSON. Future polish could split groups beyond today's local sessions when older fixture data is present.

2026-07-13 follow-up: WebUI and CLI validation now have a small internal pseudo-shell vocabulary. Read-only pseudo commands execute without the system shell, while delete commands create HITL approval requests and execute only after approval through Python filesystem operations inside the workspace boundary.
