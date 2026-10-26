title: Docker Compose：容器网络与服务发现
product: Docker
version: 通用
source: 项目内置运维教学资料 / docker-network.md
---
# Docker Compose：容器网络与服务发现

本文是项目自编教学资料。

## 容器中的 localhost
容器内 localhost 和 127.0.0.1 指向当前容器。应用连接另一个 PostgreSQL 容器时，应使用 Compose 服务名（例如 db:5432），而不是 localhost:5432。两个服务需要加入同一网络。
容器间使用服务内部端口。宿主机映射端口面向宿主机访问，不应机械地用于容器间连接。

## 启动顺序与健康检查
depends_on 的简单顺序并不保证数据库已就绪。可以配置数据库健康检查及 service_healthy 条件，并让应用以有界退避方式重新建立连接。记录失败时间、DNS 解析、网络和健康状态。

## 排查 DNS 与网络
检查服务名是否拼写正确，服务是否在同一个 Compose 网络，数据库是否监听正确地址。网络排查只读查询优先，避免直接重建生产网络或删除数据卷。
