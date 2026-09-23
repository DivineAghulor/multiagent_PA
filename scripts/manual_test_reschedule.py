"""Manual, one-off verification of the Phase 4 reschedule confirmation flow.
Not a pytest test -- run directly to watch each stage happen for real against
your local DB. Safe to run repeatedly; creates one throwaway local-only event
each time (no Google sync, so it won't touch your real calendar).

Usage: uv run python scripts/manual_test_reschedule.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta, timezone

from agents.reschedule_graph import resume_reschedule_decision, start_reschedule_proposal
from tools.calendar import create_event, get_event

# 1. Create a fresh local-only test event (no Google push, keeps this simple)
start = datetime.now(timezone.utc) + timedelta(days=1)
end = start + timedelta(hours=1)
event = create_event(title="Manual reschedule test", start_time=start, end_time=end)
print(f"1. Created event id={event.id}, start={event.start_time}, end={event.end_time}")

# 2. Propose a reschedule -- this PAUSES at the interrupt() call and returns
#    the proposal payload, exactly like it would hand off to a real UI.
new_start = start + timedelta(hours=3)
new_end = end + timedelta(hours=3)
thread_id = f"manual-test-{event.id}"

proposal = start_reschedule_proposal(
    event_id=event.id,
    new_start_time=new_start,
    new_end_time=new_end,
    reason="testing the interrupt flow",
    thread_id=thread_id,
)
print(f"2. Graph paused. Proposal payload surfaced to the 'human': {proposal}")

# 3. Simulate a human approving the change, then resume the graph.
result = resume_reschedule_decision(thread_id, approved=True)
print(f"3. Resumed with approval. Final result: {result}")

# 4. Confirm the DB actually reflects the change.
final_event = get_event(event.id)
print(f"4. DB check -- status={final_event.status}, start={final_event.start_time}")

# --- Scenario 2: test the REJECT path ---
start2 = datetime.now(timezone.utc) + timedelta(days=2)
end2 = start2 + timedelta(hours=1)
event2 = create_event(title="Manual reschedule test (reject scenario)", start_time=start2, end_time=end2)
print(f"\n5. Created second event id={event2.id}, start={event2.start_time}")

new_start2 = start2 + timedelta(hours=5)
new_end2 = end2 + timedelta(hours=5)
thread_id2 = f"manual-test-reject-{event2.id}"

proposal2 = start_reschedule_proposal(
    event_id=event2.id,
    new_start_time=new_start2,
    new_end_time=new_end2,
    reason="testing the reject path",
    thread_id=thread_id2,
)
print(f"6. Graph paused. Proposal: {proposal2}")

result2 = resume_reschedule_decision(thread_id2, approved=False)
print(f"7. Resumed with REJECTION. Final result: {result2}")

final_event2 = get_event(event2.id)
print(f"8. DB check -- status={final_event2.status}, start={final_event2.start_time} (should match ORIGINAL start: {start2})")