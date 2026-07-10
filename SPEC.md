# Guarded Harness SPEC

## 1. Problem Statement

Guarded Harness solves the problem of turning an LLM that proposes coding actions into a controlled local coding-agent system. The target users are developers and students who want to experiment with agentic software engineering without giving an LLM unrestricted shell or filesystem access.

The project is worth building because coding agents are useful only when their actions are bounded, observable, and recoverable. This project focuses on the harness layer: deterministic governance, human approval, feedback, memory, and distribution.

## 2. User Stories

1. As a developer, I can ask the harness to work on a local repository task so that I can observe each action before trusting the system.
2. As a developer, I can run the system with a mock LLM so that tests and demos work without network access or paid APIs.
3. As a reviewer, I can see dangerous actions denied by code so that safety does not depend on prompt obedience.
4. As an operator, I can approve or deny sensitive actions so that the agent can pause before crossing risk boundaries.
5. As a student, I can run deterministic mechanism demos so that the core harness behavior is easy to evaluate.
6. As a user, I can launch a minimal WebUI so that task state, pending approvals, and run results are visible.

## 3. Functional Specification

### Agent Loop

Input: task text, workspace root, configuration, selected memory, and previous observations.

Behavior:

- Build context for each turn.
- Call a mockable LLM provider.
- Parse the provider response into a structured action.
- Route the action through guardrail policy.
- Execute allowed actions through tools.
- Pause for HITL approval when required.
- Convert parser, policy, tool, and feedback results into observations.
- Stop on `finish`, `waiting_approval`, `blocked`, `failed`, or `max_steps`.

Output: a session status and persisted trace.

Error handling: invalid JSON, unknown action, missing fields, and tool exceptions become observations.

### Tools

Supported actions:

- `read_file`: read a workspace file.
- `write_file`: write a workspace file.
- `run_shell`: run a command in the workspace.
- `run_tests`: run the configured test command.
- `remember`: store a memory entry.
- `finish`: finish the session with a message.

All file paths are resolved against the workspace root. Paths outside the workspace are rejected.

### Governance And HITL

The guardrail returns one of three decisions:

- `allow`: execute now.
- `deny`: do not execute; feed a policy-denied observation back to the loop.
- `needs_approval`: create an approval request and pause the session.

Denied actions include destructive system commands, disk formatting, sensitive system path access, and writes outside the workspace.

Approval-required actions include publishing, `git push`, dependency installation, deletion inside the workspace, and `.env` modification.

Approval behavior:

- approve: resume the paused action.
- deny: feed an approval-denied observation to the loop so the LLM can choose another action.

### Feedback

The feedback sensor classifies results as `tool_success`, `test_failure`, `lint_failure`, `command_error`, `policy_denied`, or `approval_denied`. The classification is included in the next LLM context.

### Memory

The memory store persists project conventions, approval outcomes, historical decisions, and failure summaries. The loop retrieves selected recent or relevant entries instead of loading all memory.

### CLI

The CLI supports task execution, WebUI startup, approval operations, credential management, and deterministic demos.

### WebUI

The WebUI supports creating a task, viewing a session trace, listing pending approvals, approving or denying requests, and viewing final status.

## 4. Non-Functional Requirements

### Performance

Mock-mode tests and demos should complete quickly on a local development machine. The agent loop must enforce `max_steps` to avoid unbounded execution.

### Security

The harness does not trust LLM output. Every action is parsed, validated, checked against workspace boundaries, and evaluated by guardrail code.

Credential threat model:

- API keys must not be committed.
- API keys must not appear in logs, audit events, CLI output, or WebUI pages.
- The preferred storage is the system credential manager through Python `keyring`.
- `.env` is allowed only as a local development fallback and is documented as plaintext risk.

### Availability

The core must run in mock mode without network access. Real provider failures must become observations or user-facing errors, not crashes.

### Observability

Audit events record session lifecycle, actions, policy decisions, approval requests, approval outcomes, and tool results.

## 5. System Architecture

```text
CLI --------\
            -> Harness Core -> LLM Provider
WebUI ------/       |
                   |-> Action Parser
                   |-> Guardrail + HITL
                   |-> Tool Dispatcher
                   |-> Feedback Sensor
                   |-> Memory Store
                   |-> Audit Log
```

External dependencies:

- Python runtime
- FastAPI
- Typer
- pytest
- SQLite
- optional Python `keyring`
- optional OpenAI-compatible API endpoint
- Docker for distribution

## 6. Data Model

- `Action`: type, payload, raw source text.
- `Observation`: success flag, feedback kind, message, stdout, stderr, metadata.
- `PolicyDecision`: decision, risk level, reason.
- `ApprovalRequest`: id, session id, action, reason, status, created time, resolved time.
- `SessionState`: id, task, status, step count, pending approval id, observations.
- `AuditEvent`: timestamp, session id, event type, payload.
- `MemoryEntry`: id, kind, content, tags, created time.

## 7. Credentials And Distribution

Credential commands:

- `harness credentials set`
- `harness credentials status`
- `harness credentials clear`

Distribution uses Docker:

- `docker build -t guarded-harness .`
- `docker run -p 8000:8000 guarded-harness`

Docker starts the FastAPI WebUI by default. README will also document local CLI execution and mock-mode demos.

## 8. Technology Choices

- Python: fast implementation, strong testing ecosystem, good CLI and web support.
- FastAPI: small WebUI/API surface with simple deployment.
- Typer: ergonomic CLI commands.
- pytest: deterministic unit and integration tests.
- SQLite: local persistence for sessions, approvals, memory, and audit events.
- Docker: clear course-friendly distribution path.

## 9. Domain And Mechanism Design

Coding feedback signals:

- test command exit codes
- lint command exit codes
- shell stdout and stderr
- parser errors
- policy decisions
- approval outcomes

Dangerous actions:

- destructive shell commands
- writes outside workspace
- sensitive system path access
- publishing or pushing changes
- dependency installation
- `.env` changes

Tools:

- read/write files
- shell execution
- test execution
- memory write
- finish

Memory needs:

- project conventions
- previous approval decisions
- repeated failures
- task summaries

Main contribution:

The main contribution is governance: deterministic guardrails, workspace boundaries, HITL approval state, approval recovery, and audit logging. These are implemented in code and verified with mock LLM tests.

## 10. Acceptance Criteria

- `pytest` passes with mock LLM and no network.
- A mock LLM dangerous command is denied deterministically.
- A mock LLM approval-required command pauses the session.
- Approving a pending request resumes the paused action.
- Denying a pending request feeds an approval-denied observation back to the loop.
- A feedback demo shows a mock LLM changing its next action after a failure observation.
- CLI can run demos and manage approvals.
- WebUI can create a task, show trace, and approve or deny pending actions.
- Docker image builds and starts the WebUI.
- `.gitlab-ci.yml` includes a `unit-test` job.
- README documents install, run, Docker, credentials, and safety boundaries.

## 11. Risks And Open Questions

- Real LLM integration may be flaky. It remains optional until the mock-mode core is complete.
- WebUI scope may grow. It is intentionally limited to task, trace, approval, and result views.
- Policy rules may be too broad or too narrow. They will be encoded explicitly and expanded through tests.
- Cold-start validation may reveal missing details in SPEC or PLAN. The documents will be revised before implementation.
