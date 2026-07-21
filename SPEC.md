# Guarded Harness SPEC

## 1. 问题陈述

Guarded Harness 要解决的问题是：如何把一个只会提出 coding action 的 LLM，封装成一个受控、可观察、可恢复的本地 coding-agent 系统。目标用户是希望实验 agentic software engineering 的开发者和学生，他们需要让 LLM 辅助读写代码、运行测试，但不能把 shell 和文件系统无限制交给 LLM。

本项目值得做，是因为 coding agent 的可靠性不只取决于模型能力，更取决于 harness 是否能提供边界、治理、反馈和审计。本项目聚焦 harness 层：确定性治理、人工审批、客观反馈、记忆与分发。

### 范围与非范围

项目范围包括：

- 结构化 action 协议。
- mockable LLM provider 抽象。
- workspace-bounded 文件和 shell 工具。
- guardrail policy 与 HITL approval。
- SQLite session、approval、audit 和 memory store。
- CLI demo、approval 管理和凭据管理。
- FastAPI WebUI、session trace、approval queue 和 Guardrail Demo。
- Docker 与 GitHub Actions 分发/验证入口。

项目非范围包括：

- 不实现通用 IDE 插件。
- 不实现多用户权限系统。
- 不把安全决策交给提示词或模型自我约束。
- 不持久化完整 live provider 对话 checkpoint。
- 不把 SQLite 状态库设计为加密 secrets vault。

## 2. 用户故事

1. 作为开发者，我可以让 harness 在本地仓库中执行一个任务，以便观察每一步 action 后再决定是否信任系统。
2. 作为开发者，我可以使用 mock LLM 运行系统，以便测试和演示不依赖网络或付费 API。
3. 作为评审者，我可以看到危险动作被代码确定性拒绝，以便确认安全性不依赖提示词服从。
4. 作为操作者，我可以批准一次动作、拒绝当前动作或停止任务，以便 agent 在跨越风险边界前暂停，并让不同审批意图有明确语义。
5. 作为学生，我可以运行确定性机制演示，以便展示 harness 核心行为可被客观验证。
6. 作为用户，我可以打开最小 WebUI，以便查看任务状态、待审批动作和运行结果。

## 3. 功能规约

### Agent Loop

输入：任务文本、workspace root、配置、选中的 memory 和上一轮 observations。

每一轮 loop 的核心不变量是：LLM 只能返回文本，文本必须先解析为受支持的 action，
action 必须先通过 policy，允许后的工具结果必须回到 observation。任何一层失败都不会
绕过治理进入执行层，而是被记录、审计并反馈给下一轮。

行为：

- 为每轮构造上下文。
- 调用可 mock 的 LLM provider。
- 将 provider 响应解析为结构化 action。
- 将 action 交给 guardrail policy。
- 执行允许的 action。
- 对需要审批的 action 暂停并创建 HITL 请求。
- 将 parser、policy、tool 和 feedback 结果转为 observations。
- 在 `finish`、`waiting_approval`、`failed` 或 `max_steps` 时停止；`blocked` 是保留状态，当前主循环不主动产生。

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

`run_shell` 会先把命令解析为 argv，再以 `shell=False` 执行。管道、重定向、命令替换、
逻辑连接、多行命令等 shell control syntax 不被支持，避免 policy 判断和真实 executor
解释语义不一致。为兼顾 Windows 演示体验，常见只读伪命令如 `ls`、`dir`、`pwd`、
`cat`、`type`、`echo` 由项目代码显式处理；删除类伪命令会进入审批或被拒绝。

### Governance And HITL

Guardrail 返回三类判定：

- `allow`：立即执行。
- `deny`：不执行，并把 `policy_denied` observation 回灌给 loop。
- `needs_approval`：创建 approval request 并暂停 session。

直接拒绝的动作包括：破坏性系统命令、格式化磁盘、访问敏感系统路径、写入 workspace 外路径。

需要审批的动作包括：发布、`git push`、安装依赖、删除 workspace 内文件、修改 `.env`。

审批行为：

- approve：恢复执行被暂停的 action；在 Web live session 中，如 provider 配置和 key 仍可用，则继续后续 provider loop。
- deny action：向 loop 回灌 `approval_denied` observation；Web live session 会让 provider 基于该反馈尝试替代 action。
- stop task：拒绝当前 action 并结束本轮恢复，不再继续调用 provider。

CLI 的 `approvals approve/deny` 是跨进程恢复入口。它只处理已审批动作或拒绝反馈，然后记录 `approval_recovery_ended` 并结束本轮恢复；它不会静默重建先前 live provider 的对话上下文。

审批 action 和 reason 在入库前执行 secret 检测。包含 API key、Bearer token、password、常见 provider token 或 private key 的 action 会被拒绝创建；历史遗留数据在 CLI/Web 展示时仍会脱敏。

审批状态机的目标是让“暂停”和“恢复”成为可审计状态，而不是内存中的临时判断。
pending approval 持有原始 action 和 reason；批准时 action 被标记为 executing，执行成功
后标记为 executed，失败则标记为 failed；拒绝则标记为 denied，并产生
`approval_denied` observation。

### Feedback

Feedback sensor 将结果分类为 `tool_success`、`test_failure`、`lint_failure`、`command_error`、`policy_denied` 或 `approval_denied`。分类结果进入下一轮 LLM 上下文。

### Memory

Memory store 持久化项目约定、审批结果、历史决策和失败摘要。Loop 只检索最近或相关条目，而不是全量载入。

### CLI

CLI 支持任务运行、交互模式、WebUI 启动、审批操作、凭据管理、provider 配置初始化和确定性演示。

`harness run "<task>"` 是一次性任务入口。`harness run` 在没有 task 参数时进入交互模式；
交互模式中每条普通输入都会创建一个新的 harness session，并复用当前 workspace、
SQLite 状态库和 provider 配置。交互命令包括 `:help`、`:mode`、`:approvals`、
`:exit` 和 `:quit`。

### WebUI

WebUI 支持新建任务、Provider Settings、session trace、approvals queue、approval card 和最终状态展示。审批卡片提供三个明确动作：`Approve once`、`Deny action`、`Stop task`。Guardrail Demo 保留为可直接访问页面，但不出现在主导航中。

WebUI 采用服务端渲染，避免引入前端构建系统。Chat Workspace 负责启动任务和展示会话；
Provider Settings 负责 provider mode、base URL、model 与 API key 输入；Session Trace
负责展示审计事件和 observation；Approvals Queue 负责集中处理待审批动作；Guardrail
Demo 用确定性 policy 调用展示机制本身。

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

安全边界按 fail-closed 设计：解析失败不执行，未知 action 不执行，workspace 外路径不执行，
shell control syntax 不执行，疑似 secret 的审批 action 不入库。系统更愿意产生一个
可解释的 observation，而不是猜测用户或模型的真实意图。

### 可用性

核心系统必须能在无网络环境下以 mock 模式运行。真实 provider 失败时，应转化为 observation 或用户可见错误，而不是崩溃。

### 可观测性

Audit events 记录 session 生命周期、actions、policy decisions、approval requests、approval outcomes 和 tool results。

可观测性服务两个目的：一是方便开发者调试 agent loop 为什么走到当前状态；二是让课程评审者
能看到安全机制的证据链。Web session trace 和 CLI audit 输出都只展示脱敏后的信息。

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

代码组织上，`src/guarded_harness/core` 保存 action、observation、session 和 loop；
`governance` 保存 guardrail、approval、audit 与 redaction；`tools` 保存文件、shell、
测试和 dispatcher；`memory` 保存 SQLite 状态；`config` 保存 provider 配置与凭据入口；
`web` 保存 FastAPI、模板和静态资源。CLI 与 WebUI 共用同一套核心 loop 和 SQLite store。

外部依赖：

- Python runtime
- FastAPI
- Typer
- pytest
- SQLite
- 可选 Python `keyring`
- 可选 OpenAI-compatible API endpoint
- Docker
- GitHub Actions

## 6. 数据模型

- `Action`：type、payload、raw source text。
- `Observation`：success flag、feedback kind、message、stdout、stderr、metadata。
- `PolicyDecision`：decision、risk level、reason。
- `ApprovalRequest`：id、session id、action、reason、status、created time、resolved time。status 包括 `pending`、`executing`、`denied`、`executed`、`failed`。
- `SessionState`：id、task、status、step count、pending approval id、observations。
- `AuditEvent`：timestamp、session id、event type、payload。
- `MemoryEntry`：id、kind、content、tags、created time。

## 7. 凭据与分发设计

凭据命令：

- `harness credentials set`
- `harness credentials status`
- `harness credentials clear`

配置初始化命令：

- `harness config init`
- `harness config init --force`

正式分发使用 Docker：

- `docker build -t guarded-harness .`
- `docker run -p 8000:8000 guarded-harness`

Docker 默认启动 FastAPI WebUI。README 还会说明本地 CLI 执行和 mock 模式演示。

统一 provider 配置文件为 `.guarded-harness/provider.json`。刚 clone 的 workspace 可以通过
`harness config init` 自动生成该文件；仓库内的 `config/provider.example.json` 作为可提交示例。
配置文件只保存非敏感配置：

```json
{
  "mode": "live",
  "base_url": "https://njusehub.info/v1",
  "model": "deepseek-v4-flash",
  "timeout": 30
}
```

CLI 和 WebUI 都围绕这组字段工作。加载优先级为：命令行显式选项、环境变量、
`.guarded-harness/provider.json`、内置默认值。API key 不允许写入该文件。

Docker/Linux 容器中通常没有可用的桌面 OS keyring，因此 live provider 还支持 `GUARDED_HARNESS_API_KEY` 环境变量。WebUI Provider Settings 中未勾选保存的 API key 只保留在当前 FastAPI 进程内，供后续 live Chat 使用；它不写入 `provider.json`、SQLite、审计事件、日志或 HTML，服务重启后失效。

持续集成使用 GitHub Actions，配置文件为 `.github/workflows/ci.yml`。workflow 在
Python 3.11 和 3.12 上安装 `.[dev]`，运行 `pytest -q`，并执行
`python -m compileall src tests`。CI 不需要真实 LLM key，因为核心验收依赖 MockLLM
和 stub provider。

## 8. 技术选型与理由

- Python：实现快，测试生态成熟，适合 CLI 与 Web 服务。
- FastAPI：适合小型 WebUI/API，部署简单。
- Typer：CLI 命令定义清晰。
- pytest：适合确定性单元测试和集成测试。
- SQLite：适合本地持久化 sessions、approvals、memory 和 audit events。
- Docker：符合课程分发要求，便于从零运行。
- GitHub Actions：与当前 GitHub 仓库匹配，能在提交和 pull request 上自动重复本地验证。

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
- approve pending request 后，系统恢复执行被暂停 action；Web live session 可在 key 可用时继续 provider loop。
- deny action 后，系统向 loop 回灌 `approval_denied` observation；Web live session 可继续尝试替代 action。
- stop task 或 CLI 跨进程 deny 后，系统记录拒绝反馈并结束恢复轮次。
- feedback demo 展示 mock LLM 在收到失败 observation 后改变下一步 action。
- CLI 可以运行 demos 并管理 approvals。
- CLI 在无 task 参数时可以进入交互模式，并支持 `:mode`、`:approvals` 和退出命令。
- WebUI 可以创建任务、展示轨迹，并通过 `Approve once`、`Deny action`、`Stop task` 处理待审批动作。
- Docker image 可以构建并启动 WebUI。
- `.github/workflows/ci.yml` 包含 Python 3.11/3.12 测试矩阵。
- README 说明安装、运行、Docker、凭据和安全边界。

## 11. 验证矩阵

| 能力 | 验证方式 |
| --- | --- |
| action parser | `tests/unit/test_actions.py` |
| SQLite store/audit/memory | `tests/unit/test_store.py` |
| guardrail policy | `tests/unit/test_guardrail.py` |
| dispatcher 与 shell 边界 | `tests/unit/test_dispatcher.py` |
| loop 策略拒绝和反馈 | `tests/integration/test_loop_*` |
| HITL 审批恢复 | `tests/integration/test_hitl.py` |
| CLI demos 和凭据命令 | `tests/integration/test_cli.py` |
| provider config file | `tests/unit/test_config_loader.py` |
| interactive CLI | `tests/integration/test_cli.py` |
| WebUI 页面与交互 | `tests/integration/test_web.py` |
| Python 编译检查 | `python -m compileall -q src tests` |
| CI 重复验证 | `.github/workflows/ci.yml` |

## 12. 风险与未决问题

- 真实 LLM 集成可能不稳定。它保持显式 opt-in；provider 必须返回可解析的 action JSON，否则错误会进入 observation 或用户可见错误。
- WebUI 范围可能膨胀。它被限制为 Chat、Provider Settings、Session Trace、Approvals 和 Guardrail Demo。
- Policy 规则可能过宽或过窄。规则会明确编码，并通过测试逐步扩展。
- 跨进程 live provider 对话尚未持久化。CLI 审批恢复只执行已审批动作或记录拒绝反馈并结束本轮；Web live session 仅在同一进程中复用已保存或临时输入的 key 继续。
- SQLite 状态库不是加密 secrets vault；当前策略是拒绝新 secret action 入库，并对历史数据显示时脱敏。
- 冷启动验证记录和 Superpowers 过程产物已归档在 `docs/archive/superpowers/`，根目录保留最终交付文档。
