# Chat App Shell Follow-up

## Approved Change

User approved changing the home page from a tall landing-style workspace into a normal ChatGPT/Codex-like chat shell.

## Requirements

- Older messages appear above newer messages.
- The message area is independently scrollable.
- The task composer stays available at the bottom while reviewing history.
- Provider status remains visible while scrolling.
- A tiny native JavaScript snippet scrolls the message area to the latest message on page load.
- The existing provider, guardrail, HITL, audit, keyring, and session semantics remain unchanged.

## Implementation Notes

- `SQLiteStore.list_sessions()` still returns newest-first for general use.
- The WebUI reverses the recent session list for display, so the selected recent window reads oldest-to-newest.
- The home page uses `chat-app`, `chat-scroll`, and `composer-sticky` classes.
- No frontend framework, build step, WebSocket, or remote asset is introduced.
