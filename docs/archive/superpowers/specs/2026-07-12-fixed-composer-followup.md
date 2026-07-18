# Fixed Composer Follow-up

## Approved Change

User approved moving provider state into a compact ChatGPT-like fixed bottom composer.

## Requirements

- The bottom composer is fixed to the viewport.
- The composer is smaller than the previous form card.
- The visible `Task` label and visible `Start task` text are removed.
- Submit is a small circular button on the right side of the composer.
- Provider state (`mode`, `model`, `key`) is displayed in the composer area.
- Provider state is no longer shown as a message inside the chat stream.
- Message order, hidden Guardrail Demo navigation, API-key safety, and provider/agent-loop behavior remain unchanged.

## Notes

The submit button keeps `aria-label="Start task"` for accessibility while removing visible button text.
