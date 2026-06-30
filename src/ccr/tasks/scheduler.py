# SPDX-License-Identifier: Apache-2.0
"""Task scheduling policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.tasks.store import iter_tasks


def next_task(root: Path, *, role: str) -> dict[str, Any] | None:
    """Return the highest-priority open task for a role without leasing it."""

    candidates = [
        task
        for task in iter_tasks(root, status="open")
        if task.get("role") == role and task.get("status") == "open"
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda task: (
            -int(task.get("priority", 50)),
            str(task.get("created_at", "")),
            str(task.get("task_id", "")),
        )
    )
    return candidates[0]
