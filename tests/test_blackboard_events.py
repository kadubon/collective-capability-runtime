from __future__ import annotations

from ccr.blackboard.events import make_event
from ccr.blackboard.replay import read_events
from ccr.blackboard.store import append_event


def test_blackboard_event_round_trip(runtime_root):
    event = make_event(
        action="task.submit",
        object_type="task",
        object_id="task.example",
        status_before=None,
        status_after="open",
        refs=["example"],
        residuals=[],
    )
    append_event(runtime_root, event)
    events = read_events(runtime_root)
    assert events[-1]["object_id"] == "task.example"
    assert events[-1]["refs"] == ["example"]
