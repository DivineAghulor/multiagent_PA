"""The draft session store: conversational state that isn't in the database
until the user confirms (requirements §5).

A planning conversation holds its history and latest proposal; a
decomposition holds a live `DecompositionDraft` (whose M1/T3 refs must stay
stable across turns) and a LangChain message history with tool traffic.
HTTP has nowhere to keep either, so the backend does.

v1 keeps them in this process's memory (S-2): the app is single-user and
single-process, and live objects need no serialisation layer to get wrong.
The cost is deliberate and surfaced in the UI (S-3): **a backend restart loses
every unconfirmed draft**, and the next request for one gets
`session_expired`. Persisting drafts is a v2 question (S-4); see NOTES.md.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from api.errors import ConflictError, SessionExpiredError

DEFAULT_TTL_SECONDS = 12 * 60 * 60  # idle time before a draft is dropped
DEFAULT_MAX_SESSIONS = 20


@dataclass
class DraftSession:
    id: str
    kind: str  # "planning" | "decomposition"
    payload: Any
    last_used: float
    # Held for the length of a model turn or a confirm, so two tabs can't run
    # turns on one draft at once or confirm it mid-turn.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def busy(self) -> bool:
        return self.lock.locked()


class DraftStore(Protocol):
    def create(self, kind: str, payload: Any) -> DraftSession: ...

    def get(self, session_id: str, kind: str) -> DraftSession:
        """The live session, or SessionExpiredError. Refreshes its TTL."""
        ...

    def update(self, session_id: str, kind: str, payload: Any) -> DraftSession: ...

    def delete(self, session_id: str) -> None:
        """Remove a session; a no-op if it's already gone."""
        ...

    def exclusive(self, session: DraftSession) -> AbstractContextManager[DraftSession]:
        """Hold a session for a turn or a confirm; 409 if something else holds it."""
        ...


class InMemoryDraftStore:
    """DraftStore over a dict. TTL is sliding (every get renews it); when the
    cap is reached, the least recently used idle session is evicted to make
    room — for one user, the oldest abandoned draft is the right one to lose."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._clock = clock
        self._sessions: dict[str, DraftSession] = {}
        self._guard = threading.Lock()

    def __len__(self) -> int:
        with self._guard:
            self._sweep()
            return len(self._sessions)

    def _sweep(self) -> None:
        now = self._clock()
        for sid, s in list(self._sessions.items()):
            # A session mid-turn is in use however long the turn takes.
            if not s.busy and now - s.last_used > self._ttl:
                del self._sessions[sid]

    def create(self, kind: str, payload: Any) -> DraftSession:
        with self._guard:
            self._sweep()
            if len(self._sessions) >= self._max:
                idle = [s for s in self._sessions.values() if not s.busy]
                if not idle:
                    raise ConflictError("Too many drafts are mid-turn; wait for one to finish.")
                del self._sessions[min(idle, key=lambda s: s.last_used).id]
            session = DraftSession(str(uuid.uuid4()), kind, payload, self._clock())
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str, kind: str) -> DraftSession:
        with self._guard:
            self._sweep()
            session = self._sessions.get(session_id)
            # A session of the other kind is as good as missing: its payload
            # is a different shape.
            if session is None or session.kind != kind:
                raise SessionExpiredError(session_id)
            session.last_used = self._clock()
            return session

    def update(self, session_id: str, kind: str, payload: Any) -> DraftSession:
        session = self.get(session_id, kind)
        session.payload = payload
        return session

    def delete(self, session_id: str) -> None:
        with self._guard:
            self._sessions.pop(session_id, None)

    @contextmanager
    def exclusive(self, session: DraftSession) -> Iterator[DraftSession]:
        if not session.lock.acquire(blocking=False):
            raise ConflictError("This draft is busy with another request. Wait for it to finish.")
        try:
            yield session
        finally:
            # A long turn counts as use: the TTL restarts when it ends, not
            # when it began.
            session.last_used = self._clock()
            session.lock.release()


_store: DraftStore = InMemoryDraftStore()


def get_draft_store() -> DraftStore:
    """FastAPI dependency; tests override it with a fresh store."""
    return _store
