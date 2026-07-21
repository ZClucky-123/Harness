# Agent Log

## 顺序开发记录

本文记录 Guarded Harness 的主要工程阶段。整理后的记录按最终项目结构顺序呈现，保留
Superpowers 使用、人工决策和验证证据，省略与最终交付无关的临时环境噪音。

| 阶段 | 工作摘要 | 结果 |
| --- | --- | --- |
| 需求阅读 | 阅读课程要求、项目 A 说明、README 和历史 handoff，确认作业目标是 coding-agent harness，而不是通用聊天机器人。 | 明确核心交付：受控 action loop、HITL、反馈、审计、CLI/WebUI、Docker 与 CI。 |
| Brainstorming | 围绕 LLM 权限边界、危险动作、审批恢复、离线演示和 API key 安全做方案收敛。 | 决定让 LLM 只输出结构化 action，由 harness 代码执行治理。 |
| Writing Plans | 将实现拆成核心模型、SQLite、guardrail、dispatcher、agent loop、HITL、CLI、WebUI、分发文档。 | 形成 `PLAN.md` 的 Task 1--9 主线。 |
| Core Model | 建立 `Action`、`Observation`、`SessionState`、`SessionStatus` 等基础类型。 | action JSON 可解析、可校验、可测试。 |
| State Store | 增加 SQLite sessions、audit events、approvals 和 memory entries。 | session 状态、审批状态、审计轨迹和 memory 可持久化。 |
| Guardrail | 实现 workspace 边界、危险命令拒绝、敏感操作审批和策略结果。 | policy 返回 `allow`、`deny`、`needs_approval`。 |
| Dispatcher | 实现文件、shell、测试和 memory/finish 工具分发。 | shell 使用 argv + `shell=False`，拒绝 shell control syntax，常用伪命令有确定性处理。 |
| Agent Loop | 接入 MockLLM 和 OpenAI-compatible provider 抽象。 | parser、policy、tool、feedback 统一变成 observation，loop 可在 finish/approval/failure/max_steps 停止。 |
| HITL | 实现审批创建、暂停、批准、拒绝和恢复。 | `Approve once` 执行当前 action；`Deny action` 回灌 `approval_denied`；`Stop task` 结束恢复轮次。 |
| CLI | 增加 `harness run`、`demo`、`approvals`、`credentials` 和 `serve`。 | 离线 demo 可展示 guardrail、feedback、hitl；凭据命令不打印 API key。 |
| WebUI | 增加 Chat Workspace、Provider Settings、Session Trace、Approvals Queue 和 Guardrail Demo。 | 评审者可在浏览器中创建任务、查看轨迹、处理审批和演示确定性 guardrail。 |
| Live Provider | 接入 NJU SE Hub/OpenAI-compatible endpoint，要求模型输出 action JSON 并清洗 fenced JSON。 | live 模式显式 opt-in；核心治理仍由项目代码和 mock/stub 测试验证。 |
| Credential Safety | 增加 keyring、`GUARDED_HARNESS_API_KEY`、进程内临时 key 和统一 redaction。 | API key 不写入源码、`provider.json`、SQLite、audit、日志或 HTML；新审批 action 入库前检测 secret。 |
| UI Polish | 根据截图反馈统一 sidebar、composer、trace、settings、approvals 和 guardrail 页面。 | WebUI 从最小页面整理为一致的本地 agent console。 |
| Distribution | 增加 Dockerfile、GitHub Actions、README、SPEC_PROCESS 和反思文档。 | GitHub Actions 使用 Python 3.11/3.12 运行安装、`pytest -q` 和 `compileall src tests`。 |
| Unified Config + Interactive CLI | 统一 CLI/WebUI provider 配置文件，并让 `harness run` 无参数进入交互模式。 | CLI 可读取 `.guarded-harness/provider.json`；交互模式支持 `:mode`、`:approvals`、`:exit`。 |
| Final Review | 复核文档是否与代码一致，归档 Superpowers 过程文件。 | 根目录保留最终交付文档，历史过程文件位于 `docs/archive/superpowers/`。 |

## Superpowers 使用记录

- `superpowers:brainstorming`：用于澄清项目目标、WebUI 结构、审批语义和 UI 行为。
- `superpowers:writing-plans`：用于把规格拆成可执行、可验证的任务。
- `superpowers:using-git-worktrees`：用于确认工作区隔离，避免混入无关改动。
- `superpowers:test-driven-development`：用于核心机制、WebUI 回归、shell 加固和凭据处理。
- `superpowers:systematic-debugging`：用于定位 shell control syntax、审批恢复和 keyring 行为。
- `superpowers:verification-before-completion`：用于在声明完成前运行测试、编译和 diff 检查。

## TDD 轨迹摘要

| 主题 | 先写的失败场景 | 通过后的行为 |
| --- | --- | --- |
| Action parser | 非法 JSON、未知 action type、缺少字段 | parser 抛出确定性错误，loop 转成 observation。 |
| SQLite store | session/audit/approval/memory round trip | 本地状态可持久化，审批可跨命令查询。 |
| Guardrail | 危险命令、workspace 外写入、`git push` | 拒绝、允许和待审批路径可被单测区分。 |
| Dispatcher | shell 成功、shell 非零退出、文件读写 | 工具结果统一为 `Observation`。 |
| Agent loop | policy deny、tool failure、max steps | LLM 输出、策略、工具和反馈形成闭环。 |
| HITL | pending approval、approve、deny | 审批状态与 session 状态保持一致。 |
| WebUI | 页面加载、审批卡片、settings、trace | 浏览器页面可演示核心机制。 |
| Secret safety | 审批 action 含 key、页面展示 action | 新 secret action 被拒绝，历史数据展示脱敏。 |
| Shell hardening | command substitution、管道、重定向、symlink | executor 使用 `shell=False` 并 fail-closed。 |

### TDD 细节记录

**Action parser 与核心类型**

- 测试文件：`tests/unit/test_actions.py`。
- 先验证 `read_file` action 能被解析为 `ActionType.READ_FILE`，再验证未知 action 和非法
  JSON 会产生确定性错误。
- 该阶段的目标不是让模型“更会说话”，而是让后续所有模块都只接收结构化 action，
  避免工具层直接消费 LLM 原始文本。
- 产物：`Action`、`ActionType`、`parse_action()`、`Observation`、`FeedbackKind`、
  `SessionState` 和 `SessionStatus`。

**SQLite store、approval、audit 与 memory**

- 测试文件：`tests/unit/test_store.py`。
- 初始测试覆盖 session 创建、audit event 写入、approval 创建/resolve、memory round trip。
- 后续复审继续补充数据库路径 traversal、workspace root 限制、重复 resolve 拒绝、
  approval 原子创建与 session pause、执行状态 `executing/executed/failed`、手动标记失败等场景。
- secret 相关测试覆盖 task、approval action、approval reason、audit payload、memory
  content/tags 的敏感内容拒绝或展示脱敏。
- 产物：SQLite 状态库成为 agent loop 之外的事实来源，使暂停、恢复、审计和 memory
  不依赖单次进程内存。

**Guardrail policy**

- 测试文件：`tests/unit/test_guardrail.py`。
- 先写危险命令拒绝、`git push` 进入审批、workspace 外写入拒绝、workspace 内写入允许。
- 后续补充 `.env`、依赖安装、发布类动作、敏感路径访问、shell control syntax 等规则。
- 该阶段明确了三种 policy outcome：`allow`、`deny`、`needs_approval`。这三种结果是
  WebUI approval card、CLI approvals 和 audit events 的共同基础。
- 关键结论：policy 是执行前门禁，但不能替代 executor 层的边界校验。

**Tool dispatcher 与 shell executor**

- 测试文件：`tests/unit/test_dispatcher.py`。
- 初始测试证明文件 read/write、shell success、shell non-zero exit 都会返回统一
  `Observation`。
- shell 加固测试覆盖 command substitution、反引号、换行、管道、重定向、逻辑连接、
  workspace 外路径和 symlink realpath。
- Windows 演示体验补充 `ls`、`dir`、`pwd`、`cat`、`type`、`echo` 等伪命令处理；
  删除类伪命令 `rm/del/rd/rmdir` 进入审批或被 workspace 边界拒绝。
- 关键修正：执行层不再使用系统 shell 解释字符串，而是解析为 argv 并以 `shell=False`
  执行，从根源上减少 policy/executor 语义不一致。

**Agent loop 与 feedback**

- 测试文件：`tests/integration/test_loop_guardrail.py`、`tests/integration/test_loop_feedback.py`、
  `tests/integration/test_loop_failures.py`。
- 测试覆盖 policy deny 后继续 loop、命令失败后 feedback 进入下一轮、非法 JSON/未知 action
  不使程序崩溃、`max_steps` 能停止无限循环。
- `MockLLM` 保留收到的 contexts，使测试能断言 observation 确实进入下一轮 prompt context。
- 产物：agent loop 的每一步都可被观察，不再是“模型说什么就做什么”的黑盒。

**HITL approval**

- 测试文件：`tests/integration/test_hitl.py`。
- 初始测试覆盖 `git push` 暂停、pending approval 可查询、approve 执行 action、deny 产生
  `approval_denied`。
- 后续补充 approval 与 session 更新的事务边界，避免 action 已进入执行但 session 仍显示
  pending 或恢复后状态丢失。
- Web 语义最终拆成三种按钮：`Approve once`、`Deny action`、`Stop task`。其中
  `Deny action` 允许 live provider 根据拒绝反馈换路线，`Stop task` 明确结束本轮任务。

**CLI 与 WebUI**

- 测试文件：`tests/integration/test_cli.py`、`tests/integration/test_web.py`。
- CLI 测试覆盖 guardrail/feedback/hitl demo、approval list/approve/deny、credentials
  status 和 serve 入口。
- Web 测试覆盖首页、session trace、approvals queue、approval card、Provider Settings、
  Guardrail Demo、sidebar、composer、processing state、Back button refresh 等行为。
- UI 回归测试多次由截图反馈驱动，目的不是做复杂前端，而是让课程评审能快速看到机制证据。

**Live provider 与 credential safety**

- 测试文件：主要在 `tests/integration/test_web.py` 和 provider/config 相关测试中体现。
- live provider 测试使用 stub/mock，不依赖真实网络；验证 OpenAI-compatible response 能被
  清洗为 action JSON，非法响应转化为 observation。
- keyring 不可用、环境变量 key、Settings 临时 key 都有 Web 集成测试覆盖。
- 关键边界：API key 不写入 `provider.json`、SQLite、audit、日志或 HTML；未保存 key
  只存在于当前 FastAPI 进程内。

**Unified config 与 interactive CLI**

- 测试文件：`tests/unit/test_config_loader.py`、`tests/integration/test_cli.py`。
- 先写 provider 文件读取测试，确认 `.guarded-harness/provider.json` 中的 `mode`、
  `base_url`、`model`、`timeout` 会被 CLI 配置加载，同时 `api_key` 字段即使存在也不会读取。
- 再写环境变量覆盖测试，确认 `GUARDED_HARNESS_*` 优先级高于配置文件。
- CLI 集成测试验证：当 provider 文件设置 `mode=live` 时，`harness run "<task>"`
  可直接使用文件中的 base URL/model/timeout；`harness run` 无 task 时进入交互模式，
  支持普通任务、`:mode`、`:approvals` 和 `:exit`。

## 人工决策

- 项目贡献聚焦 harness 治理，而不是把安全性迁移到 prompt。
- Live provider 只能作为可选能力；MockLLM 必须能离线覆盖核心验收。
- 审批拒绝拆成 `Deny action` 与 `Stop task`，避免一个按钮同时表示“换路线”和“停止任务”。
- WebUI 不引入大型前端构建系统，采用 FastAPI + Jinja + CSS，降低运行和评审门槛。
- API key 只允许进入 keyring、环境变量或当前进程内存，不进入持久化业务数据。
- Docker 用于复现运行环境；GitHub Actions 用于当前仓库的自动测试。
- CLI/WebUI 共用 `.guarded-harness/provider.json` 作为非敏感配置文件；API key 继续通过
  keyring、环境变量或当前进程临时值提供。
- 交互式 CLI 只承诺“一行一个新 session”，不声称实现完整长对话 checkpoint。

## 阶段交付说明

Task 1--4 先建立底层可测试单元：action parser、SQLite store、guardrail 和 dispatcher。
这些任务保证系统即使没有 WebUI 和 live provider，也能独立证明“模型输出不会直接执行”。

Task 5--8 把底层机制连成用户可见流程：AgentLoop 负责多轮执行，HITL 负责暂停和恢复，
CLI 负责离线演示与命令行审批，WebUI 负责图形化查看 session、trace 和 approvals。

Task 9 之后的增强集中在真实使用体验：live provider action 协议、中文 trace 展示、
Chat Workspace 布局、三按钮审批语义、Docker 凭据处理和临时 API key。所有增强都遵守
同一原则：不绕过核心 guardrail，不泄露 secret，不让 UI 文案夸大系统能力。

### Task 1--4：受控执行基础

Task 1 先建立 action/observation/session 三个基础概念。这个阶段的核心判断是：
action 必须是 enum 支持的类型，payload 只能通过解析后的结构传给后续模块。这样后续
guardrail、dispatcher 和 loop 都不需要重新猜测模型原文含义。

Task 2 把 session、audit、approval 和 memory 放进 SQLite。选择 SQLite 是因为项目定位是
本地 harness，不需要服务端数据库；但审批暂停和恢复又不能只存在于内存中。这个阶段也为
后续 CLI approvals 命令和 Web Approvals Queue 提供共同数据源。

Task 3 实现 guardrail。规则先覆盖最明确的风险：破坏性系统命令、workspace 外路径、
敏感系统路径、发布/push、依赖安装和 `.env` 修改。这个阶段形成一个重要设计边界：
policy 只决定允许、拒绝或审批，不直接执行工具。

Task 4 实现工具分发。文件工具负责 workspace-bounded read/write；shell 工具负责 argv
执行和 stdout/stderr/returncode 采集；test runner 把测试命令也统一表示为 observation。
后续 shell 加固证明这个阶段的 executor 也必须独立 fail-closed，不能只信任 policy。

### Task 5--8：Agent Loop、HITL、CLI 和 WebUI

Task 5 把 MockLLM、OpenAI-compatible provider 抽象和 AgentLoop 接起来。loop 每轮都按
固定顺序执行：构造 context、调用 provider、解析 action、执行 policy、调用 dispatcher、
记录 audit、生成 observation。`max_steps` 是这个阶段的重要安全阀。

Task 6 实现 HITL 状态机。需要审批的 action 会被持久化为 approval request，并让 session
进入 `waiting_approval`。approve 会恢复执行；deny 会产生 `approval_denied` feedback。
后续三按钮语义是在这个基础上扩展出来的。

Task 7 实现 CLI。CLI 的价值是让核心机制可以在没有浏览器、没有真实 provider 的情况下演示：
`demo guardrail` 展示拒绝，`demo feedback` 展示失败回灌，`demo hitl` 展示审批暂停。
凭据命令只展示 configured/not configured，避免误打印 secret。

Task 8 实现 FastAPI WebUI。最小版本先提供任务输入、session trace 和 approvals 页面；
后续再扩展 Provider Settings、Guardrail Demo、Chat Workspace 布局和审批卡片即时状态。
这个阶段坚持服务端渲染，避免把课程重点转移到前端构建工具上。

### Task 9--14：交付、真实 provider 和演示体验

Task 9 完成 Dockerfile、GitHub Actions、README 和过程文档。Docker 默认启动 WebUI；
GitHub Actions 在 Python 3.11/3.12 上运行安装、测试和编译检查；README 作为评审入口。

Task 10--11 主要用于最终复审和安全补强：检查文档承诺是否超过代码能力，补充 shell
绕过、secret redaction、approval 状态和 memory 校验等边界。这里形成了“证据优先”的
交付口径：没有测试或代码支持的能力不写成已完成。

Task 12--13 根据截图反馈打磨 WebUI：固定 sidebar、统一 Chat Workspace、调整 composer、
让 session 列表和对话内容各自符合阅读顺序，并把 settings/trace/approvals/guardrail
页面统一到同一布局语言。UI 改动均配套 Web 集成测试，避免样式回归。

Task 14 处理 Docker/live provider 凭据体验。容器中通常没有可用 OS keyring，因此增加
`GUARDED_HARNESS_API_KEY` 和 Provider Settings 临时 key。这个 key 只在当前 FastAPI
进程内存中使用，不进入持久化配置、SQLite、audit、日志或 HTML。

Task 15 统一配置文件和 CLI 使用方式。`load_config()` 新增 workspace 配置文件读取，
CLI 的 live/mock 选择可以来自 `.guarded-harness/provider.json`，环境变量仍可覆盖文件。
`harness run` 的 task 参数改为可选：传入 task 时保持一次性执行，不传 task 时进入交互式
prompt。交互模式提供 `:help`、`:mode`、`:approvals`、`:exit`、`:quit`，适合课程演示
常见 harness CLI 形态。

Task 15 后续补强 first-run 配置体验。先写 CLI 集成测试覆盖三个行为：新 workspace 中
`harness config init` 会创建 `.guarded-harness/provider.json`；已有配置时默认拒绝覆盖；
传入 `--force` 时才重置为默认 provider 模板。测试在没有 `config` 子命令时先失败，随后
实现 Typer `config init` 子命令并新增 `config/provider.example.json`，让刚从 GitHub clone
下来的用户无需手动创建隐藏目录即可完成 live provider 配置。该文件仍只保存 mode、
base URL、model 和 timeout，API key 继续通过 OS keyring 或环境变量提供。

## 关键验证

| 命令 | 结果 |
| --- | --- |
| `.\.venv\Scripts\python.exe -m pytest -q` | `269 passed, 2 skipped, 1 warning` |
| `.\.venv\Scripts\python.exe -m compileall -q src tests` | PASS |
| `git diff --check` | PASS |
| `.github/workflows/ci.yml` | Python 3.11/3.12 matrix，安装 `.[dev]`，运行 pytest 和 compileall |

## 重要实现结论

- `SessionStatus.BLOCKED` 保留在模型中，但当前主循环实际停止态是 `finished`、`waiting_approval`、`failed` 和 `max_steps`。
- CLI 的 `approvals approve/deny` 是跨进程恢复入口，只处理已审批动作或拒绝反馈并结束本轮恢复。
- Web live session 在同一 FastAPI 进程内可以复用已保存或临时输入的 key，审批后继续 provider loop。
- CLI live mode 可以从 `.guarded-harness/provider.json` 读取 mode/base URL/model/timeout；
  `harness config init` 可以为新 workspace 创建该文件，但不会写入或读取文件中的 API key。
- shell 执行层不再把字符串交给系统 shell；策略层和执行层都对 shell control syntax fail-closed。
- Guardrail Demo 是可直接访问的确定性演示页，但不放在主导航中，避免干扰主要 Chat/Settings/Approvals 流程。

## 文档整理记录

### 整理前的问题

- 根目录同时放着课程原始要求、历史 handoff、旧设计草案、过程计划和最终交付文档，
  评审者不容易判断哪几份是最终材料。
- 历史过程文件分散在 `.superpowers`、`docs/superpowers` 和根目录，虽然有价值，
  但会淹没 README、SPEC、PLAN、PROCESS、REFLECTION 等主要交付入口。
- 旧文档里残留过时口径，例如旧 UI 参考、旧 CI 文件名、审批按钮语义不完整、
  CLI/Web live provider 恢复能力描述不够精确。

### 整理后的结构

- 根目录保留最终交付文档：`README.md`、`SPEC.md`、`PLAN.md`、`SPEC_PROCESS.md`、
  `REFLECTION.md`、`AGENT_LOG.md`。
- `docs/course` 保存课程原始要求，便于提交前对照，但不混入项目叙事。
- `docs/archive/superpowers` 保存历史 specs、plans、SDD reports 和 handoff。
- `.github/workflows/ci.yml` 作为当前仓库的 CI 入口。
- 旧 CI 配置删除，避免与当前 GitHub Actions 入口产生冲突。

### 口径统一结果

- 审批语义统一为 `Approve once`、`Deny action`、`Stop task`。
- shell 语义统一为 argv parsing + `shell=False` + shell control syntax 拒绝。
- 凭据语义统一为 keyring、环境变量或当前进程内存，不写入业务持久化数据。
- 配置语义统一为 `.guarded-harness/provider.json` 保存非敏感 provider 设置。
- WebUI 范围统一为 Chat Workspace、Provider Settings、Session Trace、Approvals Queue
  和 Guardrail Demo。
- CI 语义统一为 GitHub Actions Python 3.11/3.12 matrix。
- Superpowers 过程证据保留在归档目录，根目录文档只呈现最终可提交版本。
