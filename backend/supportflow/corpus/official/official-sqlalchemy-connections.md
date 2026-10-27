title: SQLAlchemy 官方文档导读：连接池、失效连接与事务重试
product: SQLAlchemy
version: 通用
source: SQLAlchemy 官方文档的中文原创摘要
source_url: https://docs.sqlalchemy.org/en/20/faq/connections.html
source_license: MIT
retrieved_at: 2026-10-27T07:40:54.585230+00:00
content_hash: 0ff8eb2cd4421181207c9c21b4cf0909e4e70d6b9cba700df5a2d71fcb71afa7
---
# SQLAlchemy 连接管理

## Engine 与连接池
多数数据库方言的 Engine 会管理应用级连接池。数据库连接配置可以通过连接参数传入驱动。应区分连接池获取连接、数据库连接建立和 SQL 事务执行三个阶段，结合对应异常定位问题。

## 失效连接与事务边界
断开的连接可以在后续使用时被检测，但已经丢失的事务不能自动恢复为原状态。重试通常需要在应用层重新执行完整事务；写操作还需检查幂等性，不能把一次超时直接当成写入失败。

本页为原创摘要；更多连接和进程使用限制请查阅官方 FAQ。
