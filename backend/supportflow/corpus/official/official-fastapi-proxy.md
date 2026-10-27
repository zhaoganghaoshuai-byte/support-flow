title: FastAPI 官方文档导读：代理转发头与路径前缀
product: FastAPI
version: 通用
source: FastAPI 官方文档的中文原创摘要
source_url: https://fastapi.tiangolo.com/advanced/behind-a-proxy/
source_license: MIT
retrieved_at: 2026-10-27T07:40:57.430713+00:00
content_hash: 4ddec3bfadf8f41ab14336817c01ca075aa84b010b1638e466924a37de979b1c
---
# FastAPI 反向代理

## 转发头与可信代理
代理通过 X-Forwarded-For、X-Forwarded-Proto、X-Forwarded-Host 描述原始客户端、协议和主机。服务端应只信任受控代理的来源地址，避免把任意客户端提供的转发头当作真实连接信息。错误的协议识别可能导致重定向地址使用 HTTP。

## 路径前缀与 root_path
当代理剥离公开 URL 的前缀时，应用需要正确的 root_path 才能生成符合公开路径的文档和地址。排查时对照用户访问路径、代理改写规则和应用实际路由。

本页为原创摘要；示例配置必须结合实际代理拓扑验证。
