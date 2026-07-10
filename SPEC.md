# Guarded Harness SPEC

## 1. 问题陈述

Guarded Harness 要解决的问题是：如何把一个只会提出 coding action 的 LLM，封装成一个受控、可观察、可恢复的本地 coding-agent 系统。目标用户是希望实验 agentic software engineering 的开发者和学生，他们需要让 LLM 辅助读写代码、运行测试，但不能把 shell 和文件系统无限制交给 LLM。

本项目值得做，是因为 coding agent 的可靠性不只取决于模型能力，更取决于 harness 是否能提供边界、治理、反馈和审计。本项目聚焦 harness 层：确定性治理、人工审批、客观反馈、记忆与分发。

## 2. 用户故事

1. 作为开发者，我可以让 harness 在本地仓库中执行一个任务，以便观察每一步 action 后再决定是否信任系统。
2. 作为开发者，我可以使用 mock LLM 运行系统，以便测试和演示不依赖网络或付费 API。
3. 作为评审者，我可以看到危险动作被代码确定性拒绝，以便确认安全性不依赖提示词服从。
4. 作为操作者，我可以 approve 或 deny 敏感动作，以便 agent 在跨越风险边界前暂停。
5. 作为学生，我可以运行确定性机制演示，以便展示 harness 核心行为可被客观验证。
6. 作为用户，我可以打开最小 WebUI，以便查看任务状态、待审批动作和运行结果。

## 3. 功能规约

### Agent Loop

输入：任务文本、workspace root、配置、选中的 memory 和上一轮 observations。

行为：

- 为每轮构造上下文。
- 调用可 mock 的 LLM provider。
- 将 provider 响应解析为结构化 action。
- 将 action 交给 guardrail policy。
- 执行允许的 action。
- 对需要审批的 action 暂停并创建 HITL 请求。
- 将 parser、policy、tool 和 feedback 结果转为 observations。
- 在 `finish`、`waiting_approval`、`blocked`、`failed` 或 `max_steps` 时停止。

输出：session 状态与持久化运行轨迹。

错误处理：非法 JSON、未知 action、缺少字段和工具异常都转化为 observation，而不是让程序崩溃。

### Tools

支持的 actions：

- `read_file`：读取 workspace 内文件。
- `write_file`：写入 workspace 内文件。
- `run_shell`：在 workspace 内运行命令。
- `run_tests`：运行配置的测试命令。
- `remember`：写入 memory entry。
- `finish`：带消息结束 session。

所有文件路径都相对 workspace root 解析。workspace 外路径必须拒绝。

### Governance And HITL

Guardrail 返回三类判定：

- `allow`：立即执行。
- `deny`：不执行，并把 `policy_denied` observation 回灌给 loop。
- `needs_approval`：创建 approval request 并暂停 session。

直接拒绝的动作包括：破坏性系统命令、格式化磁盘、访问敏感系统路径、写入 workspace 外路径。

需要审批的动作包括：发布、`git push`、安装依赖、删除 workspace 内文件、修改 `.env`。

审批行为：

- approve：恢复执行被暂停的 action。
- deny：向 loop 回灌 `approval_denied` observation，使 LLM 选择替代 action。

### Feedback

Feedback sensor 将结果分类为 `tool_success`、`test_failure`、`lint_failure`、`command_error`、`policy_denied` 或 `approval_denied`。分类结果进入下一轮 LLM 上下文。

### Memory

Memory store 持久化项目约定、审批结果、历史决策和失败摘要。Loop 只检索最近或相关条目，而不是全量载入。

### CLI

CLI 支持任务运行、WebUI 启动、审批操作、凭据管理和确定性演示。

### WebUI

WebUI 支持新建任务、查看 session 轨迹、列出待审批请求、approve/deny 请求、查看最终状态。

## 4. 非功能性需求

### 性能

Mock 模式下的测试和演示应能在本地开发机器上快速完成。Agent loop 必须强制 `max_steps`，避免无限执行。

### 安全

Harness 不信任 LLM 输出。每个 action 都必须经过解析、校验、workspace 边界检查和 guardrail 策略判断。

凭据威胁模型：

- API key 不得提交到仓库。
- API key 不得出现在日志、审计事件、CLI 输出或 WebUI 页面中。
- 优先通过 Python `keyring` 存入系统凭据管理器。
- `.env` 只作为本地开发 fallback，并明确说明它是明文风险。

### 可用性

核心系统必须能在无网络环境下以 mock 模式运行。真实 provider 失败时，应转化为 observation 或用户可见错误，而不是崩溃。

### 可观测性

Audit events 记录 session 生命周期、actions、policy decisions、approval requests、approval outcomes 和 tool results。

## 5. 系统架构

```text
CLI --------\
            -> Harness Core -> LLM Provider
WebUI ------/       |
                   |-> Action Parser
                   |-> Guardrail + HITL
                   |-> Tool Dispatcher
                   |-> Feedback Sensor
                   |-> Memory Store
                   |-> Audit Log
```

外部依赖：

- Python runtime
- FastAPI
- Typer
- pytest
- SQLite
- 可选 Python `keyring`
- 可选 OpenAI-compatible API endpoint
- Docker

## 6. 数据模型

- `Action`：type、payload、raw source text。
- `Observation`：success flag、feedback kind、message、stdout、stderr、metadata。
- `PolicyDecision`：decision、risk level、reason。
- `ApprovalRequest`：id、session id、action、reason、status、created time、resolved time。
- `SessionState`：id、task、status、step count、pending approval id、observations。
- `AuditEvent`：timestamp、session id、event type、payload。
- `MemoryEntry`：id、kind、content、tags、created time。

## 7. 凭据与分发设计

凭据命令：

- `harness credentials set`
- `harness credentials status`
- `harness credentials clear`

正式分发使用 Docker：

- `docker build -t guarded-harness .`
- `docker run -p 8000:8000 guarded-harness`

Docker 默认启动 FastAPI WebUI。README 还会说明本地 CLI 执行和 mock 模式演示。

## 8. 技术选型与理由

- Python：实现快，测试生态成熟，适合 CLI 与 Web 服务。
- FastAPI：适合小型 WebUI/API，部署简单。
- Typer：CLI 命令定义清晰。
- pytest：适合确定性单元测试和集成测试。
- SQLite：适合本地持久化 sessions、approvals、memory 和 audit events。
- Docker：符合课程分发要求，便于从零运行。

## 9. 领域与机制设计

Coding 场景的反馈信号：

- 测试命令退出码
- lint 命令退出码
- shell stdout 和 stderr
- parser errors
- policy decisions
- approval outcomes

危险动作：

- 破坏性 shell 命令
- 写入 workspace 外路径
- 访问敏感系统路径
- 发布或 push
- 安装依赖
- 修改 `.env`

所需工具：

- 文件读写
- shell 执行
- 测试执行
- memory 写入
- finish

记忆需求：

- 项目约定
- 历史审批决策
- 重复失败摘要
- 任务摘要

重点维度：

本项目的主要贡献是治理：确定性 guardrail、workspace 边界、HITL 审批状态、审批恢复和 audit logging。这些机制全部由代码实现，并通过 mock LLM 测试验证。

## 10. 验收标准

- `pytest` 在 mock LLM、无网络条件下通过。
- mock LLM 请求危险命令时，guardrail 确定性拒绝。
- mock LLM 请求需要审批的命令时，session 暂停。
- approve pending request 后，系统恢复执行被暂停 action。
- deny pending request 后，系统向 loop 回灌 `approval_denied` observation。
- feedback demo 展示 mock LLM 在收到失败 observation 后改变下一步 action。
- CLI 可以运行 demos 并管理 approvals。
- WebUI 可以创建任务、展示轨迹、approve 或 deny 待审批动作。
- Docker image 可以构建并启动 WebUI。
- `.gitlab-ci.yml` 包含 `unit-test` job。
- README 说明安装、运行、Docker、凭据和安全边界。

## 11. 风险与未决问题

- 真实 LLM 集成可能不稳定。它保持可选，直到 mock-mode core 完成。
- WebUI 范围可能膨胀。它被限制为 task、trace、approval 和 result 视图。
- Policy 规则可能过宽或过窄。规则会明确编码，并通过测试逐步扩展。
- 冷启动验证可能暴露 SPEC 或 PLAN 的缺失细节。实现前会根据验证反馈修订文档。
