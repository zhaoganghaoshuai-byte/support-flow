title: Docker 官方文档导读：启动顺序与数据库就绪
product: Docker
version: 通用
source: Docker 官方文档的中文原创摘要
source_url: https://docs.docker.com/compose/how-tos/startup-order/
source_license: Apache-2.0
retrieved_at: 2026-10-27T07:40:51.711775+00:00
content_hash: f6610350021c59e66954d7fdc5883724d462b8e776fa5c9a20b78a3ab1ebae2d
---
# Compose 启动顺序

## 已启动与已就绪
depends_on 可以表达依赖启动顺序，但容器进程开始运行并不表示数据库已经能接受连接。对依赖项设置 healthcheck，并使用 service_healthy 条件，可以让后续服务等待健康检查通过。

## 不同依赖条件
service_started 关注容器启动；service_healthy 关注健康检查；service_completed_successfully 适合先完成的初始化任务。数据库连接失败时，先核对健康状态与初始化进度，再区分网络、凭据和 SQL 错误。

本页为根据官方说明整理的原创摘要，实际健康命令需匹配镜像和账号。
