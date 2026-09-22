"""Typed, validated application settings, loaded from .env / the process env."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file, not the CWD: a relative ".env" silently resolves to
# nothing when the process is launched from another directory, which makes
# every setting fall back to its default (e.g. llm_provider -> "anthropic"
# with no key) and surfaces as a confusing auth error rather than a missing
# config error.
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Database — default matches the local dev convention (personal_assistant_dev)
    # using the default postgres role; override in .env if yours differ.
    database_url: str = Field(
        "postgresql+psycopg://postgres:postgres@localhost:5432/personal_assistant_dev",
        alias="DATABASE_URL",
    )

    # LLM provider selection (consumed by llm/factory.py)
    llm_provider: str = Field("anthropic", alias="LLM_PROVIDER")
    llm_model: str = Field("claude-sonnet-4-5", alias="LLM_MODEL")

    # Provider API keys — optional here; llm/factory.py raises its own clear
    # error if the *selected* provider's key is missing.
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    google_api_key: str | None = Field(None, alias="GOOGLE_API_KEY")
    openai_api_key: str | None = Field(None, alias="OPENAI_API_KEY")
    xai_api_key: str | None = Field(None, alias="XAI_API_KEY")
    deepseek_api_key: str | None = Field(None, alias="DEEPSEEK_API_KEY")

    # Google OAuth (Calendar sub-agent, Phase 2)
    google_client_id: str | None = Field(None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(None, alias="GOOGLE_CLIENT_SECRET")

    # Gmail (email sub-agent, later phase)
    gmail_app_password: str | None = Field(None, alias="GMAIL_APP_PASSWORD")

    # Web app (api/) — the backend binds to localhost by default and allows a
    # single frontend origin. Exposing it on a non-local interface without auth
    # would expose the whole DB and the provider key by request; see
    # docs/webapp-requirements.md SEC-1/SEC-2 before changing these.
    api_host: str = Field("127.0.0.1", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    web_origin: str = Field("http://localhost:3000", alias="WEB_ORIGIN")

    # LangSmith / tracing
    langsmith_api_key: str | None = Field(None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field("multiagent-pa", alias="LANGSMITH_PROJECT")
    langchain_tracing_v2: bool = Field(False, alias="LANGCHAIN_TRACING_V2")


settings = Settings()
