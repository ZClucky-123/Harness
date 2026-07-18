# Tool Feedback and UTF-8 File I/O Plan

## Checklist

- [x] Read `issue.md` and identify the relevant acceptance items.
- [x] Trace the tool feedback path from `ToolDispatcher` to `AgentLoop._observation_payload()`.
- [x] Add failing dispatcher tests for `write_file`, `read_file`, empty reads, and `run_tests`.
- [x] Verify tests fail for missing messages and UTF-8 decoding on Windows.
- [x] Update file tools to use explicit UTF-8 and return structured success feedback.
- [x] Update test runner tool to return pass/fail messages with exit codes.
- [x] Run focused dispatcher tests.
- [x] Run full project verification.

## Notes

The root cause is that successful tool observations were constructed with the default empty `message`. The file tool also relied on platform default encoding, which is unsafe for Chinese content on Windows.
