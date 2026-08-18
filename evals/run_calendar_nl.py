"""Runs evals/calendar_nl.yaml against the REAL configured LLM and prints a
pass/fail report. Not part of pytest/CI on purpose -- this hits a live API
and costs tokens; run manually before merging changes to the NL parser.

Usage: uv run python evals/run_calendar_nl.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.calendar_nlp import parse_event_text  # noqa: E402


def run() -> None:
    yaml_path = Path(__file__).parent / "calendar_nl.yaml"
    data = yaml.safe_load(yaml_path.read_text())
    cases = data.get("cases", [])

    if not cases:
        print("No cases found in calendar_nl.yaml.")
        return

    passed = 0
    for i, case in enumerate(cases, start=1):
        text = case["input"]
        reference_time = datetime.fromisoformat(case["reference_time"])
        expected = case["expected"]

        result = parse_event_text(text, reference_time=reference_time)

        failures = []
        if "title_contains" in expected:
            if expected["title_contains"].lower() not in result.title.lower():
                failures.append(f"title {result.title!r} missing {expected['title_contains']!r}")
        if "start_time" in expected and result.start_time != expected["start_time"]:
            failures.append(f"start_time {result.start_time!r} != {expected['start_time']!r}")
        if "end_time" in expected and result.end_time != expected["end_time"]:
            failures.append(f"end_time {result.end_time!r} != {expected['end_time']!r}")
        if "duration_minutes" in expected and result.duration_minutes != expected["duration_minutes"]:
            failures.append(f"duration_minutes {result.duration_minutes!r} != {expected['duration_minutes']!r}")
        if "explicit_date" in expected and result.explicit_date != expected["explicit_date"]:
            failures.append(f"explicit_date {result.explicit_date!r} != {expected['explicit_date']!r}")

        if failures:
            print(f"[FAIL] case {i}: {text!r}")
            for f in failures:
                print(f"        {f}")
        else:
            print(f"[PASS] case {i}: {text!r}")
            passed += 1

    print(f"\n{passed}/{len(cases)} passed")


if __name__ == "__main__":
    run()