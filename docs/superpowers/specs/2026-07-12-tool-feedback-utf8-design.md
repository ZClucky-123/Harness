# Tool Feedback and UTF-8 File I/O Design

## Context

`issue.md` reports that successful `write_file`, `read_file`, and `run_tests` observations do not include clear feedback messages. This leaves the LLM with empty `message` fields and can cause repeated actions because the agent cannot tell that a tool already succeeded.

The same investigation also reproduced a Windows-specific UTF-8 problem: `Path.read_text()` without an explicit encoding uses the process locale, so UTF-8 Chinese content can fail to read on GBK systems.

## Scope

This change covers:

- `write_file` success feedback
- `read_file` success feedback, including empty files
- UTF-8 file reads and writes
- `run_tests` pass/fail feedback with exit codes

Out of scope for this change:

- Live approval resume provider restoration
- Chat sidebar/session management
- Provider exception taxonomy
- Shell guardrail built-in command handling

## Desired Behavior

- Successful file writes return a non-empty message containing the relative path, character count, and UTF-8 byte count.
- Successful file reads return a non-empty message containing the relative path, character count, and UTF-8 byte count, while keeping full content in `stdout`.
- Empty files are explicitly reported as empty.
- File tools use explicit UTF-8 encoding for disk I/O.
- Test command results include a message that says whether the command passed or failed and includes the exit code.
- Full `stdout` and `stderr` remain available for the LLM and trace view.

## Data Flow

`ToolDispatcher.dispatch()` calls the concrete tool function and returns an `Observation`. `AgentLoop._record_observation()` serializes the observation into audit records and the next LLM context via `_observation_payload()`. Therefore the fix belongs in the tool implementations that construct successful observations.
