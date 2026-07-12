# Global Scroll Chat Follow-up

## Approved Change

User approved a closer ChatGPT-style layout after testing the previous scroll-container version.

## Requirements

- Keep only the compact top navigation fixed while the page scrolls.
- Use normal global page scrolling, not an inner scroll box.
- Keep older messages above newer messages.
- Move provider state into the chat stream as a system/status message.
- Remove repeated role labels inside messages; do not display `You` or `Harness`.
- Make the task composer smaller and keep only one visible `Task` label.
- Keep a tiny native JavaScript snippet that scrolls the page to the latest message after load.

## Non-goals

- No frontend framework, build step, WebSocket, or streaming UI.
- No provider, guardrail, HITL, keyring, audit, or session semantic changes.
