# Guarded Harness 过程记录

## Brainstorming 的关键问题

- LLM 应只提出 action，还是直接掌握文件与 shell 权限？
- 如何让危险操作的结果可复现、可观察，并且不依赖模型是否遵守提示词？
- 人工审批在何处暂停、如何持久化、拒绝后怎样把反馈交回 loop？
- 如何同时满足离线演示、命令行操作和最小 WebUI？
- 如何保证 API key 不进入代码库、审计事件或用户界面？

这些问题使方案从“调用模型完成任务”转向“由 harness 执行受治理的 action”。

## 技术选择

Python 适合快速实现可测试的本地自动化工具，也能共享 CLI 与 Web 的核心代码。FastAPI
提供轻量的应用工厂与服务端页面入口；Typer 使演示、凭据和审批命令保持清晰。SQLite
负责本地 session、审计、memory 与审批状态。Docker 则把 Python 版本、依赖和 WebUI
启动命令固定为可复现的分发单元，满足从零启动的交付要求。

技术选择的另一个原则是“机制可替换，治理不可替换”。LLM provider 可以从 MockLLM
替换为 OpenAI-compatible endpoint，WebUI 也可以从最小页面扩展为更完整的 console；
但 action parser、guardrail、workspace 边界、approval store 和 audit log 必须始终留在
项目代码中。这一原则避免把作业核心贡献隐藏到外部框架或模型行为里。

## 主要贡献：治理与 HITL

项目的中心不是让 LLM 直接执行任意命令，而是确定性的治理流程：解析 action、校验
workspace 边界、策略决定 allow/deny/needs_approval、记录审计事件，并在审批后恢复或
向 loop 回馈 `approval_denied`。这使 MockLLM 能覆盖策略拒绝、工具失败和恢复状态机，
将安全性从提示词约束提升为代码路径约束。

## 关键迭代

1. 先确立 `Action`、`Observation`、`SessionState` 等可序列化核心类型，避免 provider
   与工具实现耦合。
2. 将 SQLite 审计与审批状态放在 loop 之外持久化，使暂停、批准、拒绝能够跨命令恢复。
3. 把 guardrail 的策略判定置于 dispatcher 前，明确区分拒绝和待审批，并让结果成为下一轮
   observation。
4. 加入 MockLLM 的离线 CLI demos 与最小 FastAPI WebUI，使机制能够不依赖网络演示。
5. 最后补充 Docker、GitHub Actions 和交付文档，使应用工厂具有一致的构建与运行入口。

每个阶段结束时都留下一个可观察结果：要么是一个通过的测试文件，要么是一条 CLI demo，
要么是一个 Web 页面行为。这样做的好处是，项目不是等到最后才组合成一个大系统，而是
逐步形成可运行、可复审的小闭环。

## TDD 与复审证据

TDD 的重点不是追求测试数量，而是先定义风险行为。比如 guardrail 阶段先写
`rm -rf /`、`git push`、workspace 外写入等失败/审批用例；dispatcher 阶段先写
shell 成功、命令错误和 workspace 文件读写；HITL 阶段先写 pending approval、approve
恢复和 deny feedback。后续 shell 加固时，又补充 command substitution、管道、重定向、
换行和 symlink 等绕过场景，确保 executor 层也 fail-closed。

复审中发现的一个重要问题是：只在 policy 层拒绝危险字符串并不充分，因为 executor
如果仍以系统 shell 解释字符串，可能出现 policy 与真实执行语义不一致。最终修正为
统一 argv 解析、`shell=False` 执行和 workspace realpath 边界校验。这个问题被写入
`REFLECTION.md`，因为它体现了 AI 辅助开发中“测试承诺”和“执行事实”之间的差距。

## 测试与评审过程

实现阶段按任务使用 brainstorming、writing-plans、worktree、TDD、代码评审与最终验证
流程。单元测试覆盖模型、存储、策略和 dispatcher；集成测试覆盖 agent loop、失败反馈、
HITL、CLI 与 WebUI。交付前使用 Python 3.11 虚拟环境执行完整 `pytest -q`、
`compileall src tests` 与 diff 检查，并把结果同步到 `README.md` 与 `AGENT_LOG.md`。

## 冷启动验证

独立 agent 仅依据 `SPEC.md` 和 `PLAN.md` 复核任务拆分时，重点检查了核心类型、
guardrail、dispatcher、HITL 与 WebUI 是否能从规约推出可验证行为。复核结论是：
项目的主线可以按 Task 1--9 顺序重建；后续 UI 与凭据增强作为 Task 12--14 记录在
`PLAN.md` 和 `AGENT_LOG.md`，不改变核心架构，只补充真实 provider 与演示体验。

| 日期 | 范围 | 结果 | 发现与后续动作 |
| --- | --- | --- | --- |
| 2026-07 | SPEC + PLAN 冷启动复核 | 通过 | 明确 shell 必须 `shell=False`、审批语义拆为三种按钮、跨进程 live provider 不伪装持续上下文。 |

冷启动复核后的文档修订包括：把 `blocked` 标为保留状态、把审批拒绝拆成
`Deny action` 与 `Stop task`、补充 approval 执行状态、补充 API key 进程内临时保存策略、
以及把 CI 入口对齐为 GitHub Actions。

## 阶段 6：Live Provider 与 WebUI

在本地接入 NJU SE Hub 后，发现真实模型默认返回自然语言，而 harness 主循环只接受 action JSON。这暴露的是 provider 适配层问题，而不是治理机制问题。处理策略是在 `OpenAICompatibleProvider` 中加入明确的 action JSON 输出协议，并清洗常见的 fenced JSON 响应；同时把 WebUI 从固定 MockLLM 扩展为 Mock/Live 双模式，允许用户输入 OpenAI-compatible base URL、model 和 API key。

该变更符合项目要求：API key 仍通过隐藏输入和 OS keyring 管理，不写入源码、审计事件或 session；真实 LLM 调用仍只是单次 provider 能力，agent loop、guardrail、HITL 状态机、反馈分类和工具分发仍由项目代码实现，并继续通过 mock/stub LLM 的确定性测试验证。

这个阶段的取舍是：允许真实 provider 参与演示，但不把验收建立在真实 provider 的稳定性上。
如果 provider 返回自然语言或非法 JSON，系统会产生 parser/provider observation，而不是
跳过 action 协议直接执行自然语言意图。

## 阶段 7：中文展示与 WebUI 打磨

WebUI 原先直接使用 Jinja `tojson` 展示 trace payload，导致中文在页面源码中显示为 `\uXXXX`。修复方式是在模板层使用 `ensure_ascii=False` 的 JSON filter，让用户看到可读中文；这不改变数据库写入和审计模型。页面视觉经历了历史 UI 参考和后续截图驱动修正，最终收敛为简洁的 Chat Workspace：固定左侧 session sidebar、底部 composer、审批卡片和统一的 settings/trace/approvals 页面。该修复服务于演示与可用性，不影响核心 harness 判断逻辑。

## 阶段 8：本地 Agent Console

进一步将 WebUI 拆为 Chat Workspace、Provider Settings、Session Trace、Approvals Queue 和 Guardrail Demo。Provider Settings 只持久化非敏感配置；API key 可由 keyring 管理，也可在当前 FastAPI 进程中临时保存。审批卡片最终拆成 `Approve once`、`Deny action`、`Stop task` 三种明确语义：批准执行本次动作，拒绝动作则让 live provider 带着 `approval_denied` 反馈尝试替代路线，停止任务则结束恢复轮次。Guardrail Demo 给评审者提供一个无需真实 LLM 的确定性机制演示入口，但不放在主导航中。

## 阶段 9：Docker 与凭据处理

在 Docker 环境中实测 WebUI 后，发现容器内通常没有可用的桌面 OS keyring。原实现把 Provider Settings 中勾选保存 key 的失败直接暴露为 FastAPI 500，虽然没有泄露 secret，但不符合可演示交付的可用性要求。修复后，keyring 保存失败会回到设置页显示明确错误；同时支持 `GUARDED_HARNESS_API_KEY` 作为 Docker/live provider 的环境变量入口。

进一步的前端验证显示，用户在 Provider Settings 输入 API key 但不勾选保存时，非敏感 provider 配置会保存，key 本身不会被后续 Chat 使用。这一行为虽然安全，但在 Docker 中不实用。最终策略是把未保存的 key 仅保留在当前 FastAPI 进程内：它不进入 `provider.json`、SQLite、审计事件、日志或页面源码，容器重启后自然失效。这样同时满足演示可用性和“API key 不落盘、不入审计”的作业安全要求。

本轮修复通过新增 Web 集成测试验证：keyring 不可用时不再 500，环境变量 key 可驱动 live provider，Settings 中临时输入的 key 可供当前进程的后续 Chat 使用且不持久化。最终本地验证结果为 `262 passed, 2 skipped`，`compileall src tests` 通过，Docker 镜像在 Docker Desktop 缓存异常后重试构建通过。

## 阶段 10：统一配置文件与交互式 CLI

提交前复核使用说明时，发现 WebUI 已经能把非敏感 provider 配置写入
`.guarded-harness/provider.json`，但 CLI 只读取环境变量和 OS keyring。这会让用户在
WebUI 配好 base URL/model 后，CLI 仍然需要重复设置环境变量。修复方向是把
`provider.json` 提升为 CLI/WebUI 共用的非敏感配置文件，同时明确 API key 不进入该文件。

本阶段还增加 `harness run` 无参数交互模式，用于贴近常见 coding-agent harness 的 CLI
体验。设计上没有把它伪装成长上下文聊天：每条普通输入会创建一个新的 session，复用同一
workspace、配置文件和 SQLite 状态库。这样既满足交互式入口，又不引入额外 provider
checkpoint 风险。

本轮采用 TDD：先写 `tests/unit/test_config_loader.py` 验证 provider 文件读取、环境变量覆盖
和 API key 不从文件加载；再写 CLI 集成测试验证配置文件驱动 live run，以及
`harness run` 无参数进入交互模式。测试先失败后实现，最终完整验证结果为
`266 passed, 2 skipped`。

随后从“刚 clone 仓库的用户没有 `.guarded-harness` 目录”这一使用场景出发，继续补充
`harness config init`。该命令负责创建 `.guarded-harness/provider.json` 并写入默认 live
provider 配置；已有配置默认不覆盖，需要重置时使用 `--force`。仓库同时提供
`config/provider.example.json` 作为手动配置参考。该补充仍保持 API key 不进入 provider
文件的边界。

## 交付状态

当前交付材料分为三层：

- 根目录文档：`README.md`、`SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、`REFLECTION.md`、
  `AGENT_LOG.md`，面向课程提交和评审阅读。
- 可运行材料：`src/guarded_harness`、`tests`、`demo`、`Dockerfile`、
  `.github/workflows/ci.yml`，面向安装、运行和自动验证。
- 归档材料：`docs/course` 保存课程原始要求，`docs/archive/superpowers` 保存 specs、
  plans、SDD reports 和 handoff，避免根目录过载但保留过程证据。
