# Guarded Harness

Guarded Harness 是一个本地 coding-agent harness。它把 LLM 的结构化 action
置于确定性的 workspace 边界、guardrail 策略、审计记录和人工审批（HITL）之后。
核心机制可使用离线 `MockLLM` 验证，不依赖网络或真实模型。

## 安装

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

运行全部测试：

```powershell
pytest
python -m compileall -q src
```

## 本地 CLI

在要作为 workspace 的目录中运行命令；状态库默认写入该目录的
`.guarded-harness/state.sqlite3`。

```powershell
harness run "summarize the repository"          # 默认 mock mode
harness approvals list
harness credentials status
```

真实 provider 是显式 opt-in：先存储凭据，再使用 `--live`。

```powershell
harness credentials set
harness run "inspect the tests" --live
```

## WebUI

以应用工厂启动最小 WebUI：

```powershell
uvicorn guarded_harness.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`，可创建 mock session、查看审计轨迹并处理待审批项。

## Mock 演示

以下演示不调用网络或真实 LLM：

```powershell
harness demo guardrail
harness demo feedback
harness demo hitl
```

`guardrail` 演示危险命令被拒绝；`feedback` 演示命令失败反馈给下一轮；`hitl`
演示审批暂停与恢复。使用 `harness demo hitl --wait-only` 可保留审批记录，再以
`harness approvals approve <id>` 或 `harness approvals deny <id>` 处理。

## Docker

Docker 是推荐的 WebUI 分发方式：

```powershell
docker build -t guarded-harness .
docker run --rm -p 8000:8000 guarded-harness
```

容器启动后访问 `http://localhost:8000`。如需保留 session 数据，可额外挂载一个
workspace 卷；请只挂载你允许 harness 访问的目录。

## 凭据与安全边界

- `harness credentials set` 使用操作系统 keyring 保存 API key；状态命令只输出是否已配置。
- live mode 读取 `GUARDED_HARNESS_BASE_URL`、`GUARDED_HARNESS_MODEL` 与
  `GUARDED_HARNESS_TIMEOUT` 环境变量。API key 不应写入仓库、日志、审计记录、CLI
  输出或 Web 页面。
- `.env` 是明文文件，只应作为本地开发 fallback；它已被 `.gitignore` 忽略，但仍可能被
  备份、终端历史或误挂载卷泄露。不要提交、共享或在不受信任目录中创建它。
- 所有文件 action 都受 workspace root 约束。破坏性系统命令和 workspace 外写入被拒绝；
  `git push`、依赖安装、删除 workspace 内文件以及修改 `.env` 需要人工审批。
- Guardrail 是确定性防护层，不是完整沙箱。运行 live mode 或批准操作前，仍需审查任务、
  workspace 和命令影响。

## 目录结构

```text
src/guarded_harness/
  core/          # action、session、agent loop
  governance/    # guardrail、审批、审计
  tools/         # 文件、shell、测试分发
  memory/        # SQLite 状态和 memory
  llm/           # Mock 与 OpenAI-compatible provider
  config/        # 配置和 keyring 凭据
  web/           # FastAPI 工厂、模板、静态资源
tests/           # unit 与 integration 测试
demo/            # 离线机制演示说明
```

## 已知限制

- WebUI 目前只运行确定性的 mock session；真实 LLM 调用通过 CLI `run --live` 提供。
- `harness serve` 命令尚未连接到 WebUI 启动器，请使用上面的 `uvicorn` 命令。
- Guardrail 使用显式规则，尚未提供可配置策略、完整 OS sandbox 或多用户鉴权。
- keyring 的可用性取决于本机操作系统与后端配置。

## 第三方许可证摘要

本项目运行时依赖 FastAPI、Uvicorn、Typer、Jinja2、python-multipart、keyring 和
httpx；开发依赖 pytest。这些依赖分别遵循其上游许可证（主要为 MIT 或 BSD-3-Clause）。
Docker 基础镜像 `python:3.11-slim` 及其包含的软件遵循各自上游条款。发布或再分发前，
请以锁定版本的官方许可证文本和 SBOM 为准。

## 审批恢复与本地数据风险

- CLI/Web 的跨进程审批处理只执行已审批动作，然后结束本次恢复轮次；它不会静默创建
  `MockLLM` 来冒充原 live provider，也不会继续原 live 对话。若需继续 live 任务，应在审查结果后显式启动新的
  `harness run --live`。当前版本尚未持久化 live provider 的对话状态。
- 为了在审批后执行原动作，`.guarded-harness/state.sqlite3` 的 `approvals.action_json` 会保存原始 action。
  WebUI、CLI 列表和审计事件只使用统一的脱敏视图，不展示 API key、Bearer token 或 password；但 SQLite
  文件本身不是加密保险库。请将 workspace 及该文件限制为当前用户可读，不要同步、提交或共享状态库，敏感审批完成后按本地保留策略删除它。
- shell action 不再交给系统 shell。命令被解析为 argv 并以 `shell=False` 执行；命令替换、反引号、换行、
  重定向、管道和逻辑操作符会 fail-closed，且路径参数在执行前经过 workspace realpath 检查。

## CI/CD 与部署状态

仓库的 `.gitlab-ci.yml` 定义 `unit-test` 与 `docker-build` 两个 job：push 后应在 GitLab Runner 中安装依赖、
运行完整 pytest/compileall，并构建 Docker 镜像。当前环境没有 GitLab Runner、registry 或云部署权限，
因此这次修改**未能在本地验证 CI/CD pass，也没有可如实提供的线上 WebUI URL**。提交到课程 GitLab 后仍需确认最后一次 pipeline 为 pass，
并由仓库所有者完成镜像发布和公网部署后在此处补入真实 URL。

本地可验证入口为 `harness serve` 或：

```powershell
uvicorn guarded_harness.web.app:create_app --factory --host 127.0.0.1 --port 8000
```

本地地址为 `http://127.0.0.1:8000`，它不是线上部署 URL。
