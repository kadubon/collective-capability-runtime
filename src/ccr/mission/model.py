# SPDX-License-Identifier: Apache-2.0
"""Mission artifact model helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccr.constants import NON_CLAIMS
from ccr.io import json_file_name, read_json, write_json_atomic
from ccr.packets.store import iter_packets
from ccr.residuals.store import iter_residuals
from ccr.safe_io import require_path_within_root, residual_ready

FIXED_CREATED_AT = "1970-01-01T00:00:00Z"
MISSION_NON_CLAIMS = (
    "not_real_asi_proof",
    "not_execution_authority",
    "not_physical_outcome_proof",
    "provider_output_is_evidence_only",
    "pic_output_is_evidence_only",
)


def mission_id_from_name(name: str) -> str:
    """Return a stable mission id from a user-facing name."""

    raw = name.strip()
    if raw.startswith("mission:"):
        return raw
    slug = re.sub(r"[^A-Za-z0-9_.@+-]+", "-", raw).strip("-").lower()
    if not slug:
        slug = "default"
    return f"mission:{slug}"


def mission_name(mission_id: str) -> str:
    """Return the local mission name portion."""

    return mission_id.split(":", 1)[1] if mission_id.startswith("mission:") else mission_id


def mission_root(root: Path) -> Path:
    """Return the mission artifact root."""

    return root / "missions"


def mission_path(root: Path, mission_id: str) -> Path:
    """Return the mission artifact path."""

    return require_path_within_root(
        mission_root(root) / json_file_name(mission_id), root, field="mission path"
    )


def mission_state_path(root: Path, mission_id: str) -> Path:
    """Return the mission state artifact path."""

    return require_path_within_root(
        mission_root(root) / "state" / json_file_name(mission_id),
        root,
        field="mission state path",
    )


def target_path(root: Path, target_id: str) -> Path:
    """Return the mission target artifact path."""

    return require_path_within_root(
        mission_root(root) / "targets" / json_file_name(target_id),
        root,
        field="mission target path",
    )


def baseline_path(root: Path, baseline_id: str) -> Path:
    """Return the mission baseline artifact path."""

    return require_path_within_root(
        mission_root(root) / "baselines" / json_file_name(baseline_id),
        root,
        field="mission baseline path",
    )


def load_mission(root: Path, mission_id: str) -> dict[str, Any]:
    """Load a mission artifact."""

    data = read_json(mission_path(root, mission_id))
    if not isinstance(data, dict):
        raise ValueError(f"mission {mission_id} is not a JSON object")
    return data


def load_mission_state(root: Path, mission_id: str) -> dict[str, Any]:
    """Load a mission state artifact if present."""

    path = mission_state_path(root, mission_id)
    if not path.exists():
        return {}
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"mission state {mission_id} is not a JSON object")
    return data


def save_mission_state(root: Path, state: dict[str, Any]) -> Path:
    """Persist a mission state artifact."""

    return write_state(root, state)


def write_state(root: Path, state: dict[str, Any]) -> Path:
    """Persist a mission state artifact."""

    path = mission_state_path(root, str(state["mission_id"]))
    write_json_atomic(path, state, overwrite=True)
    return path


def build_target_fixture(mission_id: str, *, profile: str) -> dict[str, Any]:
    """Build a local ASI-proxy target fixture."""

    name = mission_name(mission_id)
    target_id = f"target:{name}"
    baseline_id = f"baseline:{name}"
    return {
        "authority_envelope": {"scope": "local_dry_run", "status": "approved"},
        "baseline_upper_envelope_ref": baseline_id,
        "capability_basis": ["local_packet_work", "residual_reduction"],
        "capability_envelope": {"status": "accepted"},
        "externality_law": {"status": "accepted"},
        "generated_law": {"status": "accepted"},
        "hazard_envelope": {"status": "accepted", "unknowns_block": True},
        "horizon": "P1D",
        "mission_law": {"status": "accepted"},
        "non_claims": [*list(NON_CLAIMS), *MISSION_NON_CLAIMS],
        "profile": profile,
        "raw_net_capital_floor": 0,
        "schema_version": "ccr.asi_proxy_target.v1",
        "target_id": target_id,
        "target_set": {"thresholds": {"local_residual_reduction": 1.0}},
        "target_validity_certificate_ref": "target-validity:local-fixture",
        "viability_set": {"status": "accepted"},
    }


def build_baseline_fixture(mission_id: str, *, profile: str) -> dict[str, Any]:
    """Build a local baseline upper-envelope fixture."""

    name = mission_name(mission_id)
    return {
        "baseline_id": f"baseline:{name}",
        "baseline_policy_class": "local-upper-envelope",
        "blockers": [],
        "confidence_budget": {"alpha": 0.05},
        "control_observability": {"status": "accepted"},
        "envelope_coordinates": {"local_residual_reduction": 0.0},
        "model_toolchain_environment_versions": {"python": "local"},
        "path_law_refs": ["path-law:local-dry-run"],
        "profile": profile,
        "refresh_contract": {"max_age": "P1D"},
        "residuals": [],
        "resource_envelope": {"budget": "local", "cpu": 1, "network": "none"},
        "schema_version": "ccr.baseline_upper_envelope.v1",
        "stale": False,
        "upper_bound_method": "local_fixture",
    }


def build_mission(
    mission_id: str,
    *,
    profile: str,
    template: str,
    target_ref: str,
    baseline_ref: str,
) -> dict[str, Any]:
    """Build a mission facade artifact."""

    return {
        "asi_proxy_target_ref": target_ref,
        "authority_envelope": {"scope": "local_dry_run", "status": "approved"},
        "baseline_ref": baseline_ref,
        "created_at": FIXED_CREATED_AT,
        "hazard_envelope": {"status": "accepted", "unknowns_block": True},
        "loop_policy": {
            "external_execution": False,
            "max_steps": 1,
            "mode": "advisory",
            "mutate_by_default": False,
        },
        "mission_id": mission_id,
        "non_claims": [*list(NON_CLAIMS), *MISSION_NON_CLAIMS],
        "packet_workspace": {"candidate_refs": [], "packet_refs": []},
        "profile": profile,
        "provider_policy": {
            "network_calls": "none",
            "provider_execution": False,
            "provider_output_is_evidence_only": True,
        },
        "report_policy": {"default_format": "markdown", "human_readable": True},
        "resource_envelope": {"budget": "local", "cpu": 1, "network": "none"},
        "residual_ledger": {"blocking_residuals_prevent_settlement": True, "refs": []},
        "schema_version": "ccr.mission.v1",
        "settlement_policy": {
            "blocking_residuals_prevent_settlement": True,
            "provider_output_is_evidence_only": True,
            "residual_waivers_allowed": False,
        },
        "template": template,
        "updated_at": FIXED_CREATED_AT,
    }


def build_mission_state(
    mission: dict[str, Any],
    *,
    mission_file: Path,
    target_file: Path,
    baseline_file: Path,
    loop_state_file: Path,
) -> dict[str, Any]:
    """Build a mission state artifact."""

    return {
        "baseline_path": str(baseline_file),
        "created_at": FIXED_CREATED_AT,
        "external_execution": False,
        "loop_state_path": str(loop_state_file),
        "mission_id": str(mission["mission_id"]),
        "mission_path": str(mission_file),
        "mutated_runtime": True,
        "network_call_performed": False,
        "packet_refs": [],
        "report_refs": [],
        "residual_refs": [],
        "schema_version": "ccr.mission_state.v1",
        "settled": False,
        "step_index": 0,
        "target_path": str(target_file),
        "updated_at": FIXED_CREATED_AT,
    }


def merge_state_refs(
    state: dict[str, Any],
    *,
    packet_refs: list[str] | None = None,
    residual_refs: list[str] | None = None,
    report_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Return state with deterministic merged reference sets."""

    updated = dict(state)
    for key, values in (
        ("packet_refs", packet_refs),
        ("residual_refs", residual_refs),
        ("report_refs", report_refs),
    ):
        current = updated.get(key)
        refs = [str(item) for item in current] if isinstance(current, list) else []
        refs.extend(str(item) for item in values or [])
        updated[key] = sorted(set(refs))
    updated["updated_at"] = FIXED_CREATED_AT
    return updated


def mission_scope(root: Path, mission_id: str) -> dict[str, Any]:
    """Return mission-scoped packets and residuals without global fallback."""

    state = load_mission_state(root, mission_id)
    if not state:
        residual = residual_ready(
            "missing_mission_state",
            mission_id,
            f"Mission state not found for {mission_id}.",
            "ccr.mission.scope",
        )
        return {
            "known_packet_refs": [],
            "ok": False,
            "packets": [],
            "residual_ready": residual,
            "residuals": [],
            "state": {},
            "state_missing": True,
        }
    packets = _mission_packets_from_state(root, mission_id, state)
    packet_ids = sorted(
        str(packet.get("packet_id", "")) for packet in packets if packet.get("packet_id")
    )
    residuals = _mission_residuals_from_state(root, mission_id, state, packet_ids)
    return {
        "known_packet_refs": packet_ids,
        "ok": True,
        "packets": packets,
        "residual_ready": None,
        "residuals": residuals,
        "state": state,
        "state_missing": False,
    }


def mission_packet_counts(packets: list[dict[str, Any]]) -> dict[str, int]:
    """Return packet status counts for a mission-scoped packet list."""

    counts: dict[str, int] = {}
    for packet in packets:
        status = str(packet.get("status", "candidate"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def mission_residual_counts(residuals: list[dict[str, Any]]) -> dict[str, int]:
    """Return mission-scoped residual counts."""

    counts: dict[str, int] = {}
    for residual in residuals:
        status = str(residual.get("status", "open"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _mission_packets_from_state(
    root: Path, mission_id: str, state: dict[str, Any]
) -> list[dict[str, Any]]:
    refs = state.get("packet_refs")
    ref_set = {str(item) for item in refs} if isinstance(refs, list) else set()
    packets = iter_packets(root)
    if ref_set:
        matched = [packet for packet in packets if str(packet.get("packet_id", "")) in ref_set]
        if matched:
            return matched
    return [
        packet for packet in packets if _extensions(packet).get("x_ccr_mission_id") == mission_id
    ]


def _mission_residuals_from_state(
    root: Path,
    mission_id: str,
    state: dict[str, Any],
    packet_ids: list[str],
) -> list[dict[str, Any]]:
    residual_refs = state.get("residual_refs")
    residual_ref_set = (
        {str(item) for item in residual_refs} if isinstance(residual_refs, list) else set()
    )
    packet_ref_set = set(packet_ids)
    residuals: list[dict[str, Any]] = []
    for residual in iter_residuals(root, status="open"):
        residual_id = str(residual.get("residual_id", ""))
        refs = residual.get("refs")
        ref_set = {str(item) for item in refs} if isinstance(refs, list) else set()
        object_id = str(residual.get("object_id", ""))
        extensions = _extensions(residual)
        if (
            (residual_ref_set and residual_id in residual_ref_set)
            or extensions.get("x_ccr_mission_id") == mission_id
            or object_id in packet_ref_set
            or bool(ref_set & packet_ref_set)
            or object_id == mission_id
            or mission_id in ref_set
        ):
            residuals.append(residual)
    return sorted(residuals, key=lambda item: str(item.get("residual_id", "")))


def _extensions(value: dict[str, Any]) -> dict[str, Any]:
    raw = value.get("extensions")
    return raw if isinstance(raw, dict) else {}
