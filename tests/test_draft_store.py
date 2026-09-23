"""The in-memory draft session store (requirements §5, T-2). No DB, no model."""
from __future__ import annotations

from datetime import date

import pytest

from agents.pm.decomposition import start_new_project_draft
from api.errors import ConflictError, SessionExpiredError
from api.sessions import InMemoryDraftStore


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock() -> Clock:
    return Clock()


def test_create_get_update_delete(clock) -> None:
    store = InMemoryDraftStore(clock=clock)
    session = store.create("planning", {"turns": 0})

    assert store.get(session.id, "planning").payload == {"turns": 0}
    store.update(session.id, "planning", {"turns": 1})
    assert store.get(session.id, "planning").payload == {"turns": 1}

    store.delete(session.id)
    with pytest.raises(SessionExpiredError):
        store.get(session.id, "planning")
    store.delete(session.id)  # deleting twice is a no-op


def test_ids_are_opaque_uuids(clock) -> None:
    store = InMemoryDraftStore(clock=clock)
    a, b = store.create("planning", None), store.create("planning", None)
    assert a.id != b.id and len(a.id) == 36


def test_missing_session_is_session_expired_with_a_404(clock) -> None:
    with pytest.raises(SessionExpiredError) as info:
        InMemoryDraftStore(clock=clock).get("nope", "planning")
    assert info.value.status_code == 404
    assert info.value.type == "session_expired"


def test_a_session_of_the_other_kind_is_not_found(clock) -> None:
    store = InMemoryDraftStore(clock=clock)
    session = store.create("planning", None)
    with pytest.raises(SessionExpiredError):
        store.get(session.id, "decomposition")


def test_ttl_expiry_is_sliding(clock) -> None:
    store = InMemoryDraftStore(ttl_seconds=60, clock=clock)
    session = store.create("planning", None)

    clock.now += 50
    store.get(session.id, "planning")  # renews
    clock.now += 50
    assert store.get(session.id, "planning")  # 100s old but used 50s ago

    clock.now += 61
    with pytest.raises(SessionExpiredError):
        store.get(session.id, "planning")


def test_a_session_mid_turn_does_not_expire(clock) -> None:
    store = InMemoryDraftStore(ttl_seconds=60, clock=clock)
    session = store.create("decomposition", None)

    with store.exclusive(session):
        clock.now += 600  # a very slow turn
        assert len(store) == 1
    clock.now += 59  # the TTL restarted when the turn ended
    assert store.get(session.id, "decomposition")


def test_cap_evicts_the_least_recently_used_idle_session(clock) -> None:
    store = InMemoryDraftStore(max_sessions=2, clock=clock)
    old = store.create("planning", "old")
    clock.now += 1
    newer = store.create("planning", "newer")
    clock.now += 1
    store.get(old.id, "planning")  # old is now the most recently used
    clock.now += 1

    store.create("planning", "third")

    assert len(store) == 2
    assert store.get(old.id, "planning").payload == "old"
    with pytest.raises(SessionExpiredError):
        store.get(newer.id, "planning")


def test_cap_never_evicts_a_busy_session(clock) -> None:
    store = InMemoryDraftStore(max_sessions=1, clock=clock)
    busy = store.create("planning", None)
    with store.exclusive(busy):
        with pytest.raises(ConflictError):
            store.create("planning", None)
    assert store.get(busy.id, "planning")


def test_exclusive_rejects_a_second_holder(clock) -> None:
    store = InMemoryDraftStore(clock=clock)
    session = store.create("planning", None)
    with store.exclusive(session):
        with pytest.raises(ConflictError) as info:
            with store.exclusive(session):
                pass
        assert info.value.status_code == 409
    with store.exclusive(session):  # released again afterwards
        pass


def test_decomposition_refs_stay_stable_across_turns(clock) -> None:
    """The draft is kept as a live object, so the M/T refs the model names in
    its next tool call still point at the same items (S-2)."""
    store = InMemoryDraftStore(clock=clock)
    draft = start_new_project_draft("Podcast")
    milestone = draft.add_milestone("Pilot recorded", None, None, date(2026, 9, 18))
    draft.add_task(milestone.ref, "Buy a microphone", None)
    session = store.create("decomposition", draft)

    later = store.get(session.id, "decomposition").payload
    later.add_task("M1", "Record episode 1", None)

    again = store.get(session.id, "decomposition").payload
    assert [(t.ref, t.title) for t in again.milestones[0].tasks] == [
        ("T2", "Buy a microphone"),
        ("T3", "Record episode 1"),
    ]
