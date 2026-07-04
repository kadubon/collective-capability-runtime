# SPDX-License-Identifier: Apache-2.0
"""Mission status reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.mission.model import load_mission, load_mission_state, mission_path
from ccr.runtime.state import packet_counts, residual_counts, task_counts


def mission_status(root: Path, *, mission_id: str) -> dict[str, Any]:
    """Return mission status without mutating runtime."""

    path = mission_path(root, mission_id)
    if not path.exists():
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "ok": False,
            "residual_ready": {
                "blocking": True,
                "description": f"Mission not found: {mission_id}",
                "kind": "missing_mission",
            },
            "schema_version": "ccr.mission_status.v1",
            "settled": False,
        }
    mission = load_mission(root, mission_id)
    state = load_mission_state(root, mission_id)
    return {
        "baseline_ref": mission.get("baseline_ref"),
        "external_execution": False,
        "mission": mission,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "ok": True,
        "packet_counts": packet_counts(root),
        "profile": mission.get("profile"),
        "residual_counts": residual_counts(root),
        "schema_version": "ccr.mission_status.v1",
        "settled": False,
        "state": state,
        "target_ref": mission.get("asi_proxy_target_ref"),
        "task_counts": task_counts(root),
    }
