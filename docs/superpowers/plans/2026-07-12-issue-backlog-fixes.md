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
- [x] Run full project verification.
- [ ] Commit the batch.

## Remaining Known Gaps

This batch improves the broad WebUI and backend defects. Remaining polish: the session sidebar still uses a simple recent-session list rather than full today/yesterday grouping, and approval cards show real action JSON/reason but do not yet include richer parsed target/resource summaries.
