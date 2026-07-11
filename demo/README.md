# CLI Mechanism Demos

Run the deterministic demonstrations from a disposable workspace:

```powershell
harness demo guardrail
harness demo feedback
harness demo hitl
```

`guardrail` records a `policy_denied` event. `feedback` records a
`command_error` event before the scripted agent changes action. `hitl` pauses
for an approval and then resumes it. To inspect the pause manually, run
`harness demo hitl --wait-only`, then use `harness approvals list` and
`harness approvals approve <id>` or `harness approvals deny <id>`.

Credentials are stored through the operating system keyring:

```powershell
harness credentials set
harness credentials status
harness credentials clear
```

The CLI never prints credential values. The HITL demo writes `.env` only after
approval, so do not run it where that file already contains important values.
