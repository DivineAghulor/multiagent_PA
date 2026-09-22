"""FastAPI application for the web app.

Run it with:  uv run uvicorn api.main:app --reload

There is no authentication: v1 is explicitly single-user and the boundary is
deployment, not code. The app binds to a loopback address by default and CORS
admits exactly one origin — an unauthenticated instance on a public URL would
expose the whole database and burn the provider key by request
(docs/webapp-requirements.md §9).
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from api.deps import server_today
from api.errors import register_error_handlers
from api.routers import habits, planning, projects, tasks, weeks
from api.schemas import HealthOut
from config import settings
from db.session import get_session
from llm.factory import provider_key_configured

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Personal Assistant API",
    version="0.1.0",
    description="HTTP boundary over the PM sub-agent and its tools.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,  # nothing is authenticated; no cookies to send
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

for module in (tasks, projects, habits, weeks, planning):
    app.include_router(module.router)


def _database_reachable() -> bool:
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 — the reason is logged; the client gets a bool
        logger.exception("health check: database unreachable")
        return False


@app.get("/api/health", response_model=HealthOut, tags=["health"])
def health() -> HealthOut:
    """Whether the app can work right now, and how degraded it is if not.

    A missing provider key is reported as `provider_key_configured: false` so
    the UI can disable the model-backed actions while leaving the rest usable
    (NFR-8). The key itself is never read here — only its presence.
    """
    database = _database_reachable()
    key = provider_key_configured()
    return HealthOut(
        status="ok" if database and key else "degraded",
        database=database,
        provider=settings.llm_provider,
        model=settings.llm_model,
        provider_key_configured=key,
        tracing=settings.langchain_tracing_v2,
        today=server_today(),
    )
