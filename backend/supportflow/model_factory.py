"""Provider-aware model assembly, following DeerFlow's factory/adapter separation."""

from urllib.parse import urlsplit

from langchain_core.messages import AIMessage
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI

from .config import Settings


class SupportFlowChatDeepSeek(ChatDeepSeek):
    """Replay DeepSeek assistant fields through tool and checkpoint round trips.

    Adapted from DeerFlow's patched_deepseek.py. The app keeps assistant history
    in order, so the source and serialized assistant entries have a one-to-one
    correspondence. Fail on a future provider conversion that changes that count
    instead of attaching provider metadata to the wrong message.
    """

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        assistant_messages = [message for message in messages if isinstance(message, AIMessage)]
        serialized = [message for message in payload["messages"] if message["role"] == "assistant"]
        extra_body = payload.get("extra_body") or {}
        thinking = (extra_body.get("thinking") or {}).get("type") == "enabled"
        for original, output in zip(assistant_messages, serialized, strict=True):
            reasoning = original.additional_kwargs.get("reasoning_content")
            if isinstance(reasoning, str):
                output["reasoning_content"] = reasoning
            if output.get("tool_calls"):
                if output.get("content") is None:
                    output["content"] = ""
                if thinking:
                    output.setdefault("reasoning_content", "")
        return payload


def resolve_provider(settings: Settings) -> str:
    """Detect the official endpoint by hostname, never by a model-name substring."""
    provider = settings.model_provider.strip().lower()
    if provider not in {"auto", "deepseek", "openai-compatible"}:
        raise ValueError("model provider 必须是 auto、deepseek 或 openai-compatible")
    endpoint = urlsplit(settings.base_url)
    if endpoint.scheme not in {"https", "http"} or not endpoint.hostname:
        raise ValueError("模型 base_url 必须是有效的 HTTP(S) 地址")
    if provider != "auto":
        return provider
    return "deepseek" if endpoint.hostname == "api.deepseek.com" else "openai-compatible"


def create_chat_model(settings: Settings):
    """Create one model without exposing its credential to prompts or responses."""
    if not settings.api_key.strip() or settings.api_key.startswith("your_"):
        raise ValueError("请先配置 DeepSeek 或兼容模型的密钥，或切回 demo 模式")
    provider = resolve_provider(settings)
    options = dict(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=0,
        max_tokens=2200,
        timeout=60,
        max_retries=1,
        use_responses_api=False,
    )
    if provider == "deepseek":
        # DeepSeek currently enables thinking implicitly. This application uses
        # an explicit non-thinking profile for bounded support/tool workflows.
        return SupportFlowChatDeepSeek(**options, extra_body={"thinking": {"type": "disabled"}})
    return ChatOpenAI(**options)
