# Guarded Harness 设计文档

## 摘要

Guarded Harness 是一个面向小型本地代码仓库的 coding-agent harness。LLM 只负责提出结构化动作，真正的执行由我们自己编写的代码控制：agent 主循环、动作解析器、工具分发器、治理护栏、HITL 人工审批状态机、反馈传感器、记忆存储与审计日志。

本项目的主要贡献是治理层：危险或敏感动作不依赖提示词约束，而是由确定性的策略代码分类为允许、拒绝或暂停等待人工审批。整个核心机制可以用 mock LLM 在无网络环境下端到端测试。

## 目标

- 实现一个自有 coding-agent harness 内核，而不是配置现成 agent 框架。
- 提供可注入 mock 的 LLM 抽象，使核心机制可以离线单测。
- 将治理作为重点维度：护栏、工作区边界、HITL 审批、审批恢复、审计日志。
- 在同一套核心之上提供 Typer CLI 与最小 FastAPI WebUI。
- 使用 Docker 分发，并提供清晰的本地运行和容器运行说明。

## 非目标

- 不基于 LangChain AgentExecutor、AutoGen、CrewAI、LlamaIndex agent runner 或编码智能体 SDK 的高层循环。
- 不尝试构建生产级完全自主 coding agent。
- 不把 WebUI 作为主要工程贡献。
- 不要求真实 LLM 或网络参与核心测试、机制演示和评分验证。

## 架构

系统有两个用户入口：

- Typer CLI：用于本地演示和操作，包括运行任务、查看 session、审批或拒绝待处理动作、管理凭据。
- FastAPI WebUI：用于提交任务、查看运行轨迹、处理审批队列和查看最终结果。

两个入口都调用同一套 harness core。

核心流程：

1. 加载任务、配置、记忆和最近 observations。
2. 调用配置的 LLM provider。
3. 将 provider 响应解析为结构化 `Action`。
4. 将 action 交给 guardrail 生成 `PolicyDecision`。
5. 如果允许，交给 tool dispatcher 执行。
6. 如果拒绝，生成 policy observation 回灌给主循环。
7. 如果需要审批，创建 `ApprovalRequest` 并暂停 session。
8. 通过 feedback sensor 分类工具输出。
9. 持久化 audit events 和 memory entries。
10. 在 finish、failure、blocked、pending approval 或 `max_steps` 时停止。

## 组件

### Agent Loop

负责 context 构造、LLM 调用、动作解析、策略检查、工具执行、结果观察和停机判断。模型输出格式错误或工具异常不会让程序崩溃，而是转化为 observation。

### LLM Providers

`LLMProvider` 接口提供一个接收上下文并返回文本的方法。`MockLLM` 返回脚本化响应，用于测试和演示。可选的 OpenAI-compatible provider 可用于真实运行，但核心测试不依赖它。

### Action Parser

将 LLM 输出解析为 JSON action。支持的动作包括：

- `read_file`
- `write_file`
- `run_shell`
- `run_tests`
- `remember`
- `finish`

未知动作类型、缺少字段和非法 JSON 都会变成确定性的 parser observation。

### Tool Dispatcher

将有效 action 分发到文件、shell、测试、记忆和 finish handler。文件与 shell action 都必须在配置的 workspace root 内执行。

### Governance

Guardrail 将 action 分类为 `allow`、`deny` 或 `needs_approval`。

直接拒绝的例子：

- `rm -rf /`
- 格式化磁盘命令
- 写入 workspace 外路径
- 读取敏感系统路径

需要审批的例子：

- `git push`
- 发布命令
- 安装依赖
- 删除 workspace 内文件
- 修改 `.env`

允许的例子：

- 读取 workspace 内文件
- 写入 workspace 内普通源码文件
- 运行测试
- 写入记忆
- 完成任务

HITL 状态机支持：

- `running -> waiting_approval`
- approve 后 `waiting_approval -> running`
- deny 后带拒绝 observation 返回 `waiting_approval -> running`
- `running -> finished | failed | blocked`

每次策略判定、审批请求、审批结果和恢复执行都会记录为 audit event。

### Feedback Sensor

将命令和测试结果分类为：

- `test_failure`
- `lint_failure`
- `command_error`
- `policy_denied`
- `approval_denied`
- `tool_success`

这些 observations 会进入下一轮 loop。mock LLM 演示会展示模型在收到失败 observation 后改变下一步动作。

### Memory

Memory 记录项目约定、历史决策、失败摘要和审批结果。优先使用 SQLite，因为 CLI 与 WebUI 都能方便查询。每轮只注入最近或相关条目，不把全部记忆塞给 LLM。

### Configuration And Credentials

配置包括 workspace root、max steps、provider 选择、policy 选项和数据库路径。凭据优先通过 Python `keyring` 存入系统凭据管理器。`.env` 只作为开发 fallback，并在文档中明确其明文风险。日志不得输出 secret 明文。

## 数据模型

- `Action`：LLM 请求执行的操作。
- `Observation`：解析器、策略、工具或反馈传感器产生的客观结果。
- `PolicyDecision`：`allow`、`deny` 或 `needs_approval`。
- `ApprovalRequest`：待处理或已处理的 HITL 记录。
- `SessionState`：任务、状态、observations、step count 和 pending approval。
- `AuditEvent`：动作、策略判定、审批和工具结果的不可变记录。
- `MemoryEntry`：持久化的项目知识或运行摘要。

## CLI

计划命令：

- `harness run "<task>"`
- `harness serve`
- `harness approvals list`
- `harness approvals approve <id>`
- `harness approvals deny <id>`
- `harness credentials set`
- `harness credentials status`
- `harness credentials clear`
- `harness demo guardrail`
- `harness demo hitl`
- `harness demo feedback`

## WebUI

WebUI 保持最小可用：

- 任务输入
- session 轨迹
- 待审批列表
- approve 和 deny 按钮
- 最终状态和结果

它用于满足可访问界面要求，工程深度仍集中在 harness kernel。

## 测试策略

测试使用 `pytest` 和 `MockLLM`。

单元测试覆盖：

- action parser
- guardrail 策略判定
- workspace 路径边界
- HITL 状态转移
- dispatcher 行为
- feedback 分类
- memory 读写
- 凭据状态查询不泄露 secret

集成测试覆盖：

- mock LLM 请求危险动作，guardrail 拒绝
- 需要审批的 action 触发 HITL 暂停和恢复
- 审批拒绝被回灌给 loop
- 命令或测试失败反馈使 mock LLM 下一步动作改变

验证命令：

- `pytest`
- `python -m compileall src`
- `docker build -t guarded-harness .`

## 机制演示

项目包含确定性演示：

1. Guardrail demo：mock LLM 请求 `rm -rf /`，策略拒绝。
2. Feedback demo：mock LLM 先产生失败动作，feedback 被分类后下一次响应改变。
3. HITL demo：mock LLM 请求 `git push`，session 暂停等待审批；approve 后恢复，deny 后回灌 `approval_denied` observation。

## 分发

Docker 是正式分发路径。镜像默认启动 FastAPI WebUI。README 将包含本地开发、Docker build/run、mock 模式、真实 provider 配置、安全边界和已知限制。

CI 使用 `.gitlab-ci.yml`，包含 `unit-test` job。如时间允许，额外加入 Docker build job。

## 风险

- 范围可能滑向大型 UI。缓解：WebUI 保持最小可用。
- 真实 LLM 集成可能消耗时间并导致测试不稳定。缓解：mock 模式一等支持，真实 provider 可选。
- Guardrail 策略可能过于模糊。缓解：用明确命令和路径规则编码，并直接测试。
- SPEC 与 PLAN 可能依赖隐性对话上下文。缓解：写清接口，并在实现前进行冷启动 agent 验证。
