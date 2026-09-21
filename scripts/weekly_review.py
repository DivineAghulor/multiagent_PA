"""Generate a weekly review from the command line.

Compares the week's goals against completed tasks and habit logs, writes a
short summary with the configured model, and saves per-goal notes/status.

    uv run python scripts/weekly_review.py                 # last week
    uv run python scripts/weekly_review.py --week 2026-09-14
    uv run python scripts/weekly_review.py --no-llm        # facts only, no API call
    uv run python scripts/weekly_review.py --no-save       # don't write back
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.pm.review import (  # noqa: E402
    build_week_review,
    current_week_start,
    missed_goals,
    render_review_facts,
    save_review,
    summarize_week,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week", help="any date in the target week (YYYY-MM-DD); default: last week")
    parser.add_argument("--no-llm", action="store_true", help="print the facts only, no model call")
    parser.add_argument("--no-save", action="store_true", help="don't write notes/status back")
    args = parser.parse_args()

    if args.week:
        week_start = current_week_start(date.fromisoformat(args.week))
    else:
        week_start = current_week_start(date.today()) - timedelta(days=7)

    review = build_week_review(week_start)
    print(render_review_facts(review))

    if not review.goals:
        print("\nNo goals were set for this week, so there's nothing to review.")
        return 0

    if not args.no_llm:
        print("\n--- Summary ---")
        print(summarize_week(review))

    if args.no_save:
        print("\n(not saved: --no-save)")
    else:
        saved = save_review(review)
        print(f"\nSaved review notes and status for {len(saved)} goal(s).")

    if missed := missed_goals(review):
        print("\nMissed goals you may want to carry into next week:")
        for g in missed:
            print(f"  [{g.goal.id}] {g.goal.description}")
        print("Carry one over from the 'This week' tab, or with:")
        print("  uv run python -c \"from tools.weekly_goals import carry_over_weekly_goal;"
              " from datetime import date; carry_over_weekly_goal(<goal id>, date(YYYY, M, D))\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
