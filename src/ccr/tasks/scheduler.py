# SPDX-License-Identifier: Apache-2.0
"""Task scheduling policy."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccr.io import read_json
from ccr.safe_io import require_path_within_root
from ccr.tasks.store import iter_tasks


def next_task(root: Path, *, role: str) -> dict[str, Any] | None:
    """Return the highest-priority open task for a role without leasing it."""

    all_tasks = iter_tasks(root)
    completed = {
        str(task.get("task_id"))
        for task in all_tasks
        if task.get("status") in {"submitted", "verified", "integrated"}
    }
    candidates = []
    for task in all_tasks:
        if task.get("role") != role or task.get("status") != "open":
            continue
        dependencies = task.get("dependencies", [])
        if isinstance(dependencies, list) and any(
            str(item) not in completed for item in dependencies
        ):
            continue
        if not _workcell_stage_active(root, task):
            continue
        candidates.append(task)
    if not candidates:
        return None
    candidates.sort(
        key=lambda task: (
            -_scheduler_score(task),
            str(task.get("created_at", "")),
            str(task.get("task_id", "")),
        )
    )
    return candidates[0]


def _scheduler_score(task: dict[str, Any]) -> float:
    score = float(task.get("priority", 50))
    created_at = _time(task.get("created_at"))
    if created_at is not None:
        age_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600)
        score += min(30.0, age_hours / 24)
    extensions = task.get("extensions")
    if not isinstance(extensions, dict):
        return score
    for key, weight in (
        ("x_blocking_fanout", 3.0),
        ("x_hazard_reduction", 4.0),
        ("x_verifiability", 2.0),
        ("x_diversity_deficit", 2.0),
    ):
        value = extensions.get(key)
        if not isinstance(value, bool) and isinstance(value, int | float) and value >= 0:
            score += min(10.0, float(value)) * weight
    cost = extensions.get("x_cost_upper_bound")
    if not isinstance(cost, bool) and isinstance(cost, int | float) and cost >= 0:
        score -= min(20.0, float(cost))
    if task.get("role") in {"verifier", "skeptic", "scheduler"}:
        score += 5.0
    return score


def _workcell_stage_active(root: Path, task: dict[str, Any]) -> bool:
    extensions = task.get("extensions")
    if not isinstance(extensions, dict):
        return True
    workcell = extensions.get("x_workcell")
    expected = extensions.get("x_workcell_stage")
    if not isinstance(workcell, str) or not isinstance(expected, str):
        return True
    path = require_path_within_root(
        root / "workcells" / workcell / "workcell.json", root, field="workcell path"
    )
    if not path.exists():
        return False
    metadata = read_json(path)
    return isinstance(metadata, dict) and metadata.get("current_stage") == expected


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
