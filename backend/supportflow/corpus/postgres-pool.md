title: PostgreSQL 与 SQLAlchemy：连接池和慢查询
product: PostgreSQL
version: 通用
source: 项目内置运维教学资料 / postgres-pool.md
---
# PostgreSQL 与 SQLAlchemy：连接池和慢查询

本文是项目自编教学资料。

## QueuePool limit reached 与连接池耗尽
出现 QueuePool limit of size reached、connection pool exhausted 或获取连接超时时，检查 Session 和 Connection 是否在请求完成后关闭。使用 with Session(engine) 或依赖注入的 try/finally 释放连接。检查长事务、未提交事务和慢查询是否长期占用连接。
pool_size、max_overflow、pool_timeout 应结合数据库 max_connections 与应用 worker 数计算。不要在未核对总连接预算时盲目扩大池。记录连接占用率、请求并发与等待时间。

## 慢查询与索引
先记录慢 SQL 和执行时间，再在合适环境用 EXPLAIN 分析执行计划，必要时评估索引。涉及真实执行的 EXPLAIN ANALYZE 要确认语句副作用和负载。连接问题与慢查询可能同时发生。

## 数据库连接被拒绝
connection refused 通常需要检查目标主机、端口、网络可达性和数据库监听。认证失败则检查用户名、数据库名、凭据与 pg_hba.conf。请勿把完整连接字符串中的密码贴进工单。
