# CLI Mechanism Demos

Run the deterministic demonstrations from any workspace:

```powershell
harness demo guardrail
harness demo feedback
harness demo hitl
```

`guardrail` records a `policy_denied` event. `feedback` records a
`command_error` observation before the scripted agent changes action. `hitl` pauses
for an approval and then resumes it in a temporary workspace, so it never writes
`.env` in the directory where the CLI was invoked. To inspect the pause manually, run
`harness demo hitl --wait-only`, then use `harness approvals list` and
`harness approvals approve <id>` or `harness approvals deny <id>`.

Credentials are stored through the operating system keyring:

```powershell
harness credentials set
harness credentials status
harness credentials clear
```

The CLI never prints credential values. The HITL demo writes `.env` only in its
temporary demo workspace after approval.
