# SPDX-License-Identifier: Apache-2.0
"""Blackboard event records."""

from __future__ import annotations

from typing import Any

from ccr.constants import DEFAULT_ACTOR
from ccr.ids import stable_id
from ccr.time import now_iso


def make_event(
    *,
    action: str,
    object_type: str,
    object_id: str,
    actor: str = DEFAULT_ACTOR,
    status_before: str | None = None,
    status_after: str | None = None,
    refs: list[str] | None = None,
    residuals: list[str] | None = None,
    dry_run: bool = False,
    note: str = "",
) -> dict[str, Any]:
    """Build a blackboard event with the required CCR fields."""

    timestamp = now_iso()
    event_id = stable_id(
        "event", timestamp, actor, action, object_type, object_id, status_before, status_after
    )
    trace_id = stable_id("trace", event_id).split(":", 1)[1].ljust(32, "0")[:32]
    span_id = stable_id("span", event_id).split(":", 1)[1][:16]
    return {
        "action": action,
        "actor": actor,
        "dry_run": dry_run,
        "event_id": event_id,
        "id": event_id,
        "note": note,
        "object_id": object_id,
        "object_type": object_type,
        "provenance": {
            "prov:generatedAtTime": timestamp,
            "prov:wasAssociatedWith": actor,
            "refs": sorted(refs or []),
        },
        "refs": sorted(refs or []),
        "residuals": sorted(residuals or []),
        "status_after": status_after,
        "status_before": status_before,
        "source": "/ccr/runtime",
        "specversion": "1.0",
        "subject": f"{object_type}/{object_id}",
        "time": timestamp,
        "timestamp": timestamp,
        "traceparent": f"00-{trace_id}-{span_id}-01",
        "type": f"io.kadubon.ccr.{action}",
    }
