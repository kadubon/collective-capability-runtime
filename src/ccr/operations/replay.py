# SPDX-License-Identifier: Apache-2.0
"""Operation replay manifests and static observation verification."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import write_json_atomic
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready


def replay_manifest(
    dispatch_report: Path, observation: Path, *, out: Path | None = None
) -> dict[str, Any]:
    """Build a replay manifest without dispatching providers or physical operations."""

    dispatch_read = _read_json(dispatch_report, source="ccr.operation.replay.dispatch")
    observation_read = _read_json(observation, source="ccr.operation.replay.observation")
    dispatch = dispatch_read["data"]
    observed = observation_read["data"]
    residuals = [*dispatch_read["residuals"], *observation_read["residuals"]]
    residuals.extend(_replay_residuals(dispatch, observed))
    blockers = _blocker_kinds(residuals)
    manifest = {
        "accepted": not blockers,
        "blockers": blockers,
        "dispatch_ref": dispatch_report.name,
        "dispatch_report_hash": _object_hash(dispatch),
        "executed": False,
        "external_execution": False,
        "manifest_id": stable_id("operation-replay", dispatch, observed),
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "observation_hash": _object_hash(observed),
        "observation_ref": observation.name,
        "ok": not blockers,
        "provider_dispatch_ready": False,
        "replay_steps": [
            "Load dispatch report as evidence.",
            "Load observation as evidence.",
            "Route unresolved acceptance, rollback, hazard, and incident gaps as residuals.",
        ],
        "residual_ready": residuals,
        "schema_version": "ccr.operation_replay_manifest.v1",
        "settled": False,
    }
    if out is not None:
        write_json_atomic(out, manifest, overwrite=True)
    return manifest


def verify_observation(manifest_path: Path, verifier_path: Path) -> dict[str, Any]:
    """Verify an observation against a static JSON verifier profile."""

    manifest_read = _read_json(manifest_path, source="ccr.operation.verify.manifest")
    verifier_read = _read_json(verifier_path, source="ccr.operation.verify.verifier")
    manifest = manifest_read["data"]
    verifier = verifier_read["data"]
    residuals = [*manifest_read["residuals"], *verifier_read["residuals"]]
    if (
        verifier.get("accepted") is not True
        and verifier.get("verifier_accepts_observation") is not True
    ):
        residuals.append(
            residual_ready(
                "unverified_claim",
                verifier_path.name,
                "Observation verifier profile does not explicitly accept the observation.",
                "ccr.operation.verify_observation",
            )
        )
    if verifier.get("rollback_verified") is not True:
        residuals.append(
            residual_ready(
                "hazard",
                verifier_path.name,
                "Observation verifier profile does not verify rollback readiness.",
                "ccr.operation.verify_observation",
            )
        )
    if verifier.get("hazard_followup_complete") is not True:
        residuals.append(
            residual_ready(
                "hazard",
                verifier_path.name,
                "Observation verifier profile does not close hazard follow-up.",
                "ccr.operation.verify_observation",
            )
        )
    if verifier.get("incident_unresolved") is True:
        residuals.append(
            residual_ready(
                "settlement_blocker",
                verifier_path.name,
                "Observation verifier profile reports an unresolved incident.",
                "ccr.operation.verify_observation",
            )
        )
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "executed": False,
        "external_execution": False,
        "manifest_id": str(manifest.get("manifest_id", "")),
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "provider_dispatch_ready": False,
        "residual_ready": residuals,
        "schema_version": "ccr.observation_verification_report.v1",
        "settled": False,
        "verifier_ref": verifier_path.name,
    }


def _replay_residuals(
    dispatch: dict[str, Any], observation: dict[str, Any]
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    if dispatch.get("executed") is True or dispatch.get("provider_dispatch_ready") is True:
        residuals.append(
            residual_ready(
                "authority_gap",
                "dispatch_report",
                "Replay manifest cannot treat prior dispatch as current execution authority.",
                "ccr.operation.replay_manifest",
            )
        )
    if observation.get("accepted") is not True and observation.get("verified") is not True:
        residuals.append(
            residual_ready(
                "unverified_claim",
                "observation",
                "Observation lacks explicit acceptance/verification.",
                "ccr.operation.replay_manifest",
            )
        )
    if not observation.get("rollback_ref") and not observation.get("rollback_verified"):
        residuals.append(
            residual_ready(
                "hazard",
                "observation",
                "Observation lacks rollback evidence.",
                "ccr.operation.replay_manifest",
            )
        )
    if not observation.get("hazard_followup_ref") and not observation.get(
        "hazard_followup_complete"
    ):
        residuals.append(
            residual_ready(
                "hazard",
                "observation",
                "Observation lacks hazard follow-up evidence.",
                "ccr.operation.replay_manifest",
            )
        )
    if observation.get("incident_unresolved") is True:
        residuals.append(
            residual_ready(
                "settlement_blocker",
                "observation",
                "Observation records an unresolved incident.",
                "ccr.operation.replay_manifest",
            )
        )
    return residuals


def _read_json(path: Path, *, source: str) -> dict[str, Any]:
    read = read_json_bounded(path, source=source)
    if not read.get("ok"):
        return {"data": {}, "residuals": [read["residual_ready"]]}
    return {"data": read["data"], "residuals": []}


def _object_hash(value: dict[str, Any]) -> str:
    import hashlib

    from ccr.io import canonical_dumps

    return f"sha256:{hashlib.sha256(canonical_dumps(value).encode('utf-8')).hexdigest()}"


def _blocker_kinds(residuals: list[dict[str, Any]]) -> list[str]:
    kinds = []
    for residual in residuals:
        if residual.get("blocking"):
            extensions = residual.get("extensions")
            if isinstance(extensions, dict) and extensions.get("finding_kind"):
                kinds.append(str(extensions["finding_kind"]))
            else:
                kinds.append(str(residual.get("kind", "validation_error")))
    return sorted(set(kinds))
