"""LangChain chat-model factory, config-driven, no provider hardcoded in agent code."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.runnables import Runnable

logger = logging.getLogger(__name__)

# Verify TLS against the OS trust store rather than certifi's bundle. Endpoint
# protection software (Avast/AVG and most corporate proxies) terminates HTTPS
# with its own root, which Windows trusts but certifi doesn't — without this,
# every provider call fails with CERTIFICATE_VERIFY_FAILED. Must run before any
# SDK builds its HTTP client, hence at import. (The older `pip-system-certs`
# does the same job but sends the OpenAI-compatible SDKs into infinite
# recursion during SSL setup; don't reintroduce it.)
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # optional: certifi's bundle is fine without TLS interception
    logger.debug("truststore not installed; using the default certificate bundle")

_SUPPORTED_PROVIDERS = {"anthropic", "google_genai", "openai", "xai", "deepseek"}


def _log_selection(provider: str, model: str, key: str | None) -> None:
    # Presence only — never log any part of the key itself (see CLAUDE.md).
    logger.debug("provider=%s model=%s api_key_set=%s", provider, model, bool(key))


def get_chat_model(provider: str, model: str, **kwargs: object) -> "BaseChatModel":
    """Return a configured BaseChatModel for the given provider.

    Args:
        provider: one of "anthropic", "google_genai", "openai", "xai", "deepseek".
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
        _log_selection("anthropic", model, settings.anthropic_api_key)
        return ChatAnthropic(model=model, **kwargs)

    if provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs.setdefault("google_api_key", settings.google_api_key)
        _log_selection("google_genai", model, settings.google_api_key)
        return ChatGoogleGenerativeAI(model=model, **kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs.setdefault("api_key", settings.openai_api_key)
        _log_selection("openai", model, settings.openai_api_key)
        return ChatOpenAI(model=model, **kwargs)

    if provider == "xai":
        from langchain_xai import ChatXAI

        kwargs.setdefault("api_key", settings.xai_api_key)
        _log_selection("xai", model, settings.xai_api_key)
        return ChatXAI(model=model, **kwargs)

    if provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        kwargs.setdefault("api_key", settings.deepseek_api_key)
        _log_selection("deepseek", model, settings.deepseek_api_key)
        return ChatDeepSeek(model=model, **kwargs)

    raise ValueError(
        f"Unsupported LLM provider: {provider!r}. Supported providers: {sorted(_SUPPORTED_PROVIDERS)}."
    )


def get_default_chat_model(**kwargs: object) -> "BaseChatModel":
    """Build a chat model from LLM_PROVIDER/LLM_MODEL in config.settings."""
    from config import settings

    return get_chat_model(settings.llm_provider, settings.llm_model, **kwargs)


# Providers whose models reject a forced tool_choice, which is what LangChain's
# default structured output relies on. DeepSeek's thinking models answer
# "Thinking mode does not support this tool_choice", so they get JSON mode plus
# the schema spelled out in the prompt (JSON mode alone doesn't show the model
# the schema, and it then invents a shape).
_JSON_MODE_PROVIDERS = {"deepseek"}

_SCHEMA_PROMPT = """Respond with a single JSON object and nothing else. It must \
validate against this JSON schema:

{schema}"""


def get_structured_model(schema: type, **kwargs: object) -> "Runnable":
    """A chat model that returns `schema` instances, by whichever mechanism the
    configured provider supports. Prefer this over calling
    `with_structured_output` directly, so agent code stays provider-agnostic."""
    import json

    from langchain_core.runnables import RunnableLambda

    from config import settings

    model = get_default_chat_model(**kwargs)
    if settings.llm_provider.lower() not in _JSON_MODE_PROVIDERS:
        return model.with_structured_output(schema)

    instructions = _SCHEMA_PROMPT.format(schema=json.dumps(schema.model_json_schema(), indent=2))
    add_schema = RunnableLambda(lambda messages: [*messages, ("system", instructions)])
    return add_schema | model.with_structured_output(schema, method="json_mode")
