# SPDX-License-Identifier: Apache-2.0
"""Mission next-action planning."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.extensions import loop_next
from ccr.mission.model import load_mission, mission_path


def mission_next(root: Path, *, mission_id: str, compact: bool = False) -> dict[str, Any]:
    """Return the next mission action without dispatching anything."""

    if not mission_path(root, mission_id).exists():
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
            "schema_version": "ccr.mission_next.compact.v1" if compact else "ccr.mission_next.v1",
            "settled": False,
        }
    mission = load_mission(root, mission_id)
    advisory = loop_next(root, compact=compact)
    safe_command = f"ccr mission next --mission {mission_id} --compact --json"
    if compact:
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "next_safe_action": safe_command,
            "non_claims": list(mission.get("non_claims", [])),
            "ok": bool(advisory.get("ok", True)),
            "recommended_action": {
                "external_execution": False,
                "kind": advisory.get("recommended_action", {}).get("kind", "advisory")
                if isinstance(advisory.get("recommended_action"), dict)
                else "advisory",
                "safe_command": safe_command,
                "writes_runtime": False,
            },
            "schema_version": "ccr.mission_next.compact.v1",
            "settled": False,
        }
    return {
        "advisory": advisory,
        "external_execution": False,
        "mission_id": mission_id,
        "mode": "advisory",
        "mutated_runtime": False,
        "next_safe_action": {
            "command": safe_command,
            "external_execution": False,
            "writes_runtime": False,
        },
        "non_claims": list(mission.get("non_claims", [])),
        "ok": bool(advisory.get("ok", True)),
        "schema_version": "ccr.mission_next.v1",
        "settled": False,
    }
