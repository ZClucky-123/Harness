# Ollama 风格 WebUI 改造设计

## 背景

当前 WebUI 已经拆分为 Dashboard、Provider Settings、Session Trace、Approvals Queue 和 Guardrail Demo，功能结构满足演示需要，但视觉仍保留 OpenCode 式终端风格。用户要求参考 `DESIGN-ollama.md`，将前端改为 Ollama 官网式的极简文档风格。

本次改造只调整前端页面结构、文案层级和样式，不改变 agent loop、provider、guardrail、HITL 状态机、凭据存储或审计数据模型。

## 目标

1. 采用 Ollama 风格的白底、黑白灰、文档式窄栏布局。
2. 所有主要交互控件使用 pill 形态：按钮、输入框、模式选择、任务入口。
3. 保留作业演示所需的五个页面：Dashboard、Provider Settings、Session Trace、Approvals、Guardrail Demo。
4. Session trace 使用轻量 terminal card 呈现，保留 macOS traffic-light dots 和 monospace JSON。
5. 中文 trace 和任务文本继续以可读中文显示，不恢复为 `\uXXXX`。
6. API key 仍只通过密码框提交并存入 OS keyring，不写入页面、session 或配置文件。

## 非目标

- 不新增真正的聊天多轮 UI。
- 不修改 live provider 的请求协议。
- 不引入前端构建工具或 JavaScript 框架。
- 不新增外部字体或远程资源依赖。
- 不为了像 Ollama 官网而加入无关 mascot、营销页或下载页。

## 推荐方案

采用完整 Ollama 化方案，保持现有页面分工不变：

- Dashboard 变成 README/CLI 风格入口，居中标题、短说明、install-snippet 式任务启动区域。
- Provider Settings 变成简洁配置页，突出当前 mode、base URL、model、key 状态。
- Session Trace 变成白底 terminal card，弱化大面积深色背景，只在代码和事件块里使用轻量边框。
- Approvals 变成三列队列视图，pending、executing、failed 仍然可扫读。
- Guardrail Demo 变成文档式示例区，展示规则、输入、判定结果和观察输出。

该方案比“只改首页和设置页”更统一，也比“重做成长营销单页”更适合作业评审，因为状态机、审批队列和 guardrail demo 仍是第一屏之后的核心内容。

## 视觉规范

- 页面背景：`#ffffff`。
- 主文字：`#000000`。
- 正文弱化：`#737373`。
- 次级文字：`#a3a3a3`。
- 软背景：`#fafafa`。
- 边框：`#e5e5e5`。
- 深色强调：`#171717`，仅用于少量 CTA 或 terminal header。
- 主容器：默认最大宽度约 760px；Approvals 可扩展到约 1040px。
- 标题：36px 左右、500 权重、系统圆润字体优先。
- 正文：16px 系统 sans。
- 代码：14px 或 16px `ui-monospace`。
- 按钮和输入框：`border-radius: 9999px`。
- 卡片：12px 圆角、1px hairline，无阴影、无渐变。

## 页面设计

### Dashboard

Dashboard 是主要入口，第一屏包括：

- 顶部简洁 nav：Guarded Harness、Settings、Approvals、Guardrail Demo。
- 居中标题：`Guarded Harness`。
- 一句说明：强调 governance guardrails、HITL state machine 和 OpenAI-compatible provider。
- 类似 Ollama install snippet 的任务启动区域，textarea 保留多行输入，但视觉上是 soft card/pill 混合。
- 当前 provider 状态以小型 pill/meta chips 显示。

### Provider Settings

Provider Settings 保留表单能力，但减少终端感：

- mode 选择显示为两个 pill/radio option。
- base URL、model、API key 使用 pill input。
- API key 状态只显示 `configured` 或 `missing`。
- 提交按钮为黑色 pill。
- 不在页面回显密钥。

### Session Trace

Session 页面用于证明 harness 可观测性：

- 顶部显示任务、状态、步数。
- 事件列表使用 terminal card，每个事件有序号、event type 和 JSON payload。
- JSON payload 使用 `pretty_json` filter，保持中文可读。
- 没有大面积深色背景，避免遮蔽内容。

### Approvals

Approvals 页面展示 HITL 状态机：

- 三列队列：Pending、Executing、Failed。
- 每个 approval 是 hairline card。
- Approve / Deny 按钮保持清晰，Deny 可使用边框式危险按钮，但不引入大面积红色主题。
- 空状态用弱化正文提示。

### Guardrail Demo

Guardrail Demo 用作评审演示入口：

- 页面说明该 demo 不依赖真实 LLM。
- 输入区和结果区保持文档式。
- 结果展示策略判定、原因和观察 payload。

## 测试策略

更新 Web 集成测试，覆盖：

1. Dashboard 包含 Ollama 风格关键结构，例如 `install-snippet`、provider status 和任务表单。
2. Provider Settings 保存流程仍可用，API key 不回显。
3. Session Trace 仍显示中文任务和中文 JSON payload。
4. Approvals 页面保留队列和审批/拒绝动作入口。
5. Guardrail Demo 提交后仍显示确定性结果。

完成实现后运行：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## 风险与约束

- 由于不引入外部字体，Windows 上无法完全复刻 SF Pro Rounded；使用 `ui-rounded`、`system-ui`、Segoe UI fallback。
- 项目没有前端构建链，本次改造继续使用 Jinja + CSS，避免增加交付复杂度。
- Ollama 官网有 mascot 元素，但本项目的作业重点是治理和状态机，因此不加入无关插画。

## Spec 自检

- 无 TBD/TODO。
- 目标与非目标边界明确。
- 所有页面改造均不改变后端协议或密钥策略。
- 测试策略覆盖 UI 关键结构和既有功能回归。
