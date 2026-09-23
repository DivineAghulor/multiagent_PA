"""Shared pytest fixtures. Tools go through db.session.get_session(), so
tests redirect it at an isolated in-memory SQLite DB instead of hitting the
local Postgres dev DB — keeps unit tests fast and independent of local setup."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import db.session
from db.models import Base


@pytest.fixture()
def db_session(monkeypatch: pytest.MonkeyPatch):
    # StaticPool + check_same_thread=False: an in-memory SQLite DB lives in its
    # connection, so every thread must share one. Streamlit's AppTest runs the
    # app script off the main thread, which otherwise can't see these tables.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_local = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
    )
    monkeypatch.setattr(db.session, "SessionLocal", test_session_local)
    yield test_session_local
    Base.metadata.drop_all(engine)
    engine.dispose()
