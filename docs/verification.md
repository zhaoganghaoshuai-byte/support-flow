# 构建与验证记录

验证日期：2026-10-26，Asia/Shanghai。

## 已完成的检查

| 检查 | 结果 | 覆盖内容 |
| --- | --- | --- |
| 后端 pytest | 16 项通过 | 登录退出、资源归属、草稿确认、并发去重、幂等冲突、状态机、乐观锁、评论、知识过滤、SSE 重放、重启恢复、错误脱敏、真实工具循环的离线替身、并发运行接纳、工具拒绝、公共扩展契约 |
| 前端 Vitest / Testing Library | 5 项通过 | 登录工作台、工单筛选、草稿必须经点击确认、中文跨字节 SSE 解码、断流识别 |
| TypeScript 与 Vite 构建 | 通过 | 生成 `frontend/dist`，JS 约 438 KB，gzip 约 134 KB；CSS 约 41 KB |
| Ruff | 通过 | 后端、测试和脚本的静态检查与格式检查 |
| pip check | 通过 | 当前环境依赖一致性 |
| 隔离 HTTP 全流程 | 通过 | 实际启动临时 API 进程，读取 HTML / JS / CSS，登录、排查、草稿、确认、重复提交、越权拒绝、状态修改与评论 |
| DeepSeek 真实模型验收 | 通过 | `deepseek-flash` 实际执行 2 次 `search_knowledge`，返回 4 条来源；记录 3348 输入 Token、701 输出 Token，单次流程约 8.55 秒 |

真实模型统计是本次合成问题的观测值，不代表平均性能或服务保证。工具完成、检索命中与问题真正解决是不同指标。

HTTP 验收使用独立临时数据库并停止自己启动的服务。脚本显式绕过 Python 环境代理，避免本机回环请求被代理成 502；没有修改系统代理。

## 离线检索评测

数据集：`evaluation/retrieval_cases.json`，30 条自编样例、5 份自编教学文档。

| 指标 | 结果 | 分母 |
| --- | --- | --- |
| 文档 Top-1 命中 | 100% | 27 条有目标文档的样例 |
| 文档 Top-3 命中 | 100% | 同上 |
| 无结果用例正确率 | 66.67% | 3 条应无结果的样例，2 条正确 |

误召回用例 q27：查询“**不存在的专有标识 ZXQVV_998877**”仍命中支持流程文档。中文双字片段“存在”与资料中的“存在替代路径”重叠，但实际语义无关。

这说明当前 BM25 的无答案判断不足。数据集是小型合成集，没有独立真实用户测试集，也没有测试向量检索、重排或模型回答忠实度。不要把 27/27 写成“真实业务问答准确率 100%”。下一步应增加独立的真实问题集，再比较相关性阈值、重排与无答案判断。

可重复生成本地报告：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py
.\.venv\Scripts\python.exe scripts/smoke_http.py
```

报告分别写入忽略提交的 `artifacts/evaluation.json`、`artifacts/http-smoke.json`。真实模型脚本另写 `artifacts/live-smoke.json`，不保存密钥或完整模型请求。

## 已知验证范围

- 当前工具没有可连接的浏览器，未完成真实浏览器截图、响应式布局视觉检查或浏览器端到端验收。前端交互测试使用 happy-dom，不代替真实布局检查。
- Docker / Compose 文件已提供，但本环境没有 Docker，未构建镜像。
- PostgreSQL 仅提供 SQLAlchemy 配置与可选驱动，尚未做真实数据库验收。
- DeerFlow 适配器完成公共契约注册、身份映射和模拟 HTTP 测试，尚未启动完整 DeerFlow Gateway 联调。
- 当前版本要求单个 API 进程；没有压测、多实例故障恢复或生产可用性验证。

## 当前验证环境

Python 3.12.15；Node.js 22.23.4；FastAPI 0.162.0；Uvicorn 0.54.0；SQLAlchemy 2.1.6；LangChain 1.4.7；LangGraph 1.2.17；langchain-openai 1.7.2；langgraph-checkpoint-sqlite 3.1.2；pytest 9.1.1；TypeScript 5.8.3；Vite 6.4.5；Vitest 3.2.7。

本机 `.venv` 使用已有 `deepagents-learning` 环境的共享依赖，但新增包只安装在项目自己的虚拟环境。新电脑按 README 的标准独立虚拟环境流程安装，不依赖这个 Conda 环境。
