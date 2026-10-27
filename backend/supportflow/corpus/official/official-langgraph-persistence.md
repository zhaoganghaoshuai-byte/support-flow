title: LangGraph 官方文档导读：检查点、会话与长期存储
product: LangGraph
version: 通用
source: LangGraph 官方文档的中文原创摘要
source_url: https://docs.langchain.com/oss/python/langgraph/persistence
source_license: MIT
retrieved_at: 2026-10-27T07:40:50.270676+00:00
content_hash: a8214b0be1cfd41673835ae332f86c68f0cfbf66014ff6f86b219e2ee76bad61
---
# LangGraph 持久化

## Checkpointer 与 thread_id
Checkpointer 保存单个线程的图状态检查点，用于延续会话、恢复中断和故障恢复。调用时通过 thread_id 定位对应线程。该索引需要由应用层结合真实用户身份与资源归属进行授权。

## Store 与跨会话数据
Store 保存图状态之外的应用数据，可用于跨线程偏好、事实和共享知识。会话检查点与长期存储的范围不同，应用可以同时使用两者。是否能跨进程恢复，还取决于实际采用的存储后端。

本页为官方持久化文档的原创摘要；示例中的内存后端不应当作持久磁盘存储。
