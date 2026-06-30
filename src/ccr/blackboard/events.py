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
    return {
        "action": action,
        "actor": actor,
        "dry_run": dry_run,
        "event_id": event_id,
        "note": note,
        "object_id": object_id,
        "object_type": object_type,
        "refs": sorted(refs or []),
        "residuals": sorted(residuals or []),
        "status_after": status_after,
        "status_before": status_before,
        "timestamp": timestamp,
    }
