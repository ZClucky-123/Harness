# Next Session Handoff

Date: 2026-07-18

## Current State

- Repository: `D:\code\Harness\Harness`
- Active branch: `dev`
- Remote status at handoff: `dev` is aligned with `origin/dev`
- Latest pushed commit: `c4c87d2 docs: record docker credential handling fixes`
- GitHub remote: `https://github.com/ZClucky-123/Harness.git`

The worktree was clean when this handoff was written.

## Project Summary

Guarded Harness is a local coding-agent harness with deterministic governance:

- LLMs return structured actions instead of directly controlling files or shell.
- Guardrail policy decides allow / deny / needs approval.
- Human approval state is stored in SQLite and can be resumed.
- WebUI provides Chat, Provider Settings, Session Trace, and Approvals.
- Mock mode is deterministic and does not require network.
- Live mode supports OpenAI-compatible providers such as NJU SE Hub.

Main code lives under `src/guarded_harness/`.

## Important Recent Fixes

### Shell and Approval Behavior

- Added support for safe pseudo shell commands such as `ls`, `dir`, `pwd`, `cat`, `type`, and `echo`.
- Deletion commands such as `rm`, `del`, `rd`, and `rmdir` require approval.
- Shell control syntax such as `&&`, pipes, redirects, and `2>&1` is denied.
- Approval cards now expose three meanings:
  - `Approve once`
  - `Deny action`
  - `Stop task`

### WebUI Behavior

- Chat input clears immediately after submit.
- User message and temporary model `...` reply appear optimistically while the model is loading.
- Send button changes to a centered white square while running.
- Browser back/forward refresh behavior was refined:
  - Chat uses full reload.
  - Other pages use partial refresh preserving form input, details state, and scroll.

### Docker and API Key Handling

Docker containers usually do not have a usable OS keyring. The latest fixes address that:

- If saving to OS keyring fails, Provider Settings now shows a controlled error instead of Internal Server Error.
- `GUARDED_HARNESS_API_KEY` can be passed as an environment variable for Docker/live provider usage.
- If the user enters an API key in Provider Settings without checking `Save key to OS keyring`, the key is kept only in the current FastAPI process memory.
- Temporary frontend-entered keys are not written to `provider.json`, SQLite, audit events, logs, or HTML.
- Restarting the server/container loses the temporary key.

## How to Run Locally

The project requires Python 3.11 or newer.

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If `python --version` shows Python 3.10, do not use it to create `.venv`; install/use Python 3.11+ first.

Run tests:

```powershell
python -m pytest -q
python -m compileall -q src tests
```

Start WebUI locally:

```powershell
uvicorn guarded_harness.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## Docker Usage

Build:

```powershell
docker build -t guarded-harness .
```

Run mock/default mode:

```powershell
docker run --rm -p 8000:8000 guarded-harness
```

Open:

```text
http://127.0.0.1:8000
```

Run live mode using environment variables:

```powershell
docker run --rm -p 8000:8000 `
  -e GUARDED_HARNESS_BASE_URL=https://njusehub.info/v1 `
  -e GUARDED_HARNESS_MODEL=deepseek-v4-flash `
  -e GUARDED_HARNESS_API_KEY=YOUR_API_KEY `
  guarded-harness
```

Alternatively, start Docker without env vars, open Provider Settings, enter the API key, do not check `Save key to OS keyring`, then save. The key will be available only for the current container process.

## Verification Already Done

Recent verification before pushing:

- `pytest -q`: `262 passed, 2 skipped`
- `compileall src tests`: passed
- `git diff --check`: passed
- Docker build: passed after retrying one Docker Desktop BuildKit cache/export issue
- GitHub Actions on `dev`: passed after CI was added

## Known Caveats

- The root `.venv` may have been recreated with Python 3.10 if the user ran `python -m venv .venv` while system `python` pointed to 3.10. Always check `python --version`.
- Docker's `0.0.0.0:8000` is a bind address, not the browser URL. Use `http://127.0.0.1:8000`.
- `docker run --rm` deletes the container after it stops, but the image remains in Docker Desktop.
- Docker image/container data is managed by Docker Desktop, commonly inside its WSL2 virtual disk, not inside the repository.
- Live provider behavior depends on the external provider returning valid action JSON. Provider prompts were tightened, but real models can still choose denied/unsupported commands.
- A trace like `ls -la file 2>&1` being denied is expected because redirection is shell control syntax.
- `rm -f missing-file` may report success, mirroring force-delete behavior.

## Useful Files

- `README.md`: user-facing install/run/Docker instructions
- `pyproject.toml`: runtime and dev dependencies for `pip install -e ".[dev]"`
- `Dockerfile`: Docker image build recipe
- `.github/workflows/ci.yml`: GitHub Actions CI
- `.gitlab-ci.yml`: GitLab CI with unit test and Docker build jobs
- `AGENT_LOG.md`: detailed task-by-task implementation log
- `SPEC_PROCESS.md`: process and design rationale required for the assignment
- `PLAN.md`: implementation plan and task checklist
- `src/guarded_harness/web/app.py`: Web routes and provider settings logic
- `src/guarded_harness/tools/shell.py`: shell executor behavior
- `src/guarded_harness/governance/policies.py`: policy classification
- `tests/integration/test_web.py`: WebUI behavior regressions
- `tests/unit/test_dispatcher.py`: tool dispatch and shell behavior regressions

## If Continuing Work

Recommended first commands:

```powershell
git status --short --branch
git log --oneline --decorate -5
python --version
```

If code changes are made:

```powershell
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

For Docker-related changes, rebuild and rerun:

```powershell
docker build -t guarded-harness .
docker run --rm -p 8000:8000 guarded-harness
```

Do not commit API keys, `.env`, `.guarded-harness/state.sqlite3`, or local Docker/runtime artifacts.
