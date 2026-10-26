"""Optional DeerFlow extension using only the public extension contract.

DeerFlow principal IDs are explicitly mapped to existing SupportFlow access tokens.
An unconfigured principal has no access. The model can never confirm a draft.
"""

import os

import httpx


def install(registry, config):
    from deerflow_extension_api import ModelTool, PluginContribution

    base_url = config.get("base_url", "http://127.0.0.1:8010")
    mappings = config.get("principal_token_env", {})
    if not isinstance(base_url, str) or not base_url.startswith(("http://", "https://")):
        raise ValueError("Configure a trusted SupportFlow base_url")
    if not isinstance(mappings, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in mappings.items()
    ):
        raise ValueError("principal_token_env must map host user IDs to environment variable names")

    async def request(context, method, path, **kwargs):
        variable = mappings.get(context.principal.user_id)
        token = os.getenv(variable, "") if variable else ""
        if not token:
            raise ValueError("当前 DeerFlow 账号尚未绑定 SupportFlow，请由管理员配置本人会话映射")
        async with httpx.AsyncClient(
            base_url=base_url, timeout=15, follow_redirects=False, trust_env=False
        ) as client:
            response = await client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
            if response.status_code >= 400:
                raise ValueError(
                    f"SupportFlow 请求未成功（HTTP {response.status_code}），请检查绑定或资源权限"
                )
            return response.json()

    async def search(payload, context):
        query = payload.get("query")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
            raise ValueError("query must contain 1–1000 characters")
        return await request(context, "GET", "/api/knowledge/search", params={"q": query.strip()})

    async def ticket(payload, context):
        identifier = payload.get("ticket_id")
        if (
            not isinstance(identifier, str)
            or not 1 <= len(identifier) <= 80
            or any(
                char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
                for char in identifier
            )
        ):
            raise ValueError("Invalid ticket identifier")
        return await request(context, "GET", f"/api/tickets/{identifier}")

    registry.plugin(
        PluginContribution(
            namespace="supportflow.support",
            title="SupportFlow 技术支持",
            description="检索运维知识，查询当前绑定账号有权访问的工单。工单确认仍在 SupportFlow 中完成。",
            enabled=bool(config.get("enabled", False)),
            tools=(
                ModelTool(
                    "supportflow_search",
                    "检索 SupportFlow 团队运维知识并返回来源",
                    {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "minLength": 1, "maxLength": 1000}
                        },
                        "required": ["query"],
                        "additionalProperties": False,
                    },
                    search,
                ),
                ModelTool(
                    "supportflow_ticket",
                    "查询绑定账号有权访问的工单；不允许指定用户身份",
                    {
                        "type": "object",
                        "properties": {
                            "ticket_id": {"type": "string", "minLength": 1, "maxLength": 80}
                        },
                        "required": ["ticket_id"],
                        "additionalProperties": False,
                    },
                    ticket,
                ),
            ),
        )
    )


# Keep the optional contract import out of ordinary standalone application startup.
try:
    from deerflow_extension_api import extension
except ImportError:
    pass
else:
    install = extension(api="0.2.9", name="supportflow")(install)
