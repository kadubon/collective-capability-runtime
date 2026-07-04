# SPDX-License-Identifier: Apache-2.0
"""Mission next-action planning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.mission.model import MISSION_NON_CLAIMS, load_mission, mission_path, mission_scope
from ccr.safe_io import residual_ready


def mission_next(root: Path, *, mission_id: str, compact: bool = False) -> dict[str, Any]:
    """Return the next mission action without dispatching anything."""

    if not mission_path(root, mission_id).exists():
        residual = residual_ready(
            "missing_mission",
            mission_id,
            f"Mission not found: {mission_id}",
            "ccr.mission.next",
        )
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "network_call_performed": False,
            "non_claims": list(MISSION_NON_CLAIMS),
            "ok": False,
            "residual_ready": residual,
            "schema_version": "ccr.mission_next.compact.v1" if compact else "ccr.mission_next.v1",
            "settled": False,
        }
    mission = load_mission(root, mission_id)
    scope = mission_scope(root, mission_id)
    blocking = [item for item in scope["residuals"] if item.get("blocking")] if scope["ok"] else []
    packet_count = len(scope["packets"]) if scope["ok"] else 0
    action_kind = "repair_residual" if blocking else "ingest_or_verify_packet"
    if blocking:
        residual_id = str(blocking[0].get("residual_id", ""))
        safe_command = f"ccr residual market --mission {mission_id} --json"
        follow_up_command = (
            f"ccr residual bounty --residual {residual_id} --mission {mission_id} "
            "--emit task --json"
            if residual_id
            else ""
        )
    else:
        safe_command = f"ccr mission next --mission {mission_id} --compact --json"
        follow_up_command = ""
    if compact:
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "network_call_performed": False,
            "next_safe_action": safe_command,
            "non_claims": list(mission.get("non_claims", [])),
            "ok": bool(scope["ok"]),
            "recommended_action": {
                "external_execution": False,
                "follow_up_command": follow_up_command,
                "kind": action_kind,
                "safe_command": safe_command,
                "writes_runtime": False,
            },
            "residual_ready": scope["residual_ready"],
            "schema_version": "ccr.mission_next.compact.v1",
            "settled": False,
        }
    return {
        "advisory": {
            "blocking_residual_count": len(blocking),
            "candidate_packet_count": packet_count,
            "mode": "mission_scoped_advisory",
        },
        "external_execution": False,
        "mission_id": mission_id,
        "mode": "advisory",
        "mutated_runtime": False,
        "network_call_performed": False,
        "next_safe_action": {
            "command": safe_command,
            "external_execution": False,
            "writes_runtime": False,
        },
        "non_claims": list(mission.get("non_claims", [])),
        "ok": bool(scope["ok"]),
        "recommended_action": {
            "external_execution": False,
            "follow_up_command": follow_up_command,
            "kind": action_kind,
            "safe_command": safe_command,
            "writes_runtime": False,
        },
        "residual_ready": scope["residual_ready"],
        "schema_version": "ccr.mission_next.v1",
        "settled": False,
    }
