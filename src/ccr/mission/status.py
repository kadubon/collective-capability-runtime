# SPDX-License-Identifier: Apache-2.0
"""Mission status reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.mission.model import (
    MISSION_NON_CLAIMS,
    load_mission,
    mission_packet_counts,
    mission_path,
    mission_residual_counts,
    mission_scope,
)
from ccr.runtime.state import task_counts
from ccr.safe_io import residual_ready


def mission_status(root: Path, *, mission_id: str) -> dict[str, Any]:
    """Return mission status without mutating runtime."""

    path = mission_path(root, mission_id)
    if not path.exists():
        residual = residual_ready(
            "missing_mission",
            mission_id,
            f"Mission not found: {mission_id}",
            "ccr.mission.status",
        )
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "network_call_performed": False,
            "non_claims": list(MISSION_NON_CLAIMS),
            "ok": False,
            "residual_ready": residual,
            "schema_version": "ccr.mission_status.v1",
            "settled": False,
        }
    mission = load_mission(root, mission_id)
    scope = mission_scope(root, mission_id)
    residuals = scope["residuals"] if scope["ok"] else []
    packets = scope["packets"] if scope["ok"] else []
    return {
        "baseline_ref": mission.get("baseline_ref"),
        "external_execution": False,
        "mission": mission,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(mission.get("non_claims", MISSION_NON_CLAIMS)),
        "ok": bool(scope["ok"]),
        "packet_counts": mission_packet_counts(packets),
        "profile": mission.get("profile"),
        "residual_counts": mission_residual_counts(residuals),
        "residual_ready": scope["residual_ready"],
        "runtime_task_counts": task_counts(root),
        "schema_version": "ccr.mission_status.v1",
        "settled": False,
        "state": scope["state"],
        "target_ref": mission.get("asi_proxy_target_ref"),
        "mission_task_counts": {},
    }
