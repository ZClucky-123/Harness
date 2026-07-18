# Live Provider Web UI Design

## Goal

Make the existing harness usable with an OpenAI-compatible provider such as NJU SE Hub from both CLI and Web UI, while preserving the deterministic mock path required by the project.

## Design

- `OpenAICompatibleProvider` will include a protocol instruction telling the model to return only harness action JSON. Ordinary Q&A should return `{"type":"finish","message":"..."}`.
- The provider will normalize common fenced JSON responses before the core parser sees them.
- The Web index will expose a compact OpenCode-inspired form with mode, base URL, model, API key, and optional keyring save.
- Web live runs will use the submitted key for the request, or fall back to the OS keyring when no key is submitted.
- API keys must never be persisted to sessions, audit events, or rendered back to the browser.

## Acceptance Criteria

- CLI live no longer reaches `parser_error` for a provider that follows the JSON action instruction.
- Web supports mock mode and live mode.
- Web can store a submitted key in the existing credential store only when requested.
- Full pytest passes in the local Python 3.11 virtual environment.

## Process Note

This is a post-review usability enhancement. It does not replace the harness mechanisms with prompts: guardrails, HITL, feedback, memory, and dispatch remain deterministic code paths covered by mock-driven tests.
