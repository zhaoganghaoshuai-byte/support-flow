"""DeepSeek wire compatibility is checked with real SDK clients and offline HTTP."""

import json
from dataclasses import replace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from supportflow.config import Settings
from supportflow.model_factory import SupportFlowChatDeepSeek, create_chat_model, resolve_provider


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("https://api.deepseek.com", "deepseek"),
        ("https://api.deepseek.com/v1", "deepseek"),
        ("https://API.DEEPSEEK.COM/v1/", "deepseek"),
        ("https://api.deepseek.com.other.example/v1", "openai-compatible"),
        ("https://models.example/v1/deepseek", "openai-compatible"),
    ],
)
def test_auto_provider_uses_endpoint_host_not_model_name(settings, endpoint, expected):
    assert (
        resolve_provider(replace(settings, base_url=endpoint, model="deepseek-flash")) == expected
    )


def test_factory_selects_deepseek_and_disables_implicit_thinking(settings):
    model = create_chat_model(replace(settings, api_key="test-only-credential"))
    assert isinstance(model, ChatDeepSeek)
    assert model.extra_body == {"thinking": {"type": "disabled"}}
    assert model.use_responses_api is False
    assert model.model_name == "deepseek-flash"


def test_generic_endpoint_keeps_openai_compatible_protocol(settings):
    model = create_chat_model(
        replace(settings, api_key="test-only-credential", base_url="https://models.example/v1")
    )
    assert isinstance(model, ChatOpenAI) and not isinstance(model, ChatDeepSeek)
    assert not model.extra_body


def test_bad_configuration_is_rejected_and_key_is_not_in_repr(settings):
    with pytest.raises(ValueError, match="密钥"):
        create_chat_model(settings)
    with pytest.raises(ValueError, match="provider"):
        create_chat_model(
            replace(settings, api_key="test-only-credential", model_provider="unknown")
        )
    assert "test-only-credential" not in repr(replace(settings, api_key="test-only-credential"))


def test_settings_preserve_explicit_generic_overrides(settings, monkeypatch, tmp_path):
    import supportflow.config as config

    monkeypatch.setattr(config, "ROOT", tmp_path)
    for key in [
        "SUPPORTFLOW_MODEL_PROVIDER",
        "SUPPORTFLOW_API_KEY",
        "SUPPORTFLOW_MODEL",
        "SUPPORTFLOW_BASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    assert Settings.load().api_key == "test-deepseek-key"
    monkeypatch.setenv("SUPPORTFLOW_API_KEY", "test-custom-key")
    monkeypatch.setenv("SUPPORTFLOW_BASE_URL", "https://models.example/v1")
    monkeypatch.setenv("SUPPORTFLOW_MODEL", "custom-model")
    loaded = Settings.load()
    assert (loaded.api_key, loaded.model) == ("test-custom-key", "custom-model")
    assert resolve_provider(loaded) == "openai-compatible"


def test_health_exposes_provider_and_model_without_credentials(settings):
    from fastapi.testclient import TestClient
    from supportflow.app import create_app

    credential = "sensitive-test-only-credential"
    with TestClient(create_app(replace(settings, agent_mode="live", api_key=credential))) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["model_provider"] == "deepseek"
    assert response.json()["model"] == "deepseek-flash"
    assert credential not in response.text and "api_key" not in response.json()


def test_request_replays_reasoning_and_normalizes_tool_call_content():
    model = SupportFlowChatDeepSeek(
        api_key="test-only-credential",
        model="deepseek-flash",
        extra_body={"thinking": {"type": "disabled"}},
    )
    thought = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "provider-specific test metadata"},
        tool_calls=[{"name": "lookup", "args": {}, "id": "call-one", "type": "tool_call"}],
    )
    messages = [
        HumanMessage(content="test"),
        thought,
        ToolMessage(content="found", tool_call_id="call-one"),
    ]
    payload = model._get_request_payload(messages)
    assistant = payload["messages"][1]
    assert assistant["content"] == ""
    assert assistant["reasoning_content"] == "provider-specific test metadata"
    assert thought.content == "" and len(messages) == 3


def test_legacy_checkpoint_without_reasoning_can_be_replayed_in_thinking_mode():
    model = SupportFlowChatDeepSeek(
        api_key="test-only-credential",
        model="deepseek-flash",
        extra_body={"thinking": {"type": "enabled"}},
    )
    message = AIMessage(
        content="", tool_calls=[{"name": "lookup", "args": {}, "id": "legacy", "type": "tool_call"}]
    )
    assistant = model._get_request_payload([message])["messages"][0]
    assert assistant["content"] == "" and assistant["reasoning_content"] == ""
    assert "reasoning_content" not in message.additional_kwargs


def test_real_sdk_keeps_deepseek_fields_across_tool_round_trip():
    requests = []

    def transport(request):
        payload = json.loads(request.content)
        requests.append(payload)
        message = {"role": "assistant", "content": "完成"}
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "content": "",
                "reasoning_content": "test provider metadata",
                "tool_calls": [
                    {
                        "id": "sdk-call",
                        "type": "function",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            }
        return httpx.Response(
            200,
            json={
                "id": "offline-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": message,
                        "finish_reason": "tool_calls" if len(requests) == 1 else "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        model = SupportFlowChatDeepSeek(
            api_key="test-only-credential",
            model="deepseek-flash",
            base_url="https://api.deepseek.com",
            http_client=client,
            extra_body={"thinking": {"type": "disabled"}},
            max_retries=0,
        )
        bound = model.bind_tools(
            [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "offline test lookup",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]
        )
        question = HumanMessage(content="lookup")
        first = bound.invoke([question])
        final = bound.invoke(
            [question, first, ToolMessage(content="found", tool_call_id="sdk-call")]
        )
    assert final.content == "完成"
    assert requests[1]["messages"][1]["reasoning_content"] == "test provider metadata"
    assert requests[1]["messages"][1]["content"] == ""
    assert requests[0]["thinking"] == {"type": "disabled"}
