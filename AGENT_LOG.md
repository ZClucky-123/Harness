# Agent Log

## 设计与实现历史

| 阶段 | 工作摘要 | 提交/验证 |
| --- | --- | --- |
| 初始文档阅读 | 阅读需求、SPEC、PLAN 和设计材料，确认离线 mock、治理与 HITL 的目标。 | 设计上下文已建立 |
| Brainstorming | 讨论 action 边界、风险策略、审批恢复、离线 demo 与凭据保护。 | 见设计记录 |
| Writing plans | 将核心模型、存储、guardrail、dispatcher、loop、HITL、CLI、WebUI 和交付拆分为可验证任务。 | 见 `PLAN.md` |
| 设计规格 | 创建并中文化 Guarded Harness 规格。 | `5641349`, `969e4ff` |
| Task 1--8 | 实现 core/session/store/guardrails/dispatcher/agent loop/HITL/CLI/WebUI，并逐任务提交。 | 以 git 历史与 tests 为准 |
| Task 9 | 增加 Docker、GitLab CI、README、过程文档和最终验证记录。 | `e918c53` |

## 使用的工作流

- `superpowers:brainstorming`：在设计阶段澄清用户、风险和机制边界。
- `superpowers:writing-plans`：将规格转化为按依赖排序的实现任务与验收命令。
- `superpowers:using-git-worktrees`：确认本任务位于 linked worktree
  `feature/guarded-harness-impl`。
- `superpowers:test-driven-development`：实现任务以先写失败测试、再最小实现的方式推进；
  Docker、CI 和纯文档遵循配置/文档例外。
- `superpowers:verification-before-completion`：在提交前运行可用测试、编译和 diff 检查。

## 环境限制

- 当前本地 Python 为 3.10，而项目声明 Python 3.11+。
- 本地环境缺少 FastAPI 与 Typer，因此完整 `pytest` 在收集 CLI/Web 测试时可能失败。
- 曾尝试安装项目依赖，但包下载受代理连接失败影响，无法在本机补齐依赖。
- Docker 可用性与镜像拉取受本机 Docker daemon 和网络访问影响；本次验证结果将在下方补充。

## Task 9 验证结果

| 命令 | 结果 |
| --- | --- |
| `pytest tests/unit tests/integration/test_loop_guardrail.py tests/integration/test_loop_feedback.py tests/integration/test_loop_failures.py tests/integration/test_hitl.py -q` | PASS，60 passed（Python 3.10.3）。 |
| `pytest` | 未完成：收集 CLI/Web 测试时缺少 `typer` 与 `fastapi`，共 2 个 `ModuleNotFoundError`。 |
| `python -m compileall -q src` | PASS，退出码 0。 |
| `git diff --check` | PASS，退出码 0；仅提示 Git 将把 README 的 LF 转为 CRLF。 |
| `docker version --format '{{.Server.Version}}'` | 未完成：Docker daemon 不可用，`//./pipe/docker_engine` 不存在，且 Docker 配置文件访问被拒绝；因此未运行 `docker build`。 |

## 最终复审修复

- 使用 `receiving-code-review`、`systematic-debugging`、`test-driven-development` 与
  `verification-before-completion` 复核最终阻塞项。
- 先用失败测试复现 shell command substitution/换行/反引号/重定向/管道绕过和字符串
  `shell=True` 执行，再改为共享 argv 解析、`shell=False` 与 realpath 边界校验。
- 先用失败测试复现审批 action 在展示模型中的 secret 泄露，再引入统一 redaction，Web/CLI 只读取脱敏 action。
- 将审批与 session 的恢复更新放入同一 SQLite 事务，引入 `executing`、`executed`、`failed` 执行状态；
  跨进程恢复明确在处理动作后结束，不声称继续 live provider loop。
- 实现 `remember` action 的字段验证、memory 持久化、observation 与 audit。
- 当前机器仍缺 FastAPI/Typer；涉及 Web/CLI 的新增测试已提交，但只能在 GitLab Runner 或安装完整依赖后执行。

## 2026-07-12 Live Provider 与 WebUI 追补

- 触发原因：使用 NJU SE Hub (`https://njusehub.info/v1`, `deepseek-v4-flash`) 运行 `harness run "回复1+1+?" --live` 时，真实模型返回自然语言，核心 loop 期望 action JSON，导致连续 `parser_error` 并进入 `max_steps`。
- 使用技能：`brainstorming` 澄清变更边界；`writing-plans` 产出小计划；`test-driven-development` 先写 provider/Web/CLI 失败测试，再实现。
- 人工决策：在 provider 层加入 action JSON 协议提示和 fenced JSON 清洗；WebUI 从 mock-only 扩展为 mock/live 双模式，并允许页面输入 base URL、model、API key，选择性保存到 OS keyring。
- 作业边界说明：这次变更只改善真实 LLM 接入和演示可用性，不把 guardrail、HITL、feedback 等机制迁移到提示词；核心机制仍由代码和 MockLLM 测试验证。

## 2026-07-12 WebUI 中文展示与 OpenCode 风格修复

- 触发原因：Session trace 页面把中文 payload 渲染成 `\uXXXX`，且页面视觉仍偏最小原型，不利于演示。
- 使用技能：`brainstorming` 明确修复范围；`test-driven-development` 先写中文展示失败测试，再实现 `pretty_json` filter 和模板改造。
- 人工决策：只修展示层，不改 SQLite 存储和 audit 数据模型；UI 参照 `DESIGN-opencode.ai.md` 的 cream canvas、monospace、terminal panel、ASCII bracket 语言。
- 作业边界说明：这是 WebUI 可用性与 Open Design 风格对齐，不改变 harness 核心机制。

## 2026-07-12 Web Console 重构

- 触发原因：用户反馈每次任务都填写 provider/API key 不符合实际使用方式，并希望页面更接近 OpenCode 控制台。
- 使用技能：`brainstorming` 确认页面信息架构；`test-driven-development` 先写 Dashboard、Provider Settings、Approvals queue、Guardrail Demo 的失败测试。
- 人工决策：将非 secret 的 mode/base URL/model 保存到 `.guarded-harness/provider.json`；API key 只在用户勾选时写入 OS keyring，不放入配置文件。
- 作业边界说明：Guardrail Demo 直接调用 deterministic `Guardrail.evaluate()`，用于展示“机制是代码而不是提示词”。

## 2026-07-13 01:26:06 +08:00 - Task 12 WebUI layout polish started

- **Task:** Task 12 - ChatGPT-like WebUI Layout Polish.
- **Superpowers skills:** `brainstorming`, `test-driven-development`; planned follow-up `verification-before-completion`.
- **Prompt/context configuration:** User supplied five screenshot-driven UI requirements: keep only one approval navigation link and render links as underlined text, remove Copy command, pin the session sidebar to the left with independent scrolling, align chat content and composer widths, and tune overall horizontal spacing to match ChatGPT-like layout.
- **Subagent output key fragments:** No delegated subagent output. Work is performed by `Codex(main)`.
- **Manual intervention:** User approved the design and required explicit process records in `PLAN.md` and `AGENT_LOG.md`, plus commit messages that identify subagent/manual changes.
- **Lesson so far:** UI polish requests must be tracked as first-class tasks, not hidden inside one large implementation commit.

## 2026-07-13 01:38:00 +08:00 - Task 12 WebUI layout polish implemented

- **Task:** Task 12 - ChatGPT-like WebUI Layout Polish.
- **Superpowers skills:** `test-driven-development`, `verification-before-completion`.
- **Prompt/context configuration:** Continued from the approved screenshot requirements. Existing worktree only had untracked `test.md`; it was intentionally left untouched.
- **Subagent output key fragments:** No delegated subagent output. `Codex(main)` wrote failing web integration assertions, observed the expected red tests, then implemented the minimal template/CSS changes.
- **Manual intervention:** User's requested changes drove all UI decisions: keep only `View trace`, remove `Copy command`, use underlined text for `Technical details`, pin left sidebar with its own scroll, and align composer width to chat content.
- **Verification:** `pytest -q` -> 235 passed, 2 skipped, 1 warning. `python -m compileall src` -> exit 0. `git diff --check` -> exit 0.
- **Commits:** workflow start `72877ec`; implementation `33ecf68`; completion record `543f6e1`.
- **Lesson:** Layout constants should be explicit CSS variables (`--sidebar-width`, `--content-width`) so future screenshot-driven tuning stays local and testable.

## 2026-07-13 01:36:10 +08:00 - Task 12 PR workflow status

- **Task:** Task 12 - ChatGPT-like WebUI Layout Polish.
- **Superpowers skills:** `verification-before-completion`.
- **Prompt/context configuration:** User required a complete commit + PR workflow and commit messages that identify subagent/manual intervention.
- **Subagent output key fragments:** No delegated subagent output. Local branch `feature/guarded-harness-impl` contains split commits and is PR-ready.
- **Manual intervention:** Attempted `git push -u origin feature/guarded-harness-impl`, but sandbox safety rejected exporting workspace code to `https://github.com/ZClucky-123/Harness.git` until the user explicitly approves that remote push after being informed of the risk.
- **Lesson:** PR workflow needs an explicit remote-export approval separate from local commit approval.

## 2026-07-13 01:44:24 +08:00 - Task 13 conversation/sidebar polish started

- **Task:** Task 13 - Chat Conversation Order and Sidebar Header Polish.
- **Superpowers skills:** `brainstorming`, `test-driven-development`; planned follow-up `verification-before-completion`.
- **Prompt/context configuration:** User supplied four corrections after visual testing: right-side chat order should be old-to-new with newest at the bottom, composer should be white and grow upward with the send button anchored lower-right, the fixed sidebar should expose its own scroll area, and `Guarded Harness` should move above the left sidebar list on session pages.
- **Subagent output key fragments:** No delegated subagent output. Work is performed by `Codex(main)`.
- **Manual intervention:** User approved the design and clarified the expected behavior with screenshots.
- **Lesson so far:** The sidebar ordering and conversation ordering are separate UX models and need separate tests.

## 2026-07-13 01:53:03 +08:00 - Task 13 conversation/sidebar polish implemented

- **Task:** Task 13 - Chat Conversation Order and Sidebar Header Polish.
- **Superpowers skills:** `test-driven-development`, `verification-before-completion`.
- **Prompt/context configuration:** Continued from the approved four screenshot corrections. Existing untracked `test.md` was left untouched.
- **Subagent output key fragments:** No delegated subagent output. `Codex(main)` wrote failing tests for chat order, sidebar brand/scroll, white composer, textarea growth, and removal of mojibake separators, then implemented the smallest view-model/template/CSS changes.
- **Manual intervention:** User corrected the previous interpretation: left sidebar remains newest-first, but the right chat transcript must be old-to-new with newest at the bottom.
- **Verification:** `pytest -q` -> 235 passed, 2 skipped, 1 warning. `python -m compileall src` -> exit 0. `git diff --check` -> exit 0.
- **Commits:** workflow start `7e07cb7`; implementation `4534a00`; completion record `385b0a5`.
- **Lesson:** Similar-looking lists can encode different interaction models; tests should isolate DOM regions instead of using whole-page string order.

## 2026-07-13 - Fix: chat session list truncation at 12 items

- **Superpowers skills:** `systematic-debugging` (根因定位), `test-driven-development` (更新断言).
- **Bug:** When chat sessions exceeded 12, older content disappeared from both the left sidebar and right conversation panel.
- **Root cause:** `_conversation_items()` in `app.py` had `limit: int = 12`, hardcoding the SQLite query to fetch only 12 sessions. Both `index` and `show_session` routes called it without an explicit limit.
- **Fix:** Raised default limit from `12` to `200` in `src/guarded_harness/web/app.py:160`.
- **Files changed:** `src/guarded_harness/web/app.py` (1 line: `limit: int = 12 → limit: int = 200`).
- **Verification:** Existing tests remain compatible; change is a single numeric constant.
- **Lesson:** UI list queries should have generous defaults; hard limits that match common UX pagination sizes (like 12) silently truncate data when both sidebar and main panel share the same query.

## 2026-07-13 - Fix: composer send button placement and alignment

- **Superpowers skills:** `brainstorming` (clarify desired layout), `test-driven-development` (update CSS assertions before/alongside implementation), `verification-before-completion` (diff check).
- **Trigger:** User reported two issues: (1) the send button (↑) should be in the status row below the textarea, not overlaid on the textarea; (2) the composer was slightly offset to the right relative to the chat content above it.
- **Root cause (alignment):** `.composer-fixed` `left` calculation used `(100vw - var(--sidebar-width)) / 2`, ignoring the 32px right padding that `.chat-page` applies. `.composer-fixed` `width` used `-64px` (double-counting padding) instead of `-32px`. This caused a ~16px rightward offset.
- **Root cause (button):** The submit button was positioned `absolute` at `right: 0; bottom: 0` inside `.composer-row`, overlaying the textarea.
- **Fix:** 
  - Moved `<button>` from `composer-row` into `composer-status` in `index.html`, wrapping the status text in a `<span>`.
  - Changed `.composer-status` to `display: flex; align-items: center; justify-content: space-between`.
  - Removed `position: absolute` from `.composer-submit`.
  - Simplified `.composer-row` to `grid-template-columns: 1fr` (removed 36px column for button).
  - Changed textarea `padding` from `10px 56px 10px 16px` to `10px 16px` (no need for button clearance).
  - Fixed `.composer-fixed` `left` to `calc(var(--sidebar-width) + (100vw - var(--sidebar-width) - 32px) / 2)` and `width` to `min(var(--content-width), calc(100vw - var(--sidebar-width) - 32px))`.
- **Files changed:** `src/guarded_harness/web/templates/index.html`, `src/guarded_harness/web/static/styles.css`, `tests/integration/test_web.py`.
- **Lesson:** Fixed-position elements that mirror centered auto-margin elements must account for all asymmetric padding in the parent container; a single missing term produces visible misalignment.

## 2026-07-13 - Fix: compress composer vertical spacing

- **Superpowers skills:** `brainstorming` (iterative refinement of spacing), `test-driven-development` (sync CSS + test assertions), `verification-before-completion`.
- **Trigger:** User requested the composer be vertically compressed ("压窄，上下长度") — less top/bottom space, same width.
- **Fix:**
  - `.composer, .settings-card` padding `12px → 8px`
  - `.composer-row textarea` padding `10px 16px → 8px 14px`
  - `.composer-status` margin `8px → 1px`; font-size `13px → 12px`
  - `.composer-submit` `36×36 → 28×28`
  - `.composer fieldset { margin: 0 }` — eliminate global fieldset 16px bottom margin inside composer
  - Width and textarea min/max-height intentionally preserved.
- **Files changed:** `src/guarded_harness/web/static/styles.css`, `tests/integration/test_web.py`.
- **Lesson:** Clarify width vs height terminology up front — "压窄" (compress narrow) + "上下长度" (top-bottom length) means reduce vertical padding, not horizontal width. Also: fieldset default browser margins can silently add padding inside forms.

## 2026-07-13 - Fix: chat message styling polish

- **Superpowers skills:** `brainstorming` (clarify visual requirements), `test-driven-development` (CSS assertions), `verification-before-completion`.
- **Trigger:** User requested multiple chat message display improvements.
- **Fixes:**
  - `.message p` margin `8px 0 0 → 4px 0` — symmetric top/bottom spacing inside bubbles
  - `.message p` + `.markdown-body p` add `overflow-wrap: break-word; word-break: break-word` — fix long text premature wrapping
  - `.message-agent` remove `background: #fafafa` and `border` — no gray background for agent messages
  - `.message` max-width `min(100%, 620px) → 100%` — messages fill to chat right edge
  - `.message` remove `width: fit-content` — fix premature line breaks caused by min-content sizing
- **Files changed:** `src/guarded_harness/web/static/styles.css`.
- **Lesson:** `width: fit-content` on text containers calculates min-content from the longest unbreakable word, causing early wraps even with `max-width: 100%` and `word-break` set.

## 2026-07-13 - Fix: widen chat content area and remove heading

- **Superpowers skills:** `brainstorming`, `test-driven-development`, `verification-before-completion`.
- **Trigger:** User wanted wider chat area and cleaner UI.
- **Fixes:**
  - `--content-width: 760px → 860px` — chat area and composer both widen, stay aligned via shared variable
  - Remove `<h2>Recent Sessions</h2>` from `index.html`
- **Files changed:** `src/guarded_harness/web/static/styles.css`, `src/guarded_harness/web/templates/index.html`, `tests/integration/test_web.py`.

## 2026-07-13 - Fix: cross-platform pseudo-shell commands for WebUI validation

- **Superpowers skills:** `brainstorming` (approved design), `systematic-debugging` (root cause and command classification), `test-driven-development` (red/green tests), `verification-before-completion` (planned final verification).
- **Trigger:** Live WebUI trace showed `ls` was allowed by policy but failed on Windows because `shell=False` looked for `ls.exe`; user then requested support for common `ls`/`rm`-style commands so the frontend can verify successful tool calls and approval flows.
- **Root cause:** The shell safe allowlist mixed portable external executables with PowerShell aliases/cmdlets and cmd built-ins. The executor correctly avoided system shells, but no internal implementation existed for commands such as `ls`, `cat`, `pwd`, `echo`, `dir`, `type`, `rm`, `del`, `rd`, and `rmdir`.
- **Design decision:** Add a small Harness-owned pseudo-shell vocabulary instead of enabling `cmd`, PowerShell, Bash, pipes, redirects, or inline interpreters.
- **Fixes:**
  - `ls [path]` / `dir [path]` list workspace directories via Python.
  - `pwd` returns the workspace root.
  - `cat <file>` / `type <file>` read UTF-8 files inside the workspace.
  - `echo <text>` returns text without supporting redirects.
  - `rm`, `del`, `rd`, and `rmdir` now require HITL approval and execute approved deletes through Python filesystem operations inside the workspace boundary.
  - `subprocess.run` for remaining external executables now uses `encoding="utf-8", errors="replace"` to avoid Windows GBK decode failures on Chinese output.
- **TDD evidence:** First focused run failed with 16 expected failures for unsupported pseudo commands and missing UTF-8 subprocess kwargs. After implementation, `.\.venv\Scripts\python.exe -m pytest tests\unit\test_guardrail.py tests\unit\test_dispatcher.py tests\integration\test_hitl.py -q` passed with 128 passed, 2 skipped.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest -q` -> 252 passed, 2 skipped, 1 failed at the pre-existing CSS exact-string assertion in `tests/integration/test_web.py::test_chat_workspace_css_uses_global_scroll_and_compact_composer`; `.\.venv\Scripts\python.exe -m compileall -q src` -> exit 0; `git diff --check` -> exit 0.
- **Files changed:** `src/guarded_harness/governance/policies.py`, `src/guarded_harness/governance/shell_command.py`, `src/guarded_harness/tools/dispatcher.py`, `src/guarded_harness/tools/shell.py`, `tests/unit/test_guardrail.py`, `tests/unit/test_dispatcher.py`, `tests/integration/test_hitl.py`, `docs/superpowers/plans/2026-07-12-issue-backlog-fixes.md`.
- **Lesson:** A safe shell policy must describe capabilities the harness actually owns. Cross-platform demo commands are safer as structured internal operations than as aliases to platform shells.

## 2026-07-13 - Fix: stale compact composer CSS assertion

- **Superpowers skills:** `systematic-debugging`, `test-driven-development`, `verification-before-completion`.
- **Trigger:** Full pytest still had one failure in `test_chat_workspace_css_uses_global_scroll_and_compact_composer` after the shell work.
- **Root cause:** The test still expected the old `.composer, .settings-card` `padding: 12px`, while the UI had intentionally been compressed to `padding: 8px 8px 6px 8px` in the earlier composer spacing task.
- **Fix:** Updated the CSS assertion in `tests/integration/test_web.py` to match the documented compact composer rule.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest tests\integration\test_web.py::test_chat_workspace_css_uses_global_scroll_and_compact_composer -q` -> 1 passed; `.\.venv\Scripts\python.exe -m pytest -q` -> 253 passed, 2 skipped, 1 warning.

## 2026-07-13 - Fix: composer submit feedback

- **Superpowers skills:** `brainstorming` (approved UI behavior), `systematic-debugging` (confirmed missing submit-state handler), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User reported that after sending from the frontend, the message remained in the input box while the request was processing, making it look as if the send failed.
- **Root cause:** The composer only handled textarea growth and Enter submission. The normal form submit had no immediate UI feedback, no textarea clearing, and no duplicate-submit guard. A first pass disabled the textarea before browser serialization, which omitted the `task` field from the POST body.
- **Fix:** Added a submit listener that checks native validity, copies the textarea value into a hidden `task` field, prevents duplicate submissions, clears the visible textarea immediately, resets its height, disables textarea/button, and marks the submit button `aria-busy` while the normal form submission continues. The textarea keeps `name="task"` as a no-JS fallback; the hidden field receives `name="task"` only during JS submit before the textarea is disabled.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest tests\integration\test_web.py::test_composer_matches_borderless_input_with_submit_in_status_row tests\integration\test_web.py::test_composer_submit_clears_input_and_prevents_duplicate_submits -q` -> 2 passed.

## 2026-07-13 - Fix: approval card immediate processing state

- **Superpowers skills:** `brainstorming` (approved UI behavior), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User reported that clicking an approval/denial button left the same approval card visible and actionable during the POST round trip, making the click feel ineffective.
- **Fix:** Added stable `data-approval-card`/`data-approval-submit` hooks, a per-card submit guard, immediate title/status updates (`Approving...` / `Denying...`), and button disabling with `aria-busy` while the existing backend approval POST continues.
- **Verification:** `.\.venv\Scripts\python.exe -m pytest tests\integration\test_web.py::test_waiting_approval_session_shows_approval_card_in_chat tests\integration\test_web.py::test_approval_card_submit_switches_to_processing_state tests\integration\test_web.py::test_run_shell_approval_card_uses_real_tool_summary -q` -> 3 passed.

## 2026-07-13 - Fix: approval submit auto-refresh after completion

- **Superpowers skills:** `systematic-debugging` (confirmed stale approval card after successful submit), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User confirmed that after approving a delete command, the card changed to `Approving...` but stayed on the same selectable page after execution returned.
- **Root cause:** The previous UI only changed local card state before allowing the normal form submit. In the frontend trace flow, that did not reliably force the displayed chat workspace to reload after the backend completed approval recovery.
- **Fix:** Converted approval forms to controlled JavaScript submission: prevent default form navigation, POST with `fetch(..., redirect: "follow")`, then explicitly `window.location.assign(response.url)` for backend redirects or `window.location.reload()` for successful non-redirect responses. Failed requests now restore the buttons and show `Approval failed`.
- **TDD evidence:** Added assertions for `fetch(form.action, ...)`, same-origin POST, redirect following, explicit `window.location.assign`, explicit reload, and failure recovery. The focused test failed before implementation and passed after the template change.

## 2026-07-13 - Fix: composer running icon without disabling input

- **Superpowers skills:** `brainstorming` (clarified expected send-button state), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User reported that while a message is being sent, the send button still shows the arrow; it should switch to a square, then return to the arrow after the page completes, and the input box should not be disabled.
- **Root cause:** The previous submit feedback disabled both textarea and submit button and only used `aria-busy`; it did not change the visible button glyph.
- **Fix:** During JS submit, copy the textarea value into the hidden `task` input, remove the textarea `name` to avoid submitting the cleared textarea as a second `task` value, clear the visible textarea, and change the submit button text to `■` with `aria-label="Task is running"`. The textarea and button remain enabled visually; duplicate submits are still guarded by `isSubmitting`.
- **TDD evidence:** Updated the composer submit test to require the square glyph, reject `taskInput.disabled = true` and `submitButton.disabled = true`, and require `taskInput.removeAttribute("name")`. The test failed before implementation and passed after the template change.

## 2026-07-13 - Fix: optimistic chat message and centered stop icon

- **Superpowers skills:** `brainstorming` (approved optimistic-message design), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User clarified that after sending, the chat page should immediately show the submitted user message while the send button is in square running state; the square should appear as a centered white stop icon inside the black circular button.
- **Root cause:** The previous running state cleared the input and changed the button text, but did not append any local chat message before the backend response. The square was also rendered as button text, which made visual centering dependent on font metrics.
- **Fix:** Added `appendOptimisticUserMessage()` to append a temporary right-aligned user message using DOM APIs and `textContent` for safe escaping. Replaced text-based `■` with a `.composer-stop-icon` span styled as a 10px white square centered by the inline-flex submit button.
- **TDD evidence:** Added assertions for the optimistic message DOM creation, safe `textContent`, appending to `.conversation-list`, and CSS for the centered white square. The focused WebUI tests failed first and then passed after the template/CSS changes.

## 2026-07-13 - Fix: loading reply and disabled stop button

- **Superpowers skills:** `brainstorming` (approved loading-state behavior), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User clarified that while the model is loading, the stop-square send button should be disabled, the centered white square must remain visible, and the temporary model reply should show `...` until the real page refresh completes.
- **Root cause:** The optimistic send state only appended the user message and left the submit button clickable. The disabled button browser style was not pinned, so making it disabled could dim the icon/background depending on browser defaults.
- **Fix:** Added `appendOptimisticAgentMessage()` to append a temporary left-aligned agent message containing `...`; disabled the submit button after adding the white-square stop icon; added disabled-state CSS to preserve black background, white square, and default cursor.
- **TDD evidence:** Updated WebUI assertions to require the `...` agent loading message, `submitButton.disabled = true`, and explicit disabled CSS that keeps `.composer-stop-icon` white. The focused tests failed first and passed after implementation.

## 2026-07-13 - Fix: larger loading ellipsis

- **Superpowers skills:** `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User requested the temporary model loading ellipsis be larger.
- **Fix:** Added a dedicated `.loading-placeholder` class for the optimistic agent reply and styled it with `font-size: 28px`, `line-height: 1`, and the existing muted text color. This keeps the larger ellipsis scoped to the loading placeholder instead of changing all markdown output.
- **TDD evidence:** Added assertions for the `markdown-body loading-placeholder` class and the new CSS rule. The focused WebUI tests failed before implementation and passed after the template/CSS change.

## 2026-07-13 - Fix: stylesheet cache busting for loading UI

- **Superpowers skills:** `systematic-debugging` (compared screenshot behavior with updated JS/CSS), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User screenshot showed the temporary `...` appeared, but it was not enlarged and the stop button remained a plain black circle without the white square.
- **Root cause:** The inline template JavaScript was fresh, but the browser was still using cached `/static/styles.css`, so `.loading-placeholder` and `.composer-stop-icon` styles were missing.
- **Fix:** Added a `_STATIC_VERSION` Jinja global and appended `?v={{ static_version }}` to every stylesheet link so updated CSS is fetched after UI changes.
- **TDD evidence:** Added an assertion that the chat page includes `styles.css?v=`; the test failed before adding the versioned stylesheet URL and passed after implementation.

## 2026-07-13 - Fix: refresh pages restored from browser history

- **Superpowers skills:** `brainstorming` (approved all-page behavior), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User found that after approval completes and redirects, clicking the browser Back button can restore a stale page instead of fetching current state.
- **Root cause:** Browsers may restore pages from the back-forward cache, preserving transient UI state such as `Approving...` without a network request.
- **Fix:** Added shared `_history_refresh.html` and included it on Chat, Settings, Approvals, Guardrail, and Session pages. The script listens for `pageshow` and reloads when `event.persisted` or the navigation type is `back_forward`.
- **TDD evidence:** Added an integration test that fetches all primary pages and asserts the shared `pageshow` reload logic is present. The test failed before the shared partial was included and passed after implementation.

## 2026-07-13 - Refine: partial history refresh outside chat

- **Superpowers skills:** `brainstorming` (approved page-specific refresh policy), `test-driven-development` (red/green WebUI regression), `verification-before-completion`.
- **Trigger:** User clarified that browser back/forward should fetch fresh server data while preserving unsubmitted form input, details expansion, and scroll position where possible; Chat should keep full reload.
- **Fix:** Added `data-history-refresh="reload"` to Chat and `data-history-refresh="partial"` to Settings, Approvals, Guardrail, and Session. The shared history script now fully reloads Chat, but on partial pages fetches the current URL with `cache: "no-store"`, replaces `.site-header`, `.session-sidebar`, and `.chat-main`, then restores form values, `details` open state, and scroll position.
- **TDD evidence:** Updated the history restore integration test to assert Chat uses reload mode and all other primary pages expose partial refresh, region replacement, form/details state restoration, and scroll restoration. The test failed before implementation and passed after the partial-refresh script change.

## 2026-07-13 - Fix: unified layout across all pages

- **Superpowers skills:** `brainstorming` (layout consistency design), `test-driven-development` (update template tests), `verification-before-completion` (cross-page diff check).
- **Trigger:** User wanted nav links (Chat / Provider Settings / Approvals) to maintain fixed distance from sidebar "Guarded Harness" across page navigation, and all pages to share the same sidebar + header layout.
- **Fixes:**
  - `.chat-page .site-header` add `position: fixed; left: var(--sidebar-width); right: 0; padding-right: 32px` — chat page header stays fixed at 320px from sidebar brand. Non-chat pages keep `position: sticky`.
  - Converted `settings.html`, `approvals.html`, `guardrail.html` from `<main class="shell">` to `<main class="chat-page">` with full sidebar (session list, "Guarded Harness" brand).
  - Updated `app.py` routes for `/settings`, `/approvals`, `/guardrail` to pass `sidebar_groups` and `pending_approval_count`.
  - `.chat-page` `padding-top: 0 → 56px` — prevent fixed header from covering hero content.
- **Files changed:** `src/guarded_harness/web/static/styles.css`, `src/guarded_harness/web/templates/settings.html`, `src/guarded_harness/web/templates/approvals.html`, `src/guarded_harness/web/templates/guardrail.html`, `src/guarded_harness/web/app.py`, `tests/integration/test_web.py`.
- **Lesson:** Fixed sidebar + fixed header with a shared CSS variable for the offset ensures consistent cross-page layout. All pages should share the same structural skeleton.

## 2026-07-13 - Fix: approvals page redesign

- **Superpowers skills:** `brainstorming` (design alignment), `test-driven-development` (test updates to match new template), `verification-before-completion`.
- **Trigger:** User wanted approvals page to match other pages' design style.
- **Fixes:**
  - Replaced custom `approval-board` / `approval-board-header` / `approval-tabs` with `.hero` + `.panel` sections matching chat/settings page style.
  - Simplified approval items: removed nested h3/h4, used `strong` + `approval-meta` paragraph layout.
  - Status counts shown in hero subtitle: `Pending N · Executing N · Completed N · Failed N`.
  - "Technical details" → "Details", removed redundant approval/execution state lines.
  - Cleaned up CSS: removed `.approval-board`, `.approval-board-header`, `.approval-tabs`, `.approval-section` styles.
- **Files changed:** `src/guarded_harness/web/templates/approvals.html`, `src/guarded_harness/web/static/styles.css`, `tests/integration/test_web.py`.

## 2026-07-13 - Fix: message bubble and textarea spacing

- **Superpowers skills:** `brainstorming`, `test-driven-development`, `verification-before-completion`.
- **Trigger:** User requested tighter spacing in chat messages and input area.
- **Fixes:**
  - `.message` padding `12px 16px → 6px 14px`
  - `.composer-row textarea` padding `8px 14px → 4px 14px`
  - `textarea` min-height `44px → 36px`
  - `.composer-status` margin `1px → 0`
  - `.chat-page` bottom padding `150px → 100px`
  - Added `.composer-backdrop` (fixed white block, z-index 19) behind composer
- **Files changed:** `src/guarded_harness/web/static/styles.css`, `src/guarded_harness/web/templates/index.html`, `tests/integration/test_web.py`.

## 2026-07-13 - Fix: shell control syntax and file-target ls trace loop

- **Superpowers skills:** `systematic-debugging` (trace/root-cause analysis), `test-driven-development` (red/green shell policy regressions), `verification-before-completion`.
- **Trigger:** User provided a `恢复test.md` trace ending in `[max steps]`; the trace showed shell control syntax being sent to approval even though the executor rejects it after approval, plus `ls -la test.md` failing for an existing-file style target.
- **Root cause:** `classify_shell_command()` treated shell control syntax as approvable, but `parse_shell_argv()` rejects that syntax unconditionally. The pseudo `ls` implementation only accepted directories, unlike common shell behavior where `ls file` is a valid existence check.
- **Fixes:**
  - Shell control syntax now returns `policy_deny` with `shell control syntax is not supported; run one command at a time`, avoiding approval cards that cannot succeed.
  - Pseudo `ls` now supports file targets and returns the file entry instead of `ls target is not a directory`.
  - Provider action protocol now tells the model to emit single-argv shell commands only, and to `finish` with an explanation when observations prove no allowed recovery source exists.
- **TDD evidence:** Added/updated guardrail and dispatcher tests. The focused tests failed first with `needs_approval` / `ls target is not a directory`, then passed after implementation.

## 2026-07-13 - Fix: deny approval stops live Web session (superseded)

- **Superpowers skills:** `systematic-debugging` (trace/root-cause analysis), `test-driven-development` (Web approval regression), `verification-before-completion`.
- **Trigger:** User provided a trace where clicking Deny on `git status && git log --oneline` recorded `approval_denied`, but the live provider then continued with `git status`, `git log --oneline`, and finished the task.
- **Root cause:** Web `_resume_approval()` set `continue_after_resolution = True` for live sessions regardless of whether the approval was accepted or denied. That made Deny behave like "reject this exact action, then let the model try another action".
- **Fix:** Web approval resume now continues the live provider loop only when `approved` is true. Deny uses the non-continuing recovery path, records `approval_denied`, finishes the session, and avoids constructing/calling the live provider.
- **TDD evidence:** Added `test_denying_live_approval_stops_without_calling_provider`, asserting Deny does not construct the provider, does not show a provider continuation message, records `approval_denied`, and records `approval_recovery_ended`.
- **Superseded by:** The later three-button refinement splits this into `Deny action` (continue live provider) and `Stop task` (end the task).

## 2026-07-13 - Refine: split approval denial into action denial and task stop

- **Superpowers skills:** `brainstorming` (confirmed three-button semantics), `test-driven-development` (Web approval regressions), `verification-before-completion`.
- **Trigger:** User asked which approval denial behavior is better; we chose explicit buttons for both meanings instead of overloading one `Deny` action.
- **Fix:** Chat approval cards and the Approvals page now show `Approve once`, `Deny action`, and `Stop task`. `/approvals/{id}/deny` means "deny this action and let live provider try another route"; `/approvals/{id}/stop` means "deny and end this task". The processing UI now shows distinct `Denying action...` and `Stopping...` states.
- **TDD evidence:** Updated approval-card assertions and added regressions proving live `Deny action` continues with `approval_denied` feedback while live `Stop task` does not construct/call the provider and records `approval_recovery_ended`.

## 2026-07-13 - Fix: Docker provider settings keyring failure

- **Superpowers skills:** `systematic-debugging` (traced Settings form -> POST route -> keyring backend), `test-driven-development` (red/green Web regressions), `verification-before-completion`.
- **Trigger:** User ran the Docker image, opened Provider Settings, entered an API key, checked `Save key to OS keyring`, and saw `Internal Server Error`.
- **Root cause:** Docker/Linux containers normally do not have a usable desktop OS keyring. `POST /settings` called `CredentialStore.set_key()` directly, so keyring backend failures escaped FastAPI as 500 responses.
- **Fixes:**
  - Settings save now catches keyring failures and re-renders Provider Settings with a 400 status plus `Could not save API key: ...`.
  - The submitted API key is still never written to `provider.json`, SQLite, audit events, logs, or page output.
  - Added `GUARDED_HARNESS_API_KEY` as an environment-variable fallback for Docker/live provider usage.
  - README now documents Docker live mode with environment-variable injection and clarifies Python 3.11+ setup commands.
- **TDD evidence:** Added failing tests for keyring failure handling and environment API key use. They failed first with `RuntimeError: keyring unavailable` / `400 Bad Request`, then passed after the route/config changes.
- **Verification:** `pytest -q` -> `261 passed, 2 skipped`; `compileall src tests` passed; `git diff --check` passed. `docker build -t guarded-harness .` first hit a Docker Desktop BuildKit snapshot cache error at image export, then passed on retry.
- **Commit:** `459ba7a fix: handle keyring failures in provider settings`.

## 2026-07-13 - Fix: Provider Settings temporary API key in WebUI

- **Superpowers skills:** `systematic-debugging` (verified why Settings input did not affect later Chat runs), `test-driven-development` (red/green Web regression), `verification-before-completion`.
- **Trigger:** User reported that entering an API key in Provider Settings and clicking `Save provider` returned to Chat, but the key was not recorded and live mode still behaved as if no key existed.
- **Root cause:** Without `Save key to OS keyring`, `/settings` only persisted non-sensitive provider settings (`mode`, `base_url`, `model`). This was safe, but poor UX for Docker because keyring persistence is unavailable there.
- **Fix:** `create_app()` now keeps a submitted Settings API key in current-process memory when the user does not request keyring persistence. This key can be used by later Chat live sessions in the same server/container process, while remaining absent from disk, SQLite, audit traces, and rendered HTML. Restarting the container or server drops the key.
- **TDD evidence:** Added a failing integration test proving that a Settings-submitted key should mark the provider as configured and power a later live session without persisting the secret. It failed first with `key missing`, then passed after adding the process-local key.
- **Verification:** `pytest -q` -> `262 passed, 2 skipped`; `compileall src tests` passed; `git diff --check` passed.
- **Commit:** `4e33334 fix: keep web provider key for current process`.
