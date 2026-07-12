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
5. 最后补充 Docker、GitLab CI 和交付文档，使应用工厂具有一致的构建与运行入口。

## 测试与评审过程

实现阶段按任务使用 brainstorming、writing-plans、worktree、TDD、代码评审与最终验证
流程。单元测试覆盖模型、存储、策略和 dispatcher；集成测试覆盖 agent loop、失败反馈、
HITL、CLI 与 WebUI。交付前执行受当前环境支持的 pytest 子集、`compileall` 与 diff
检查；完整 pytest 与 Docker build 的结果在 `AGENT_LOG.md` 中保留。

## 冷启动验证

预留给独立 agent 仅依据 `SPEC.md` 和 `PLAN.md` 重做 1--2 个任务的记录：

| 日期 | 范围 | 结果 | 发现与后续动作 |
| --- | --- | --- | --- |
| 待执行 | 待选 Task 1--2 | 待记录 | 待记录 |

## 后期需求变更：Live Provider 与 WebUI

在本地接入 NJU SE Hub 后，发现真实模型默认返回自然语言，而 harness 主循环只接受 action JSON。这暴露的是 provider 适配层问题，而不是治理机制问题。处理策略是在 `OpenAICompatibleProvider` 中加入明确的 action JSON 输出协议，并清洗常见的 fenced JSON 响应；同时把 WebUI 从固定 MockLLM 扩展为 Mock/Live 双模式，允许用户输入 OpenAI-compatible base URL、model 和 API key。

该变更符合项目要求：API key 仍通过隐藏输入和 OS keyring 管理，不写入源码、审计事件或 session；真实 LLM 调用仍只是单次 provider 能力，agent loop、guardrail、HITL 状态机、反馈分类和工具分发仍由项目代码实现，并继续通过 mock/stub LLM 的确定性测试验证。

## 后期 UI 修复：中文展示与 OpenCode 风格

WebUI 原先直接使用 Jinja `tojson` 展示 trace payload，导致中文在页面源码中显示为 `\uXXXX`。修复方式是在模板层使用 `ensure_ascii=False` 的 JSON filter，让用户看到可读中文；这不改变数据库写入和审计模型。页面视觉同时按 `DESIGN-opencode.ai.md` 收敛到 monospaced terminal 风格，包括 cream 背景、深色终端面板、ASCII bracket 标签、hairline 边框和 4px 控件。该修复服务于演示与可用性，不影响核心 harness 判断逻辑。
