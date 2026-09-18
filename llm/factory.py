"""LangChain chat-model factory, config-driven, no provider hardcoded in agent code."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

_SUPPORTED_PROVIDERS = {"anthropic", "google_genai", "openai", "xai"}


def _mask(key: str | None) -> str:
    """Render an API key for debug output without exposing it (see CLAUDE.md)."""
    if not key:
        return "<MISSING>"
    return f"{key[:6]}...{key[-4:]} (len={len(key)})"


def get_chat_model(provider: str, model: str, **kwargs: object) -> "BaseChatModel":
    """Return a configured BaseChatModel for the given provider.

    Args:
        provider: one of "anthropic", "google_genai", "openai", "xai".
        model: provider-specific model id (e.g. "claude-sonnet-4-5").
        **kwargs: forwarded to the underlying LangChain chat model constructor
            (temperature, max_tokens, etc).

    Raises:
        ValueError: if provider is not supported.
    """
    provider = provider.lower()

    # pydantic-settings loads .env into config.settings only — it never
    # populates os.environ, so each provider SDK's own env-var lookup
    # (ANTHROPIC_API_KEY, etc.) sees nothing unless we forward it explicitly.
    from config import settings

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs.setdefault("api_key", settings.anthropic_api_key)
        print(f"[llm.factory] provider=anthropic model={model} api_key={_mask(settings.anthropic_api_key)}")
        return ChatAnthropic(model=model, **kwargs)

    if provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs.setdefault("google_api_key", settings.google_api_key)
        print(f"[llm.factory] provider=google_genai model={model} api_key={_mask(settings.google_api_key)}")
        return ChatGoogleGenerativeAI(model=model, **kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs.setdefault("api_key", settings.openai_api_key)
        print(f"[llm.factory] provider=openai model={model} api_key={_mask(settings.openai_api_key)}")
        return ChatOpenAI(model=model, **kwargs)

    if provider == "xai":
        from langchain_xai import ChatXAI

        kwargs.setdefault("api_key", settings.xai_api_key)
        print(f"[llm.factory] provider=xai model={model} api_key={_mask(settings.xai_api_key)}")
        return ChatXAI(model=model, **kwargs)

    raise ValueError(
        f"Unsupported LLM provider: {provider!r}. Supported providers: {sorted(_SUPPORTED_PROVIDERS)}."
    )


def get_default_chat_model(**kwargs: object) -> "BaseChatModel":
    """Build a chat model from LLM_PROVIDER/LLM_MODEL in config.settings."""
    from config import settings

    return get_chat_model(settings.llm_provider, settings.llm_model, **kwargs)
