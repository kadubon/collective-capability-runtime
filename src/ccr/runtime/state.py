# SPDX-License-Identifier: Apache-2.0
"""Runtime state inspection."""

from __future__ import annotations

from pathlib import Path

from ccr.constants import PACKET_STATUSES, RESIDUAL_STATUSES, TASK_STATUSES


def count_json_files(path: Path) -> int:
    """Count JSON files in a directory."""

    if not path.exists():
        return 0
    return sum(1 for item in path.glob("*.json") if item.is_file())


def packet_counts(root: Path) -> dict[str, int]:
    """Return packet counts by status."""

    return {status: count_json_files(root / "packets" / status) for status in PACKET_STATUSES}


def task_counts(root: Path) -> dict[str, int]:
    """Return task counts by status."""

    return {status: count_json_files(root / "tasks" / status) for status in TASK_STATUSES}


def residual_counts(root: Path) -> dict[str, int]:
    """Return residual counts by status."""

    return {status: count_json_files(root / "residuals" / status) for status in RESIDUAL_STATUSES}
