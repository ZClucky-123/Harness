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
