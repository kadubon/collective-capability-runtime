# SPDX-License-Identifier: Apache-2.0
"""Persistent blackboard event store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import append_jsonl
from ccr.paths import blackboard_events_path


def append_event(root: Path, event: dict[str, Any]) -> None:
    """Append an event to the runtime blackboard."""

    append_jsonl(blackboard_events_path(root), event)
