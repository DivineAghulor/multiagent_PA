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
        hints = [(t.project_hint or "").lower() for t in batch.tasks]
        missing_hints = [
            h for h in case.get("expected_project_hints", [])
            if not any(h.lower() in got_hint for got_hint in hints)
        ]
        ok = got == expected and not missing_hints
        if not ok:
            failures += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {case['input']!r} -> {got} task(s) (expected {expected})")
        if missing_hints:
            print(f"         missing project_hint(s): {missing_hints}")
        for t in batch.tasks:
            print(f"         - {t.title!r} (project_hint={t.project_hint!r})")

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
