# SupportFlow · 技术支持与工单协作平台

参考 DeerFlow 的技术架构实现的独立全栈项目。用户描述故障后，Agent 检索知识、分析日志并提出排查建议；需要升级时先形成草稿，由用户确认后正式创建工单，支持工程师继续分派、讨论与跟进。

**技术栈：Python 3.12+ · FastAPI · LangChain / LangGraph · SQLAlchemy · SQLite · React 19 · TypeScript · Vite。**

## 界面演示

以下为离线演示模式下的平台截图。

**工作台**：集中查看工单数量、处理状态和最近更新。

![SupportFlow 工作台](docs/screenshots/dashboard.png)

<details>
<summary>查看登录页面</summary>

支持工程师、提问用户与管理员演示角色切换。

![SupportFlow 登录页面](docs/screenshots/login.png)

</details>

<details>
<summary>查看 AI 支持助手</summary>

通过多轮咨询开展排查，并查看知识引用和工具执行记录。

![SupportFlow AI 支持助手](docs/screenshots/assistant.png)

</details>

<details>
<summary>查看工单中心</summary>

按状态筛选工单，查看优先级、处理人与更新进展。

![SupportFlow 工单中心](docs/screenshots/tickets.png)

</details>

<details>
<summary>查看知识库</summary>

检索与维护团队运维文档，为排查提供知识依据。

![SupportFlow 知识库](docs/screenshots/knowledge.png)

</details>

<details>
<summary>查看运行记录</summary>

查看任务结果、执行耗时、工具调用次数与模型用量。

![SupportFlow 运行记录](docs/screenshots/runs.png)

</details>

## 快速开始

需要 Python 3.12+ 和 Node.js 22+。以下命令适用于 Windows PowerShell：

```powershell
git clone https://github.com/zhaoganghaoshuai-byte/support-flow.git
cd support-flow
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m supportflow.cli
```

打开 **http://127.0.0.1:8010**，接口文档为 **http://127.0.0.1:8010/docs**。默认离线演示模式无需模型密钥。通过 Ctrl+C 停止前台服务。

本地演示账号（密码均为 `SupportFlow123!`）：

| 账号 | 角色 | 权限 |
| --- | --- | --- |
| `engineer@supportflow.local` | 支持工程师 | 团队工单、分派、状态修改、知识添加 |
| `customer@supportflow.local` | 提问用户 | 本人的工单、会话、草稿和评论 |
| `admin@supportflow.local` | 管理员 | 本版与工程师具有相同业务管理权限 |
| `another@supportflow.local` | 另一位提问用户 | 用于验证用户之间的数据隔离 |

默认 `demo` 模式不需要模型密钥。初始工单、监控值均为明确标注的模拟数据，知识文档为项目自编教学资料。登录界面可切换演示角色。

## 已实现的流程

- 工作台：实际工单数量、状态分布、最近更新和常用排查入口。
- AI 支持助手：独立多轮会话、SQLite 检查点、进度与工具事件流、来源快照、工单草稿。
- 工单中心：搜索筛选、分页、草稿确认、工程师分派、状态机、优先级、评论与操作时间线。
- 知识库：中文 / 英文 BM25 检索、产品 / 版本过滤、文档阅读、Markdown / 文本入库。
- 运行记录：本人的执行结果、耗时、工具次数和真实模型 Token 用量。
- 业务约束：Bearer 会话、资源归属、并发创建去重、幂等键冲突检测和乐观锁。
- 可选 DeerFlow 扩展：通过公开契约暴露检索和工单查询。

## 本地开发

已完成安装后，再次启动只需在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m supportflow.cli
```

前后端分开开发时，后端使用上述命令；另开终端进入 `frontend` 后执行 `npm run dev`。Vite 的 `/api` 代理指向 `127.0.0.1:8010`。虚拟环境、Node.js 安装目录、运行数据库和前端构建产物均不纳入源码仓库，首次克隆后需按“快速开始”安装与构建。

## 使用真实模型

复制 `.env.example` 为 `.env`，设置：

```dotenv
SUPPORTFLOW_AGENT_MODE=live
DEEPSEEK_API_KEY=自己的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
```

重启后，页面右上角显示“模型模式”。也可以设置 `SUPPORTFLOW_API_KEY / SUPPORTFLOW_BASE_URL / SUPPORTFLOW_MODEL` 使用其他兼容 Chat Completions 的工具调用模型。

真实模式使用 `create_agent()`；离线模式使用固定的 LangGraph 流程，界面和回答会明确标注。真实调用产生模型费用，不把离线输出当成模型能力展示。密钥只保存在后端环境或忽略提交的 `.env` 中。

运行一次显式的真实模型验收：

```powershell
.\.venv\Scripts\python.exe scripts/smoke_live.py --env-file .env
```

该脚本在临时数据库中发送一条合成问题，验证模型确实调用检索工具并返回来源。仅输出调用统计，不输出凭据和完整请求。

## 测试与评测

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests scripts
.\.venv\Scripts\python.exe scripts/evaluate.py
.\.venv\Scripts\python.exe scripts/smoke_http.py
cd frontend
npm test
npm run build
```

后端测试覆盖资源隔离、并发去重、状态机、版本冲突、知识过滤、SSE 幂等、重启恢复与模型工具循环。前端交互测试覆盖登录、工单筛选，以及“模型草稿不能直接创建工单”的确认流程。

DeerFlow 适配器的 3 项测试需要公共契约；未安装时会跳过该测试模块。要一起运行，可先在本项目环境中执行 `python -m pip install -e ../deer-flow-main/backend/packages/extension-api`。

`evaluation/retrieval_cases.json` 包含 30 条自编检索样例。`artifacts/evaluation.json` 报告文档 Top-1、Top-3 和无结果用例表现；该小型合成数据集不能代表真实业务准确率或模型回答准确率。

详细验证结果和限制见 [docs/verification.md](docs/verification.md)。

## Docker 与数据库

```powershell
docker compose up --build
```

Compose 只向本机发布 `127.0.0.1:8010`，数据保存在命名卷中。若要换用 PostgreSQL，安装 `pip install -e ".[postgres]"` 并设置 `SUPPORTFLOW_DATABASE_URL`；这仅替换业务数据库。

当前版本要求 **一个 API 进程**，检查点仍是本地 SQLite，不支持多副本部署。真实部署前可关闭初始化演示账号：`SUPPORTFLOW_SEED_DEMO=false`。然后创建实际账号：

```powershell
.\.venv\Scripts\python.exe scripts/create_user.py --email you@example.com --name 你的名字 --role admin
```

密码通过交互输入。关闭初始化不会删除已经存在的演示账号，已有演示数据库请继续仅用于演示。

## 代码导航

```text
backend/supportflow/
  app.py                 API、身份与 SSE 任务接纳
  agent.py               demo 图、真实 Agent、领域工具
  services.py            工单事务、状态机、幂等与版本检查
  knowledge.py           文档分段、中文切词与 BM25
  models.py              业务数据结构
  security.py            密码哈希与访问会话
  deerflow_extension.py  可选公共契约适配器
  corpus/                自编运维知识
frontend/src/            React 页面、交互与样式
tests/                   后端集成测试
evaluation/              可重复检索样例
scripts/                 启动、开户、评测与真实模型验收
```

进一步阅读：[架构与 DeerFlow 对应关系](docs/architecture.md)、[DeerFlow 接入](docs/deerflow-integration.md)、[实践与架构导读](docs/learning-guide.md)。
