# SPDX-License-Identifier: Apache-2.0
"""Mission-local ingest helpers."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.claims.audit import audit_claims
from ccr.claims.extract import extract_claims_from_text
from ccr.extensions import make_packet
from ccr.ids import stable_id
from ccr.io import write_json_atomic
from ccr.mission.model import (
    load_mission,
    load_mission_state,
    merge_state_refs,
    mission_path,
    save_mission_state,
)
from ccr.packets.store import submit_packet
from ccr.residuals.store import save_residual

MAX_INGEST_BYTES = 1_000_000
MAX_INGESTED_CLAIMS = 10


def ingest_mission(
    root: Path,
    *,
    mission_id: str,
    source_format: str,
    input_path: Path,
) -> dict[str, Any]:
    """Ingest a local document into mission candidate packet work."""

    if source_format != "markdown":
        raise ValueError("only markdown mission ingest is supported")
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
            "schema_version": "ccr.mission_ingest.v1",
            "settled": False,
        }
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if input_path.stat().st_size > MAX_INGEST_BYTES:
        return {
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "ok": False,
            "residual_ready": {
                "blocking": True,
                "description": "Mission ingest input exceeds local size bound.",
                "kind": "input_too_large",
            },
            "schema_version": "ccr.mission_ingest.v1",
            "settled": False,
        }
    mission = load_mission(root, mission_id)
    text = input_path.read_text(encoding="utf-8")
    source_ref = _source_ref(input_path)
    claims = extract_claims_from_text(text, source=source_ref)["claims"]
    audit = audit_claims(claims, source=source_ref, fail_on=[])
    packet_ids: list[str] = []
    packet_paths: list[str] = []
    for claim in claims[:MAX_INGESTED_CLAIMS]:
        packet_id = stable_id("packet:mission", mission_id, claim["claim_id"])
        packet = make_packet(
            packet_id=packet_id,
            summary=f"Mission candidate from {source_ref}.",
            claim_text=str(claim["text"]),
            packet_type="claim",
        )
        packet.setdefault("extensions", {})
        packet["extensions"].update(
            {
                "x_ccr_claim_id": claim["claim_id"],
                "x_ccr_mission_id": mission_id,
                "x_source_line": claim.get("line"),
            }
        )
        packet["provenance"]["source_refs"] = [source_ref]
        with suppress(FileExistsError):
            packet_paths.append(str(submit_packet(root, packet)))
        packet_ids.append(packet_id)
    residual_ids: list[str] = []
    for residual in audit.get("residual_ready", []):
        if isinstance(residual, dict) and residual.get("blocking"):
            save_residual(root, residual, overwrite=True)
            residual_ids.append(str(residual["residual_id"]))
    state = load_mission_state(root, mission_id)
    if state:
        state = merge_state_refs(state, packet_refs=packet_ids, residual_refs=residual_ids)
        save_mission_state(root, state)
    append_event(
        root,
        make_event(
            action="mission.ingest",
            object_type="runtime",
            object_id=mission_id,
            status_before=None,
            status_after="candidate_packets",
            refs=[source_ref, *packet_paths],
            residuals=residual_ids,
            note="Mission ingest creates local candidate packets only.",
        ),
    )
    workspace = mission.get("packet_workspace")
    if isinstance(workspace, dict):
        workspace["candidate_refs"] = sorted(
            set([*workspace.get("candidate_refs", []), *packet_ids])
        )
        workspace["packet_refs"] = sorted(set([*workspace.get("packet_refs", []), *packet_ids]))
        write_json_atomic(mission_path(root, mission_id), mission, overwrite=True)
    return {
        "claim_count": len(claims),
        "external_execution": False,
        "ingested_packet_ids": sorted(set(packet_ids)),
        "mission_id": mission_id,
        "mutated_runtime": True,
        "network_call_performed": False,
        "ok": True,
        "overclaim_count": audit.get("overclaim_count", 0),
        "residual_ids": sorted(set(residual_ids)),
        "schema_version": "ccr.mission_ingest.v1",
        "settled": False,
        "source": source_ref,
    }


def _source_ref(path: Path) -> str:
    digest = stable_id("source", path.name, path.stat().st_size)
    return f"{path.name}#{digest.rsplit(':', 1)[-1]}"
