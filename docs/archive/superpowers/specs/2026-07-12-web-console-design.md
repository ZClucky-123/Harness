# Web Console Design

## Goal

Turn the Web UI from a single form into a local agent console suitable for project demonstration.

## Design

- Dashboard is the default page. It shows current provider mode, endpoint, model, key status, a task input, and links to major workflows.
- Provider Settings is a separate page. It stores non-secret provider settings in `.guarded-harness/provider.json`; API keys remain optional and are saved only to the OS keyring when requested.
- Session Trace uses terminal-style numbered event rows.
- Approvals uses queue columns for `[pending]`, `[executing]`, and `[failed]`.
- Guardrail Demo exposes deterministic sample actions so reviewers can see code-enforced allow/deny/approval decisions without relying on prompt behavior.

## Acceptance Criteria

- Users configure provider settings once, then run tasks from Dashboard without retyping API configuration.
- The Dashboard does not render an API key field.
- Approvals visibly groups pending, executing, and failed items.
- Guardrail Demo can classify `rm -rf /` as denied.
- Full pytest passes.

## Security Notes

The provider settings file must not contain API keys. API keys are accepted only through hidden form input and saved only through the existing keyring abstraction.
