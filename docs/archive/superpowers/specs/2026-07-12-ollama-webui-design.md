# Ollama 风格 Chat Workspace WebUI 设计

## 背景

当前 WebUI 已经拆分为 Dashboard、Provider Settings、Session Trace、Approvals Queue 和 Guardrail Demo，功能结构满足演示需要，但首页仍像后台表单：用户输入任务后跳转到 Session 页面，首页不展示持续对话，也没有把已经持久化的 session/audit 内容转化为可读的交互历史。

用户要求参考 `DESIGN-ollama.md` 改成 Ollama 官网式的极简文档风格，同时希望首页模仿 Codex 的聊天框体验：输入任务后仍留在同一工作台，页面保存并展示自己与 AI/harness 的交互内容。Guardrail Demo 不再作为主导航入口。

本次改造只调整前端页面结构、文案层级、样式和首页展示流，不改变 agent loop、provider、guardrail、HITL 状态机、凭据存储或审计数据模型。

## 目标

1. 采用 Ollama 风格的白底、黑白灰、文档式窄栏布局。
2. 所有主要交互控件使用 pill 形态：按钮、输入框、模式选择、任务入口。
3. 首页从 Dashboard 改为 Chat Workspace，展示最近 session 形成的对话历史。
4. 点击 Start task 后返回首页并追加新的 conversation item，而不是主动跳转到 Session Trace。
5. 保留 Session Trace 详情页作为审计入口，但不把它作为主交互路径。
6. 从主导航和首页卡片中隐藏 Guardrail Demo；后端路由可保留，便于作业评审或测试直接访问。
7. Session trace 和首页历史中的中文任务、中文 JSON payload 继续以可读中文显示，不恢复为 `\uXXXX`。
8. API key 仍只通过密码框提交并存入 OS keyring，不写入页面、session 或配置文件。

## 非目标

- 不新增真正的多轮 agent memory 或连续上下文能力。
- 不修改 live provider 的请求协议。
- 不引入前端构建工具、JavaScript 框架或 WebSocket。
- 不新增外部字体或远程资源依赖。
- 不为了像 Ollama 官网而加入无关 mascot、营销页或下载页。
- 不删除 Guardrail Demo 后端能力，只从主 UI 隐藏。

## 推荐方案

采用完整 Ollama 化 + Chat Workspace 方案：

- Dashboard 改名为 Chat Workspace，作为唯一主要入口。
- 首页顶部保留简洁 nav：`Guarded Harness`、`Provider Settings`、`Approvals`。
- 首页展示当前 provider 状态 chips：mode、model、key status。
- 首页中部展示 conversation timeline：每个 session 显示用户任务、harness/AI 结果摘要、状态、步数和可选 trace 链接。
- 首页底部是 Codex 式输入区：大输入框 + 黑色 pill 提交按钮。
- Provider Settings、Session Trace、Approvals 继续独立存在并套用 Ollama 风格。
- Guardrail Demo 保留路由和测试，但不在首页或导航中展示。

该方案比单纯换皮更符合真实使用方式：用户打开首页就能配置后开始任务、看到历史、继续提交，而不是在多个页面之间反复跳转。

## 数据与交互流

### 首页读取

首页加载时读取最近 sessions，并为每个 session 组装一个 conversation item：

- `task`：用户输入内容。
- `status`：session 当前状态。
- `step_count`：执行步数。
- `events`：最近审计事件。
- `summary`：优先取 `finished.message`、`max_steps`、`approval_requested`、`guardrail_denied`、`parser_error` 等关键事件摘要。
- `trace_url`：指向 `/sessions/{session_id}` 的审计详情链接。

### 任务提交

首页表单仍提交到 `/sessions`，但成功后重定向到 `/`，而不是 `/sessions/{session_id}`。这样用户看到的是同一个 Chat Workspace 中新增的对话记录。

### 审计详情

Session Trace 详情页保留，用于查看完整事件和 payload。首页只展示摘要，不把 JSON trace 全量堆在主工作台。

## 视觉规范

- 页面背景：`#ffffff`。
- 主文字：`#000000`。
- 正文弱化：`#737373`。
- 次级文字：`#a3a3a3`。
- 软背景：`#fafafa`。
- 边框：`#e5e5e5`。
- 深色强调：`#171717`，仅用于主按钮或 terminal header。
- 主容器：默认最大宽度约 760px；Approvals 可扩展到约 1040px。
- 标题：36px 左右、500 权重、系统圆润字体优先。
- 正文：16px 系统 sans。
- 代码：14px 或 16px `ui-monospace`。
- 按钮和输入框：`border-radius: 9999px`。
- 卡片：12px 圆角、1px hairline，无阴影、无渐变。

## 页面设计

### Chat Workspace

首页是主要交互页，第一屏包括：

- 顶部简洁 nav：`Guarded Harness`、`Provider Settings`、`Approvals`。
- 居中标题：`Guarded Harness`。
- 一句说明：强调 governance guardrails、HITL state machine 和 OpenAI-compatible provider。
- 当前 provider 状态以小型 pill/meta chips 显示。
- conversation timeline 展示最近交互：
  - user bubble：任务文本。
  - harness bubble：结果摘要、状态、步数。
  - trace 链接作为小号文本链接，不作为醒目的主按钮。
- 页面底部任务输入区模仿 Codex 聊天框：大圆角输入框、黑色 pill 提交按钮。

不再展示旧的 Provider 卡片、Recent Sessions 空卡片、`Change configuration` 按钮或 Guardrail Demo 跳转按钮。

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

Guardrail Demo 作为隐藏演示页保留：

- 不在主导航和首页出现。
- 直接访问 `/guardrail` 仍可看到 demo。
- 相关测试继续覆盖，保证作业评审需要时可以使用。

## 测试策略

更新 Web 集成测试，覆盖：

1. 首页包含 Chat Workspace 结构、provider status chips 和任务输入区。
2. 首页不再包含 Guardrail Demo 主导航链接、Provider 卡片按钮或 `Change configuration` 首页按钮。
3. 提交任务后响应回到首页，并能看到新的 conversation item。
4. 首页 conversation item 显示用户任务、状态、步数、结果摘要和 trace 链接。
5. Provider Settings 保存流程仍可用，API key 不回显。
6. Session Trace 仍显示中文任务和中文 JSON payload。
7. Approvals 页面保留队列和审批/拒绝动作入口。
8. Guardrail Demo 直接访问和提交后仍显示确定性结果。

完成实现后运行：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

## 风险与约束

- 首页展示的是 session 历史摘要，不代表新增了真正多轮上下文。
- 由于不引入外部字体，Windows 上无法完全复刻 SF Pro Rounded；使用 `ui-rounded`、`system-ui`、Segoe UI fallback。
- 项目没有前端构建链，本次改造继续使用 Jinja + CSS，避免增加交付复杂度。
- Guardrail Demo 从主 UI 隐藏后，演示时需要直接输入 `/guardrail` 才能打开。

## Spec 自检

- 无 TBD/TODO。
- 已纳入用户新增要求：去掉 Guardrail Demo 主入口、去掉首页配置跳转按钮、首页展示保存的交互内容、提交后留在首页。
- 目标与非目标边界明确。
- 页面改造不改变后端 provider 协议或密钥策略。
- 测试策略覆盖 UI 关键结构和既有功能回归。
