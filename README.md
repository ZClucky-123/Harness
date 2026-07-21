# Guarded Harness

Guarded Harness 是一个本地 coding-agent harness。它不让 LLM 直接操作文件系统或 shell，而是要求模型返回结构化 action，再由项目代码完成解析、策略判断、人工审批、执行和审计。

项目支持两种模式：

- `mock`：离线确定性模式，适合演示和测试，不需要 API key。
- `live`：调用 OpenAI-compatible provider，例如 NJU SE Hub。

线上 WebUI：

```text
http://39.107.87.32/
```

GitHub Release：

```text
https://github.com/ZClucky-123/Harness/releases/tag/v0.1.0
```

## 安装

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## 启动 WebUI

本地启动：

```powershell
harness serve
```

浏览器打开：

```text
http://127.0.0.1:8000
```

WebUI 主要页面：

- `Chat`：提交任务并查看结果。
- `Provider Settings`：选择 mock/live，配置 base URL、model，并填写 API key。
- `Approvals`：处理需要人工确认的操作。
- `Guardrail Demo`：直接访问 `/guardrail`，演示危险操作拦截。

## WebUI 使用

默认可以直接使用 `mock` 模式测试流程。

如果要使用 `live` 模式：

1. 打开 `Provider Settings`。
2. 选择 `Live OpenAI-compatible API`。
3. 填写 `Base URL`、`Model` 和 `API key`。
4. 点击 `Save provider`。
5. 回到 `Chat` 提交任务。

默认 live provider 配置：

```text
Base URL: https://njusehub.info/v1
Model: deepseek-v4-flash
```

WebUI 中填写的 API key 只保存在当前浏览器 sessionStorage 中。服务器不会把它写入配置文件、SQLite、审计日志、HTML 或全局内存，因此其他访问者不能复用你的 key。

如果没有填写 API key 就使用 live mode，页面会提示先到 `Provider Settings` 填写 key。

## CLI 使用

常用命令：

```powershell
harness run "summarize the repository"
harness run
harness demo guardrail
harness demo feedback
harness demo hitl
harness approvals list
harness approvals approve <id>
harness approvals deny <id>
harness credentials status
harness serve
```

说明：

- `harness run "<task>"`：运行一次任务。
- `harness run`：进入交互模式。
- `harness demo guardrail`：演示危险命令被策略拦截。
- `harness demo feedback`：演示失败反馈进入下一轮。
- `harness demo hitl`：演示人工审批暂停和恢复。
- `harness serve`：启动本地 WebUI。

## CLI Provider 配置

生成本地 provider 配置：

```powershell
harness config init
```

配置文件位于：

```text
.guarded-harness/provider.json
```

该文件只保存非敏感配置，不保存 API key。

如果 CLI 要使用 live mode，可以把 API key 存到 OS keyring：

```powershell
harness credentials set
```

也可以使用环境变量：

```powershell
$env:GUARDED_HARNESS_MODE="live"
$env:GUARDED_HARNESS_BASE_URL="https://njusehub.info/v1"
$env:GUARDED_HARNESS_MODEL="deepseek-v4-flash"
$env:GUARDED_HARNESS_API_KEY="YOUR_API_KEY"
```

## Docker

构建并启动：

```powershell
docker build -t guarded-harness .
docker run --rm -p 8000:8000 guarded-harness
```

打开：

```text
http://127.0.0.1:8000
```

## 测试

```powershell
python -m pytest -q
python -m compileall -q src tests
```

最近一次本地验证：

```text
271 passed, 2 skipped, 1 warning
compileall passed
```

## 安全说明

- API key 不应提交到仓库。
- `.guarded-harness/provider.json` 不保存 API key。
- WebUI 的 API key 只保存在当前浏览器 sessionStorage。
- CLI 可以使用 OS keyring 或 `GUARDED_HARNESS_API_KEY`。
- action 入库前会检查常见 secret，包含 API key、Bearer token、password 等内容的 action 会被拒绝。

## 项目结构

```text
src/guarded_harness/
  core/        agent loop、action、observation
  governance/  guardrail、approval、audit、redaction
  tools/       filesystem、shell、test runner
  memory/      SQLite store
  llm/         MockLLM 和 OpenAI-compatible provider
  config/      provider config 和 credential store
  web/         FastAPI WebUI
tests/         unit 和 integration tests
```
