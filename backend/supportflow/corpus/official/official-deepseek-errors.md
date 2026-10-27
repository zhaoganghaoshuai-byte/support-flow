title: DeepSeek 官方文档导读：请求错误、认证与限流
product: DeepSeek
version: 通用
source: DeepSeek 官方文档的中文原创摘要
source_url: https://api-docs.deepseek.com/quick_start/error_codes
source_license: 原站版权；仓库仅保存原创摘要
retrieved_at: 2026-10-27T07:40:55.955026+00:00
content_hash: 80cfc13182365dcc07d18a15484ad0c12b17802df83aabb96fdee6e7008a263b
---
# DeepSeek API 错误排查

## 请求格式与账号配置
400 通常指请求格式问题，422 指参数不合法，应根据错误提示核对字段。401 指 API key 认证失败；402 指余额不足。认证排查应在服务端配置中完成，不把密钥写进对话或工单。

## 限流与服务端错误
429 表示请求频率或并发限制，需要合理降低请求节奏。500 是服务端错误，503 表示服务过载，官方建议短暂等待后重试；持续错误需联系服务支持。应用应设置有限重试与超时，并记录脱敏状态。

本页为官方错误码页的原创摘要，不复制完整原站文档。
