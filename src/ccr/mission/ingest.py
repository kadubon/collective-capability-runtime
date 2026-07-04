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
    MISSION_NON_CLAIMS,
    load_mission,
    load_mission_state,
    merge_state_refs,
    mission_path,
    save_mission_state,
)
from ccr.packets.store import submit_packet
from ccr.residuals.store import save_residual
from ccr.safe_io import read_text_bounded, residual_ready

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
        return _ingest_failure(
            mission_id,
            "unsupported_source_format",
            f"Unsupported mission ingest source format: {source_format}",
        )
    if not mission_path(root, mission_id).exists():
        return _ingest_failure(mission_id, "missing_mission", f"Mission not found: {mission_id}")
    mission = load_mission(root, mission_id)
    state = load_mission_state(root, mission_id)
    if not state:
        return _ingest_failure(
            mission_id,
            "missing_mission_state",
            f"Mission state not found for {mission_id}.",
        )
    read = read_text_bounded(
        input_path,
        max_bytes=MAX_INGEST_BYTES,
        source="ccr.mission.ingest",
    )
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _ingest_failure(
            mission_id,
            str(residual["extensions"]["finding_kind"]),
            str(residual["description"]),
            residual=residual,
        )
    text = str(read["text"])
    source_ref = _source_ref(input_path, display=str(read["display"]))
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
    residual_ready_count = 0
    for residual in audit.get("residual_ready", []):
        if isinstance(residual, dict):
            residual_ready_count += 1
            prepared = _mission_residual(residual, mission_id=mission_id, source_ref=source_ref)
            save_residual(root, prepared, overwrite=True)
            residual_ids.append(str(prepared["residual_id"]))
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
        "residual_ready_count": residual_ready_count,
        "residual_ids": sorted(set(residual_ids)),
        "schema_version": "ccr.mission_ingest.v1",
        "settled": False,
        "source": source_ref,
    }


def _source_ref(path: Path, *, display: str) -> str:
    size = path.stat().st_size if path.exists() else 0
    digest = stable_id("source", display, size)
    return f"{display}#{digest.rsplit(':', 1)[-1]}"


def _mission_residual(
    residual: dict[str, Any],
    *,
    mission_id: str,
    source_ref: str,
) -> dict[str, Any]:
    prepared = dict(residual)
    refs = prepared.get("refs")
    ref_set = {str(item) for item in refs} if isinstance(refs, list) else set()
    ref_set.add(source_ref)
    prepared["refs"] = sorted(ref_set)
    extensions = prepared.get("extensions")
    extension_map = dict(extensions) if isinstance(extensions, dict) else {}
    extension_map["x_ccr_mission_id"] = mission_id
    extension_map["x_ccr_source_ref"] = source_ref
    prepared["extensions"] = extension_map
    return prepared


def _ingest_failure(
    mission_id: str,
    kind: str,
    description: str,
    *,
    residual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ready = residual or residual_ready(kind, mission_id, description, "ccr.mission.ingest")
    return {
        "external_execution": False,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": False,
        "residual_ready": ready,
        "schema_version": "ccr.mission_ingest.v1",
        "settled": False,
    }
