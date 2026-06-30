# SPDX-License-Identifier: Apache-2.0
"""Replay blackboard events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import read_jsonl
from ccr.paths import blackboard_events_path


def read_events(root: Path) -> list[dict[str, Any]]:
    """Read blackboard events."""

    return [event for event in read_jsonl(blackboard_events_path(root)) if isinstance(event, dict)]
