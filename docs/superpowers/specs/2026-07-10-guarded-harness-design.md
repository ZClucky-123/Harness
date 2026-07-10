# Guarded Harness Design

## Summary

Guarded Harness is a local coding-agent harness for small software repositories. It lets an LLM propose structured actions, but all execution is controlled by code that we own: an agent loop, action parser, tool dispatcher, guardrail, HITL approval state machine, feedback sensor, memory store, and audit log.

The main contribution is the governance layer: dangerous or sensitive actions are not handled by prompt instructions. They are classified by deterministic policy code, either allowed, denied, or paused for human approval. The system can be tested end to end with a mock LLM and no network access.

## Goals

- Implement a self-owned coding-agent harness kernel rather than configuring an existing agent framework.
- Provide a mockable LLM abstraction so core mechanisms can be unit tested offline.
- Make governance the deep mechanism: guardrails, workspace boundaries, HITL approval, approval recovery, and audit logs.
- Provide both a Typer CLI and a minimal FastAPI WebUI over the same core.
- Ship through Docker with clear local and container usage instructions.

## Non-Goals

- Do not build on LangChain AgentExecutor, AutoGen, CrewAI, LlamaIndex agent runners, or coding-agent SDK loops.
- Do not attempt a fully autonomous production coding agent.
- Do not make the WebUI the main engineering contribution.
- Do not require a real LLM or network for tests, demos, or grading of core mechanisms.

## Architecture

The system has two user-facing entry points:

- Typer CLI for local demos and operations: run tasks, inspect sessions, approve or deny pending actions, and manage credentials.
- FastAPI WebUI for task submission, run trace inspection, approval queue handling, and final result display.

Both entry points call the same harness core.

Core flow:

1. Load task, configuration, memory, and recent observations.
2. Call the configured LLM provider.
3. Parse the provider response into a structured `Action`.
4. Ask the guardrail for a `PolicyDecision`.
5. If allowed, dispatch the action to a tool.
6. If denied, return a policy observation to the loop.
7. If approval is required, create an `ApprovalRequest` and pause the session.
8. Classify tool output through the feedback sensor.
9. Persist audit events and memory entries.
10. Stop on finish, failure, blocked state, pending approval, or `max_steps`.

## Components

### Agent Loop

Owns the repeated context-build, LLM-call, action-parse, policy-check, execute, observe, and stop cycle. It converts malformed model output and tool exceptions into observations instead of crashing.

### LLM Providers

The `LLMProvider` interface exposes one method that accepts a context object and returns text. `MockLLM` returns scripted responses for tests and demos. An optional OpenAI-compatible provider can be configured for real usage, but it is not required for tests.

### Action Parser

Parses LLM output as JSON actions. Supported actions:

- `read_file`
- `write_file`
- `run_shell`
- `run_tests`
- `remember`
- `finish`

Unknown action types, missing fields, and invalid JSON become deterministic parser observations.

### Tool Dispatcher

Dispatches valid actions to file, shell, test, memory, and finish handlers. File and shell actions are always evaluated against the configured workspace root.

### Governance

The guardrail classifies actions into `allow`, `deny`, or `needs_approval`.

Denied examples:

- `rm -rf /`
- disk formatting commands
- writes outside the workspace
- reads from sensitive system paths

Approval examples:

- `git push`
- publishing commands
- dependency installation
- deleting files inside the workspace
- modifying `.env`

Allowed examples:

- reading workspace files
- writing ordinary source files inside the workspace
- running tests
- remembering project notes
- finishing a run

The HITL state machine supports:

- `running -> waiting_approval`
- `waiting_approval -> running` on approve
- `waiting_approval -> running` with denial observation on deny
- `running -> finished | failed | blocked`

Every policy decision, approval request, approval result, and resumed action is recorded as an audit event.

### Feedback Sensor

Classifies command and test results into:

- `test_failure`
- `lint_failure`
- `command_error`
- `policy_denied`
- `approval_denied`
- `tool_success`

These observations are fed into the next loop turn. A mock LLM demo will show the model changing its next action after receiving a failure observation.

### Memory

Memory stores project conventions, previous decisions, failure summaries, and approval outcomes. SQLite is preferred because both CLI and WebUI can query it cleanly. Each loop receives selected recent or relevant entries, not the full memory log.

### Configuration And Credentials

Configuration includes workspace root, max steps, provider choice, policy options, and database path. Credentials are managed through Python `keyring` when available. `.env` is allowed only as a development fallback and is documented as plaintext risk. Logs must never print secret values.

## Data Model

- `Action`: requested operation from the LLM.
- `Observation`: objective result from parsing, policy, tools, or feedback.
- `PolicyDecision`: `allow`, `deny`, or `needs_approval`.
- `ApprovalRequest`: pending or resolved HITL record.
- `SessionState`: task, status, observations, step count, and pending approval.
- `AuditEvent`: immutable record of actions, decisions, approvals, and tool results.
- `MemoryEntry`: persisted project knowledge or run summary.

## CLI

Planned commands:

- `harness run "<task>"`
- `harness serve`
- `harness approvals list`
- `harness approvals approve <id>`
- `harness approvals deny <id>`
- `harness credentials set`
- `harness credentials status`
- `harness credentials clear`
- `harness demo guardrail`
- `harness demo hitl`
- `harness demo feedback`

## WebUI

The WebUI is intentionally minimal:

- task input
- session trace
- pending approval list
- approve and deny buttons
- final status and result

It exists to satisfy the accessible interface requirement while keeping engineering depth in the harness kernel.

## Testing Strategy

Tests use `pytest` and `MockLLM`.

Unit tests cover:

- action parser
- guardrail policy decisions
- workspace path boundaries
- HITL state transitions
- dispatcher behavior
- feedback classification
- memory read/write
- credential status without secret leakage

Integration tests cover:

- guardrail denying a dangerous action from mock LLM
- HITL pause and resume for an approval-required action
- denied approval being fed back to the loop
- command/test failure feedback causing the next mock LLM action to change

Verification commands:

- `pytest`
- `python -m compileall src`
- `docker build -t guarded-harness .`

## Mechanism Demonstrations

The project will include deterministic demos:

1. Guardrail demo: mock LLM requests `rm -rf /`; policy denies it.
2. Feedback demo: mock LLM first produces a failing action; feedback is classified and the next mock response changes.
3. HITL demo: mock LLM requests `git push`; session pauses for approval. Approve resumes the action; deny feeds back an approval-denied observation.

## Distribution

Docker is the official distribution path. The image starts the FastAPI WebUI by default. README will include local development, Docker build/run, mock mode, real provider configuration, security boundaries, and known limitations.

CI will include `.gitlab-ci.yml` with a `unit-test` job. If time allows, CI will also include a Docker build job.

## Risks

- The scope can drift toward a large UI. Mitigation: keep WebUI minimal.
- Real LLM integration can consume time and introduce flaky tests. Mitigation: make mock mode first-class and keep real provider optional.
- Guardrail policies can become vague. Mitigation: encode explicit command and path rules and test them directly.
- SPEC and PLAN may rely on hidden conversation context. Mitigation: write concrete interfaces and use a cold-start agent validation step before implementation.
