# 官方资料来源与入库

项目保留原有 5 份教学资料，并增加 8 份根据官方资料整理的中文原创摘要。摘要位于 `backend/supportflow/corpus/official/`，对应的来源清单为同目录的 `manifest.json`。摘要用于帮助检索和排查，涉及版本细节时应打开原始文档核对。

## 已整理的来源

| 主题 | 官方来源 | 上游许可信息 |
| --- | --- | --- |
| FastAPI 容器部署、启动与退出 | [FastAPI in Containers](https://fastapi.tiangolo.com/deployment/docker/) | [FastAPI MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| FastAPI 代理转发头与路径前缀 | [Behind a Proxy](https://fastapi.tiangolo.com/advanced/behind-a-proxy/) | [FastAPI MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Compose 启动依赖与健康检查 | [Startup order](https://docs.docker.com/compose/how-tos/startup-order/) | [docker/docs Apache-2.0](https://github.com/docker/docs/blob/main/LICENSE) |
| Compose 服务发现与端口 | [Networking](https://docs.docker.com/compose/how-tos/networking/) | [docker/docs Apache-2.0](https://github.com/docker/docs/blob/main/LICENSE) |
| SQLAlchemy 连接管理与事务重试 | [Connections / Engines FAQ](https://docs.sqlalchemy.org/en/20/faq/connections.html) | [SQLAlchemy MIT](https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE) |
| PostgreSQL 客户端身份认证 | [Client Authentication](https://www.postgresql.org/docs/current/client-authentication.html) | [PostgreSQL License](https://www.postgresql.org/about/licence/) |
| LangGraph 检查点和跨线程存储 | [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | [LangChain docs MIT](https://github.com/langchain-ai/docs/blob/main/LICENSE) |
| DeepSeek 请求错误、认证和限流 | [Error Codes](https://api-docs.deepseek.com/quick_start/error_codes/) | 原站版权；仓库仅保存原创摘要和来源链接 |

`docker/docs` 的仓库许可证实际为 Apache-2.0。这里记录所引用仓库的许可链接，未将全部第三方文档重新打包为项目源码。

## 来源记录的含义

每份摘要保存标题、产品、版本范围、来源 URL、上游许可信息、抓取时间和摘要正文 SHA256。清单额外保存章节对应链接、原始来源文本提取的 SHA256，以及提取方式。

摘要依据上述 8 个官方页面的可读文本整理，清单中的 `extraction_method` 为 `readable-page-text`。`source_sha256` 表示来源页面可读文本的哈希，**不是原始 HTTP 响应字节的哈希**。官方站点未提供可验证的源版本号时，`source_revision` 为 null；日期保留在 `retrieved_at` 中。摘要的 `content_hash` 则只对入库的中文正文计算。

获取的来源文本缓存于被 Git 忽略的 `artifacts/official-docs/`。项目提交的是短篇原创摘要及其来源清单。网站内容会更新，当前摘要不会自动随网站变化。

## 可重复的抓取与导入

运行以下命令会抓取固定的 8 个官方来源并生成缓存与 dry-run 报告，不写入业务数据库：

```powershell
.\.venv\Scripts\python.exe scripts/import_official_docs.py
```

也可以只选一个已登记的来源：

```powershell
.\.venv\Scripts\python.exe scripts/import_official_docs.py --source official-docker-startup
```

确认来源与缓存后，由操作人员显式导入。必须指定已存在且处于启用状态的工程师或管理员账号：

```powershell
.\.venv\Scripts\python.exe scripts/import_official_docs.py --offline --apply --creator-email engineer@supportflow.local
```

`--offline` 先校验缓存正文哈希，再复用已获取的来源文本，不发起网络请求。数据库使用确定的导入文档 ID，通过内容哈希区分新增、更新和未变化；重复导入不会生成重复文档。摘要的 `official-*` ID 与完整来源提取的 `import-*` ID 分开，避免误把中文摘要覆盖为英文原文。导入脚本不会创建用户或扩大账号权限。

## 网络边界

抓取器只允许列出的官方 HTTPS 域名和已登记的 GitHub 官方仓库路径，拒绝 URL 凭据、查询参数、非标准端口和私有地址。每次重定向都重新校验地址，并限制重定向次数、响应大小、正文长度、超时和内容类型。抓取能力只供操作人员执行，不暴露为模型可任意调用的网络工具。

使用 fake-IP DNS 的网络代理可能将官方域名解析到非公网地址，抓取器会拒绝这类结果。联网抓取需要能够返回真实公网 DNS 结果的网络环境；也可通过可信渠道准备并核对来源缓存，再使用 `--offline` 校验和导入。
