title: FastAPI 与 Nginx：502 故障排查
product: FastAPI
version: 通用
source: 项目内置运维教学资料 / fastapi-502.md
---
# FastAPI 与 Nginx：502 故障排查

本文是项目自编教学资料。请以实际环境验证结果为准。

## 502 与 Connection refused
当 Nginx 返回 502 Bad Gateway，且 error.log 包含 connect() failed (111: Connection refused) while connecting to upstream，通常说明目标地址没有可接受连接的服务。先检查应用进程是否存活、监听地址和端口，再核对 proxy_pass 中的上游地址。
容器内 Uvicorn 若仅监听 127.0.0.1，其他容器通常无法通过容器 IP 访问。常见启动方式为 uvicorn app.main:app --host 0.0.0.0 --port 8000。修改后应在同一容器网络内检查 /health，并验证反向代理。

## 504 与上游超时
504 Gateway Timeout 表示代理等待上游超时。应检查请求耗时、慢查询、外部 API 超时和 worker 阻塞。先定位慢操作，再评估 proxy_read_timeout。仅增大超时不能消除应用阻塞。

## 变更与验证记录
排查前记录服务版本、部署时间、Nginx 错误片段及健康检查结果。变更监听地址或重启应用后，复查 /health 和失败请求，保留前后结果。重启、修改配置和执行生产命令应遵守团队变更流程。
