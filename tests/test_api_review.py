"""W4's week review and carry-over over HTTP. summarize_week (the one model
call) is mocked at the router; everything else runs for real."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.models import WeeklyGoalStatus
from tools.reviews import get_week_summary
from tools.tasks import complete_task, create_task, get_task
from tools.weekly_goals import create_weekly_goal, get_weekly_goal, list_weekly_goals

MONDAY = date(2026, 9, 14)
NEXT_MONDAY = date(2026, 9, 21)


@pytest.fixture()
def client(db_session, monkeypatch):
    import api.deps
    import llm.factory

    monkeypatch.setattr(api.deps, "today", lambda: date(2026, 9, 20))
    monkeypatch.setattr(llm.factory, "provider_key_configured", lambda provider=None: True)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def week(db_session):
    """One achieved goal, one missed goal, one unplanned completion."""
    done = create_task("Write copy")
    open_ = create_task("Pick photos")
    stray = create_task("Answer email")
    achieved = create_weekly_goal(MONDAY, "Ship the copy", task_ids=[done.id])
    missed = create_weekly_goal(MONDAY, "Choose imagery", task_ids=[open_.id])
    complete_task(done.id, completed_at=datetime(2026, 9, 15, tzinfo=timezone.utc))
    complete_task(stray.id, completed_at=datetime(2026, 9, 16, tzinfo=timezone.utc))
    return {"achieved": achieved, "missed": missed, "open": open_}


def error_of(response) -> tuple[str, str]:
    body = response.json()["error"]
    return body["type"], body["message"]


def test_drafting_a_review_calls_the_model_over_the_facts_and_writes_nothing(client, week, monkeypatch) -> None:
    import api.routers.weeks

    seen = {}

    def fake_summarize(review):
        seen["goals"] = [g.goal.description for g in review.goals]
        return "A decent week."

    monkeypatch.setattr(api.routers.weeks, "summarize_week", fake_summarize)

    response = client.post(f"/api/weeks/{MONDAY.isoformat()}/review/draft")

    assert response.json() == {"summary": "A decent week."}
    assert seen["goals"] == ["Ship the copy", "Choose imagery"]
    assert get_week_summary(MONDAY) is None
    assert all(g.reviewed_at is None for g in list_weekly_goals(week_start=MONDAY))


def test_a_provider_failure_while_drafting_is_typed(client, week, monkeypatch) -> None:
    import api.routers.weeks

    monkeypatch.setattr(api.routers.weeks, "summarize_week", lambda review: (_ for _ in ()).throw(TimeoutError("slow")))

    response = client.post(f"/api/weeks/{MONDAY.isoformat()}/review/draft")

    assert response.status_code == 502
    assert error_of(response)[0] == "provider"


def test_saving_stores_verdicts_and_the_narrative_with_its_counts(client, week) -> None:
    body = client.post(f"/api/weeks/{MONDAY.isoformat()}/review", json={"summary": "A decent week."}).json()

    assert body["review"]["summary"] == "A decent week."
    assert (body["review"]["achieved_count"], body["review"]["measurable_count"], body["review"]["unplanned_count"]) == (1, 2, 1)
    assert get_weekly_goal(week["achieved"].id).status == WeeklyGoalStatus.ACHIEVED
    assert get_weekly_goal(week["missed"].id).status == WeeklyGoalStatus.MISSED
    assert "Outstanding: Pick photos" in get_weekly_goal(week["missed"].id).review_notes


def test_saving_without_prose_records_verdicts_only(client, week) -> None:
    body = client.post(f"/api/weeks/{MONDAY.isoformat()}/review", json={"summary": None}).json()

    assert body["review"] is None
    assert get_weekly_goal(week["achieved"].id).reviewed_at is not None


def test_re_saving_overwrites_the_week(client, week) -> None:
    client.post(f"/api/weeks/{MONDAY.isoformat()}/review", json={"summary": "First."})
    body = client.post(f"/api/weeks/{MONDAY.isoformat()}/review", json={"summary": "Second."}).json()

    assert body["review"]["summary"] == "Second."
    assert len(client.get("/api/reviews").json()) == 1


def test_blank_prose_is_rejected(client, week) -> None:
    response = client.post(f"/api/weeks/{MONDAY.isoformat()}/review", json={"summary": "   "})
    assert response.status_code == 400
    assert get_week_summary(MONDAY) is None


def test_review_endpoints_require_a_monday(client) -> None:
    assert client.post("/api/weeks/2026-09-15/review/draft").status_code == 400
    assert client.post("/api/weeks/2026-09-15/review", json={}).status_code == 400


def test_carry_over_moves_unfinished_tasks_into_the_later_week(client, week) -> None:
    response = client.post(
        f"/api/weekly-goals/{week['missed'].id}/carry-over", json={"new_week_start": NEXT_MONDAY.isoformat()}
    )

    assert response.status_code == 200
    carried = response.json()
    assert (carried["week_start"], carried["description"]) == (NEXT_MONDAY.isoformat(), "Choose imagery")
    assert get_task(week["open"].id).weekly_goal_id == carried["id"]
    assert get_weekly_goal(week["missed"].id).status == WeeklyGoalStatus.CARRIED_OVER


@pytest.mark.parametrize("target", ["2026-09-22", "2026-09-07"])  # not a Monday; not later
def test_carry_over_rejects_a_bad_target_week(client, week, target) -> None:
    response = client.post(f"/api/weekly-goals/{week['missed'].id}/carry-over", json={"new_week_start": target})
    assert response.status_code == 400


def test_carry_over_of_a_missing_goal_is_a_404(client) -> None:
    response = client.post("/api/weekly-goals/999/carry-over", json={"new_week_start": NEXT_MONDAY.isoformat()})
    assert response.status_code == 404
