# Guarded Harness

Guarded Harness 是一个本地 coding-agent harness。它不让 LLM 直接控制文件系统或
shell，而是要求模型返回结构化 action，再由项目代码完成解析、策略判定、审批、执行和审计。

项目支持两种运行方式：

- **Mock 模式**：完全离线、确定性输出，适合测试和演示。
- **Live 模式**：显式开启，支持 OpenAI-compatible provider，例如 NJU SE Hub。
- **CI 验证**：GitHub Actions 在 Python 3.11/3.12 上运行测试和编译检查。

## 项目亮点

- **治理优先**：项目的核心不是聊天界面，而是把 LLM 输出变成受控 action 的 harness。
- **确定性 guardrail**：危险动作由代码规则拒绝或进入审批，不依赖提示词让模型自觉遵守。
- **HITL 状态机**：审批请求持久化到 SQLite，支持批准一次、拒绝当前动作和停止任务。
- **反馈回灌**：解析错误、策略拒绝、命令失败和审批拒绝都会转化为 observation，进入下一轮决策。
- **离线可验收**：MockLLM 覆盖主要机制，测试和演示不需要真实 API key。
- **凭据隔离**：live provider key 不进入源码、审计、SQLite、日志或页面输出。
- **轻量交付**：CLI、FastAPI WebUI、Dockerfile 和 GitHub Actions 共用同一套核心代码。

## 核心机制

- LLM 只能提出结构化 action。
- 文件和 shell 操作都受 workspace root 约束。
- Guardrail 返回 `allow`、`deny`、`needs_approval` 三类决策。
- 需要人工确认的动作会写入 SQLite，并暂停 session。
- 审计日志记录 action、策略决策、工具结果和审批结果。
- WebUI 提供 Chat、Provider Settings、Session Trace 和 Approvals。
- Docker 场景支持通过环境变量或进程内临时 key 使用 live provider。
- GitHub Actions 配置位于 `.github/workflows/ci.yml`，与本地验证命令保持一致。

## 一分钟演示路线

评审时推荐先走确定性路线，再展示可选 live provider：

1. 运行 `harness demo guardrail`，展示危险命令被 policy 拒绝。
2. 运行 `harness demo feedback`，展示命令失败如何变成下一轮 observation。
3. 运行 `harness demo hitl --wait-only`，再用 `harness approvals list` 和
   `harness approvals approve <id>` 展示审批暂停与恢复。
4. 启动 WebUI，打开 Chat Workspace，提交一个 mock 任务并查看 Session Trace。
5. 打开 Approvals Queue，展示 `Approve once`、`Deny action`、`Stop task` 的语义差异。
6. 打开 Guardrail Demo，展示无需真实 LLM 也能验证核心安全机制。

## 快速开始

需要 Python 3.11 或更高版本。

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

如果系统默认 `python` 不是 Python 3.11+，请直接指定 Python 3.11 路径创建虚拟环境。本机可用路径是：

```powershell
& C:\Users\37592\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python --version
```

本机激活后应显示：

```text
Python 3.11.9
```

## 验证

```powershell
python -m pytest -q
python -m compileall -q src tests
```

最近一次本地验证结果：

```text
266 passed, 2 skipped
compileall src tests: passed
```

仓库还包含 GitHub Actions workflow：

```text
.github/workflows/ci.yml
```

该 workflow 在 `main`、`dev` 和 `feature/**` 分支 push 或 pull request 时触发，并在
Python 3.11 与 3.12 上执行安装、`pytest -q` 和 `compileall src tests`。

## 本地 CLI

在希望作为 workspace 的目录中运行命令。状态库默认写入该目录的
`.guarded-harness/state.sqlite3`。

```powershell
harness run "summarize the repository"
harness run
harness config init
harness approvals list
harness credentials status
```

常用命令：

- `harness run "<task>"`：运行一次任务。
- `harness run`：进入交互模式；每条普通输入会创建一个新的 session。
- `harness config init`：为当前 workspace 生成 provider 配置文件。
- `harness demo guardrail`：演示危险动作被拒绝。
- `harness demo feedback`：演示失败反馈进入下一轮。
- `harness demo hitl`：演示人工审批暂停和恢复。
- `harness approvals list`：查看待审批动作。
- `harness approvals approve <id>`：批准一次待审批动作。
- `harness approvals deny <id>`：拒绝一次待审批动作。
- `harness credentials status`：查看 key 是否已配置，不显示 key。
- `harness serve`：启动本地 WebUI。

交互模式支持 `:help`、`:mode`、`:approvals`、`:exit` 和 `:quit`。当前实现中，交互模式
复用同一 workspace、配置文件和状态库，但每条普通输入都是一个新的 harness session。

## Provider 配置

Live provider 是显式 opt-in。刚 clone 仓库后，推荐先让 CLI 自动生成本地配置文件：

```powershell
harness config init
```

该命令会创建：

```text
.guarded-harness/provider.json
```

默认内容与 `config/provider.example.json` 一致：

```json
{
  "mode": "live",
  "base_url": "https://njusehub.info/v1",
  "model": "deepseek-v4-flash",
  "timeout": 30
}
```

如果文件已经存在，`harness config init` 不会覆盖；确实需要重置时可以运行：

```powershell
harness config init --force
```

然后把 API key 存到 OS keyring：

```powershell
harness credentials set
```

`.guarded-harness/provider.json` 不会也不应该保存 API key。配置加载优先级为：

```text
命令行显式选项 > 环境变量 > .guarded-harness/provider.json > 内置默认值
```

如果配置文件里的 `mode` 是 `live`，CLI 会自动使用 live provider：

```powershell
harness run "inspect the tests"
```

也可以不用配置文件，直接使用环境变量覆盖某次运行：

```powershell
$env:GUARDED_HARNESS_MODE="live"
$env:GUARDED_HARNESS_BASE_URL="https://njusehub.info/v1"
$env:GUARDED_HARNESS_MODEL="deepseek-v4-flash"
$env:GUARDED_HARNESS_API_KEY="YOUR_API_KEY"
```

## Mock 演示

以下演示不调用网络或真实 LLM：

```powershell
harness demo guardrail
harness demo feedback
harness demo hitl
```

- `guardrail`：演示危险 shell 命令被策略拒绝。
- `feedback`：演示命令失败反馈进入下一轮上下文。
- `hitl`：演示人工审批暂停和恢复。

保留一个待审批记录用于手动检查：

```powershell
harness demo hitl --wait-only
harness approvals list
harness approvals approve <id>
```

## WebUI

启动本地 WebUI：

```powershell
uvicorn guarded_harness.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

WebUI 包含：

- Chat Workspace
- Provider Settings
- Session Trace
- Approvals Queue
- Guardrail Demo

审批卡片提供三个动作：`Approve once` 执行本次动作，`Deny action` 拒绝当前动作并把反馈交给 live provider 尝试替代路线，`Stop task` 拒绝并结束本轮任务。

默认 live provider 配置：

```text
GUARDED_HARNESS_BASE_URL = https://njusehub.info/v1
GUARDED_HARNESS_MODEL = deepseek-v4-flash
```

## Docker

构建并运行 mock/default WebUI：

```powershell
docker build -t guarded-harness .
docker run --rm -p 8000:8000 guarded-harness
```

打开：

```text
http://127.0.0.1:8000
```

Uvicorn 日志里显示的 `http://0.0.0.0:8000` 是容器内部监听地址，不是浏览器访问地址。
在本机浏览器中请使用 `http://127.0.0.1:8000` 或 `http://localhost:8000`。

使用环境变量运行 live mode：

```powershell
docker run --rm -p 8000:8000 `
  -e GUARDED_HARNESS_BASE_URL=https://njusehub.info/v1 `
  -e GUARDED_HARNESS_MODEL=deepseek-v4-flash `
  -e GUARDED_HARNESS_API_KEY=YOUR_API_KEY `
  guarded-harness
```

Docker 容器通常没有可用的桌面 OS keyring。容器中推荐使用环境变量注入 API key，或在
Provider Settings 输入 key 但不勾选保存。未保存的 key 只存在于当前 FastAPI 进程内，容器重启后失效。

## 凭据与安全边界

- API key 不应进入仓库、日志、审计事件、CLI 输出或 HTML。
- `harness credentials set` 使用 OS keyring 保存 API key。
- `GUARDED_HARNESS_API_KEY` 可用于 Docker/live provider。
- `.guarded-harness/provider.json` 只保存非敏感 provider 配置，不保存 API key。
- WebUI 临时输入且未保存的 key 只保存在当前进程内存中。
- 新建审批 action 入库前会执行 secret 检测；包含 API key、Bearer token、password 等敏感内容的 action 会被拒绝创建。
- 历史遗留 secret 数据在 CLI/Web 展示时会脱敏。
- `.env` 已被 git 忽略，但它仍是明文文件，不应提交或共享。
- 所有文件 action 都受 workspace root 约束。
- shell action 会解析为 argv，并以 `shell=False` 执行。
- 管道、重定向、命令替换、逻辑连接等 shell control syntax 会被拒绝。
- 删除等敏感动作会被拒绝或进入人工审批，取决于风险等级。

## 课程提交清单

- 源码：`src/guarded_harness`。
- 测试：`tests/unit` 和 `tests/integration`。
- 本地运行说明：本 README 的快速开始、CLI、WebUI 和 Docker 章节。
- 设计文档：`SPEC.md`。
- 过程文档：`SPEC_PROCESS.md`、`PLAN.md`、`AGENT_LOG.md`。
- 反思文档：`REFLECTION.md`。
- 演示说明：`demo/README.md`。
- CI：`.github/workflows/ci.yml`。
- 历史过程材料：`docs/archive/superpowers`。
- 课程原始要求：`docs/course`。

## 项目结构

```text
src/guarded_harness/
  core/          action、session、observation、agent loop
  governance/    guardrail、approval、audit、redaction
  tools/         filesystem、shell、test runner、dispatcher
  memory/        SQLite store 和 memory entries
  llm/           MockLLM 与 OpenAI-compatible provider
  config/        provider config 与 credential store
  web/           FastAPI app、Jinja templates、static assets
tests/           unit 和 integration tests
demo/            CLI demo 说明
docs/course/     课程原始要求
docs/archive/    历史设计、计划、报告和交接文档
.github/workflows/ci.yml  GitHub Actions 测试工作流
```

## 主要交付文档

- [SPEC.md](SPEC.md)：最终设计规约。
- [PLAN.md](PLAN.md)：实现计划和任务历史。
- [SPEC_PROCESS.md](SPEC_PROCESS.md)：过程记录和设计 rationale。
- [REFLECTION.md](REFLECTION.md)：项目反思。
- [AGENT_LOG.md](AGENT_LOG.md)：详细 agent 工作日志。
- [demo/README.md](demo/README.md)：确定性 CLI 演示说明。

归档文档：

- [docs/course](docs/course)：课程通用要求和项目 A 原始说明。
- [docs/archive](docs/archive)：历史 UI 设计、Superpowers specs/plans、SDD reports 和会话交接文档。

## 已知限制

- Live provider 行为取决于外部 provider 是否返回合法 action JSON。
- CLI 跨进程审批恢复只执行已审批动作或记录拒绝反馈并结束本轮恢复，不会静默重建之前的 live provider 对话。
- Web live session 可以在同一 FastAPI 进程内复用已保存或临时输入的 key 继续审批后的 provider loop。
- SQLite 状态文件是本地状态库，不是加密 secrets vault。
- Docker 的 `0.0.0.0:8000` 是 bind address，浏览器应访问 `http://127.0.0.1:8000`。
- 当前仓库未包含部署配置；课程提交时可先提交源码、文档、Dockerfile 和 GitHub Actions 验证结果。

## 第三方许可证摘要

运行时依赖包括 FastAPI、Uvicorn、Typer、Jinja2、python-multipart、keyring 和 httpx。
开发依赖包括 pytest。发布或再分发前，应以锁定版本对应的上游许可证文本和 SBOM 为准。
