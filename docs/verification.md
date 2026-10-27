# 构建与验证记录

最近验证日期：2026-10-27，Asia/Shanghai。

## 已完成的检查

| 检查 | 结果 | 覆盖内容 |
| --- | --- | --- |
| 后端 pytest | 92 项通过 | 业务权限与事务、模型适配、SSE、数据库迁移、官方资料抓取与导入、初始化容量边界、BM25 缓存和可选 Chroma 索引 |
| 前端 Vitest / Testing Library | 12 项通过 | 登录、工单筛选、草稿确认、中文 SSE 解码、增量输出、断流提示、知识来源、产品 / 版本过滤及过期搜索响应竞态 |
| TypeScript 与 Vite 构建 | 通过 | 生成 `frontend/dist`，主 JS 约 302 KB / gzip 93 KB，Markdown 约 169 KB、UI 约 44 KB，CSS 约 51 KB；依赖分包 |
| Ruff | 通过 | 后端、测试和脚本的静态检查与格式检查 |
| pip check | 通过 | 当前环境依赖一致性 |
| 隔离 HTTP 全流程 | 通过，退出码 0 | 实际启动临时 API 进程，读取 4 个前端资源，登录、排查、草稿、确认、重复提交、越权拒绝、状态修改与评论；服务进程、监听端口及临时数据库清理完成 |
| DeepSeek 真实模型验收 | 通过 | `deepseek-flash` 两轮咨询、843 个可见文本增量事件、2 次 `search_knowledge` 和 1 次 `draft_ticket`，首轮返回 6 条来源；15903 输入 Token、1628 输出 Token，约 17.57 秒；验证上下文延续、草稿确认与确认去重 |
| Alembic 与部署离线检查 | 17 项通过，计入上述 92 项 | 旧库接管保留数据、不兼容结构拒绝升级、来源字段迁移、当前 ORM 结构一致性、PostgreSQL 离线 DDL 与 Compose / Nginx 契约 |
| 官方来源与初始化测试 | 31 项通过，计入上述 92 项 | 固定来源与 DNS 校验、重定向、格式 / 大小限制、离线缓存哈希、增量入库、导入与初始化的 200 份容量边界、失败整批回滚 |
| Python wheel 资源验证 | 通过 | 实际构建 wheel，检查 13 份 Markdown、来源清单、Alembic 版本脚本及模板完整打包 |

真实模型统计是两轮合成咨询的观测值，不代表平均性能或服务保证。工具完成、检索命中与问题真正解决是不同指标。

HTTP 验收使用独立临时数据库，固定 BM25，并绕过环境代理访问回环接口。验收脚本结束自己启动的进程树，确认端口关闭、临时目录清理完成后才写入成功报告。

SQLite 旧库升级至 `0002_knowledge_sources` 的验证结果：用户 4→4、工单 4→4、消息 8→8、知识文档 5→13。原有业务记录保留，新增 8 份带来源的中文摘要。

Chroma 测试实际使用持久化目录，验证产品范围、增量更新、失效片段删除和重新创建客户端后的索引复用。测试用确定性向量替身替代外部 Embedding 模型，只验证索引工程行为；没有测试真实 Embedding 模型的语义召回质量。默认 `bm25` 可直接运行，`hybrid` / `vector` 需另行配置服务。

## 离线检索评测

使用 `rank-bm25.BM25Plus`，分开报告两个固定开发集：原有 `evaluation/retrieval_cases.json` 保持 30 条问题不变，仅评测 5 份教学文档；新增 `evaluation/official_retrieval_cases.json` 包含 20 条问题，评测 13 份完整资料。

| 数据集 | 首个片段的文档命中 | 前三片段的文档命中 | 无结果用例 |
| --- | --- | --- | --- |
| 原有教学集 | 27/27 | 27/27 | 3/3 |
| 官方资料集 | 17/17 | 17/17 | 3/3 |

脚本取前 3 个片段，再判断其中是否包含目标文档；它们可能来自同一文档，没有按文档去重。因此报告字段 `top3_document_hit_rate` 表示“前三片段中的文档命中率”，不等于取 3 份不同文档后的命中率。

原有 q27“**不存在的专有标识 ZXQVV_998877**”误召回现已消除。改进包括：BM25Plus 基线分数不能单独构成命中，通用停用词过滤，未知配置标识保护及有效词项重叠要求；另外增加 `pg_hba.conf` 等带点标识的回归，避免保护规则误伤有效查询。

官方资料问题先依据来源章节编写，再观察排序；后续仍根据开发集中的失败结果改进了通用预处理规则，因此它不是盲测保留集。两个数据集均为小型自编样例，无结果问题每组只有 3 条。这些数字衡量文档检索回归，不代表真实业务问答准确率、模型回答忠实度或语义无答案能力；尚无独立真实用户测试集。

可重复生成本地报告：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py
.\.venv\Scripts\python.exe scripts/smoke_http.py
```

报告分别写入忽略提交的 `artifacts/evaluation.json`、`artifacts/http-smoke.json`。真实模型脚本另写 `artifacts/live-smoke.json`，不保存密钥或完整模型请求。

## 已知验证范围

- 前端交互测试使用 happy-dom；真实浏览器端到端验收及响应式布局视觉检查尚未完成。
- 三服务 Docker / Compose 文件已提供并有离线契约检查，镜像构建和容器运行验收尚未完成。
- PostgreSQL 驱动、Alembic 路径与离线 DDL 已验证，尚未连接真实 PostgreSQL 执行迁移和业务测试。
- 官方资料的 8 份页面可读文本缓存已完成哈希校验。抓取 CLI 的离线校验与模拟 HTTP 测试通过，联网抓取 CLI 的端到端验收尚未完成。
- DeerFlow 适配器完成公共契约注册、身份映射和模拟 HTTP 测试，尚未启动完整 DeerFlow Gateway 联调。
- 当前版本要求单个 API 进程；没有压测、多实例故障恢复或生产可用性验证。

## 当前验证环境

Python 3.12.15；Node.js 22.23.4；FastAPI 0.162.0；Uvicorn 0.54.0；SQLAlchemy 2.1.6；LangChain 1.4.7；LangGraph 1.2.17；langchain-openai 1.7.2；langgraph-checkpoint-sqlite 3.1.2；pytest 9.1.1；TypeScript 5.8.3；Vite 6.4.5；Vitest 3.2.7。

其他依赖版本：langchain-deepseek 1.1.1、Alembic 1.20.1、rank-bm25 0.2.2、beautifulsoup4 4.15.0、psycopg 3.3.6、Chroma 1.5.9；前端 Tailwind CSS 4.3.3、Radix Dialog 1.3.1。模型工厂使用官方 DeepSeek 适配器并显式禁用思考模式。模型密钥由后端环境或被 Git 忽略的 `.env` 提供，不写入文档或报告。

项目安装步骤见 README，使用独立虚拟环境安装项目依赖。
