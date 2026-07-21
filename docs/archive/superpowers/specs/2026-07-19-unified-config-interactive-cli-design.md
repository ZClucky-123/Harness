# Unified Config and Interactive CLI Design

## Goal

Add a shared provider configuration file and an interactive CLI entry so the project can be run in both one-shot and prompt-style harness modes.

## Current Gap

The WebUI already writes non-secret provider settings to `.guarded-harness/provider.json`, while CLI live mode reads only environment variables plus OS keyring. This means WebUI and CLI do not share the same non-sensitive provider configuration. Also, `harness run` currently requires a task argument, while some coding-agent harnesses expose a prompt-style command that starts with `harness run` and then waits for user input.

## Design

Use `.guarded-harness/provider.json` as the shared non-secret provider config:

```json
{
  "mode": "live",
  "base_url": "https://njusehub.info/v1",
  "model": "deepseek-v4-flash",
  "timeout": 30
}
```

The config file must never contain API keys. API keys continue to come from OS keyring, `GUARDED_HARNESS_API_KEY`, or WebUI current-process temporary memory.

Configuration precedence:

1. CLI flags and explicit form values.
2. Environment variables.
3. `.guarded-harness/provider.json`.
4. Built-in defaults.

`harness run "<task>"` remains the one-shot command. `harness run` with no task starts interactive mode. In interactive mode, each ordinary input line starts a new session with the currently configured mode. Commands:

- `:help`
- `:mode`
- `:approvals`
- `:exit`
- `:quit`

## Testing

Add tests proving:

- CLI loads base URL/model/timeout from `.guarded-harness/provider.json`.
- Environment variables override the config file.
- API key is not loaded from provider.json.
- `harness run` without a task enters interactive mode and executes entered tasks.
- Interactive `:mode` and `:approvals` commands work without leaking secrets.

## Documentation

Update README, SPEC, PLAN, SPEC_PROCESS and AGENT_LOG as Task 15, recording that this improves course submission ergonomics while preserving the core security boundary.
