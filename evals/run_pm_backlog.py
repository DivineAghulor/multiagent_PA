"""Run evals/pm_backlog.yaml against the real configured LLM provider.

Behavior check, not a unit test — hits a live API. Run manually:
    uv run python evals/run_pm_backlog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.pm.extraction import extract_tasks  # noqa: E402


def main() -> int:
    cases = yaml.safe_load(Path(__file__).with_name("pm_backlog.yaml").read_text())["cases"]
    failures = 0
    for case in cases:
        batch = extract_tasks(case["input"])
        got = len(batch.tasks)
        expected = case["expected_task_count"]
        status = "PASS" if got == expected else "FAIL"
        if got != expected:
            failures += 1
        print(f"[{status}] {case['input']!r} -> {got} task(s) (expected {expected})")
        for t in batch.tasks:
            print(f"         - {t.title!r} (project_hint={t.project_hint!r})")

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
