# SPDX-License-Identifier: Apache-2.0
"""Persistent blackboard event store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import append_jsonl
from ccr.paths import blackboard_events_path
from ccr.storage.sqlite import record_event
from ccr.telemetry import emit_event_span


def append_event(root: Path, event: dict[str, Any]) -> None:
    """Append an event to the runtime blackboard."""

    record_event(root, event)
    append_jsonl(blackboard_events_path(root), event)
    emit_event_span(
        f"ccr.{event.get('action', 'event')}",
        {
            "actor": str(event.get("actor", "")),
            "object_id": str(event.get("object_id", "")),
            "object_type": str(event.get("object_type", "")),
            "status_after": str(event.get("status_after", "")),
        },
    )
