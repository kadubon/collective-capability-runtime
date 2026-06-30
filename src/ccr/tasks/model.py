# SPDX-License-Identifier: Apache-2.0
"""Task model helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import json_file_name

STATUS_TO_DIR = {
    "open": "open",
    "leased": "leased",
    "submitted": "submitted",
    "blocked": "blocked",
    "verified": "verified",
    "integrated": "integrated",
    "quarantined": "quarantined",
    "rejected": "rejected",
    "expired": "expired",
}


def task_id(task: dict[str, Any]) -> str:
    """Return task id."""

    return str(task["task_id"])


def task_status(task: dict[str, Any]) -> str:
    """Return task status."""

    return str(task.get("status", "open"))


def task_path(root: Path, task_id_value: str, status: str) -> Path:
    """Return task path by status."""

    return root / "tasks" / STATUS_TO_DIR.get(status, status) / json_file_name(task_id_value)
