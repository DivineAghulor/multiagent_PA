"""Typed, validated application settings, loaded from .env / the process env."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Google OAuth (Calendar sub-agent, Phase 2)
    google_client_id: str | None = Field(None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(None, alias="GOOGLE_CLIENT_SECRET")

    # Gmail (email sub-agent, later phase)
    gmail_app_password: str | None = Field(None, alias="GMAIL_APP_PASSWORD")

    # LangSmith / tracing
    langsmith_api_key: str | None = Field(None, alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field("multiagent-pa", alias="LANGSMITH_PROJECT")
    langchain_tracing_v2: bool = Field(False, alias="LANGCHAIN_TRACING_V2")


settings = Settings()
