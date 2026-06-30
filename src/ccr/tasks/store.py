# SPDX-License-Identifier: Apache-2.0
"""Task store operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import read_json, write_json_atomic
from ccr.schemas.validation import ValidationResult, validate_instance
from ccr.tasks.model import STATUS_TO_DIR, task_path


def validate_task(task: dict[str, Any], *, root: Path) -> ValidationResult:
    """Validate a task against the normative schema."""

    return validate_instance("task", task, root=root)


def submit_task(root: Path, task: dict[str, Any]) -> Path:
    """Store an open task."""

    status = str(task.get("status", "open"))
    destination_status = "open" if status == "open" else status
    path = task_path(root, str(task["task_id"]), destination_status)
    write_json_atomic(path, task, overwrite=False)
    return path


def find_task_path(root: Path, task_id_value: str) -> tuple[Path, str] | None:
    """Find a task by id across queues."""

    for status in STATUS_TO_DIR:
        path = task_path(root, task_id_value, status)
        if path.exists():
            return path, status
    return None


def load_task(root: Path, task_id_value: str) -> tuple[dict[str, Any], Path, str]:
    """Load a task by id."""

    found = find_task_path(root, task_id_value)
    if found is None:
        raise FileNotFoundError(task_id_value)
    path, status = found
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"task {task_id_value} is not a JSON object")
    return data, path, status


def iter_tasks(root: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    """Return tasks sorted by status path and filename."""

    statuses = [status] if status else list(STATUS_TO_DIR)
    tasks: list[dict[str, Any]] = []
    for current in statuses:
        directory = root / "tasks" / STATUS_TO_DIR.get(current, current)
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            data = read_json(path)
            if isinstance(data, dict):
                tasks.append(data)
    return tasks
