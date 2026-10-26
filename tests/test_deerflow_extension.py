import asyncio
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("deerflow_extension_api")
from supportflow.deerflow_extension import install


def plugin(config):
    contributions = []
    registry = SimpleNamespace(plugin=lambda contribution: contributions.append(contribution))
    install(registry, config)
    return contributions[0]


def test_extension_denies_unmapped_principal_without_network():
    contribution = plugin({"enabled": True})
    context = SimpleNamespace(principal=SimpleNamespace(user_id="unmapped"))
    with pytest.raises(ValueError, match="尚未绑定"):
        asyncio.run(contribution.tools[0].handler({"query": "502"}, context))
    assert {tool.name for tool in contribution.tools} == {
        "supportflow_search",
        "supportflow_ticket",
    }


def test_extension_uses_host_principal_mapping_and_upstream_authorization(monkeypatch):
    monkeypatch.setenv("TEST_SUPPORTFLOW_ALICE", "alice-token")
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"items": []})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)),
    )
    contribution = plugin(
        {"enabled": True, "principal_token_env": {"host-alice": "TEST_SUPPORTFLOW_ALICE"}}
    )
    context = SimpleNamespace(principal=SimpleNamespace(user_id="host-alice"))
    result = asyncio.run(
        contribution.tools[0].handler({"query": "502", "user_id": "host-bob"}, context)
    )
    assert result == {"items": []}
    assert seen[0].headers["Authorization"] == "Bearer alice-token"
    assert seen[0].url.path == "/api/knowledge/search"


def test_extension_validates_ticket_path():
    contribution = plugin({"enabled": True})
    context = SimpleNamespace(principal=SimpleNamespace(user_id="alice"))
    with pytest.raises(ValueError, match="Invalid ticket"):
        asyncio.run(contribution.tools[1].handler({"ticket_id": "../auth/me"}, context))
