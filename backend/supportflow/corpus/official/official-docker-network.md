title: Docker 官方文档导读：Compose 服务发现与端口
product: Docker
version: 通用
source: Docker 官方文档的中文原创摘要
source_url: https://docs.docker.com/compose/how-tos/networking/
source_license: Apache-2.0
retrieved_at: 2026-10-27T07:40:53.203260+00:00
content_hash: 1c7b1fbeabc217b56976d0227b36c26f7ab5ad294c306f7a4b5f8b092ec0065d
---
# Compose 容器网络

## 服务名与容器端口
同一 Compose 网络中的服务可以通过服务名发现彼此。应用访问数据库时，应使用数据库服务名和容器内端口；宿主机映射端口用于从宿主机访问。容器中的 localhost 指向容器自身。

## 更新后的连接
重新创建服务容器后，容器 IP 可能变化，服务名仍是连接入口。客户端需要重新解析地址并处理旧连接失效。排查时检查端口映射、网络成员关系和连通性，不应依赖易变的容器 IP。

本页为原创摘要，网络变更前应确认服务边界与数据保留需求。
