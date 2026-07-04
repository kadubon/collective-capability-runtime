# SPDX-License-Identifier: Apache-2.0
"""Provider manifest and conformance checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready
from ccr.schemas.validation import validate_instance

SAFE_SIDE_EFFECT_POLICIES = {"none", "read_only", "read-only", "dry_run_only", "dry-run-only"}
SAFE_NETWORK_POLICIES = {"none", "disabled", "explicit_source_only", "local_only", "local-only"}


def inspect_provider_manifest(path: Path) -> dict[str, Any]:
    """Inspect a provider manifest without loading or executing the provider."""

    read = read_json_bounded(path, source="ccr.provider.manifest")
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _report({}, [residual], source=str(read.get("display", path.name)))
    manifest = read["data"]
    residuals = _manifest_residuals(manifest, source=str(read["display"]))
    return _report(manifest, residuals, source=str(read["display"]))


def provider_conformance(path: Path) -> dict[str, Any]:
    """Return a provider conformance report for CI/static review."""

    report = inspect_provider_manifest(path)
    report["schema_version"] = "ccr.provider_conformance_report.v1"
    report["conformance_profile"] = "ccr-provider-static-v1"
    return report


def _manifest_residuals(manifest: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    validation = validate_instance("provider-manifest", manifest)
    if not validation.ok:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                "Provider manifest failed schema validation.",
                "ccr.provider.manifest",
                extensions={"schema_errors": [issue.to_json() for issue in validation.errors]},
            )
        )
    side_effect_policy = str(manifest.get("side_effect_policy", "unknown")).lower()
    if side_effect_policy not in SAFE_SIDE_EFFECT_POLICIES:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"Provider side_effect_policy is not static-safe: {side_effect_policy}",
                "ccr.provider.manifest",
            )
        )
    network_policy = str(manifest.get("network_policy", "unknown")).lower()
    if network_policy not in SAFE_NETWORK_POLICIES:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"Provider network_policy is not bounded: {network_policy}",
                "ccr.provider.manifest",
            )
        )
    settlement_policy = manifest.get("settlement_policy")
    if not isinstance(settlement_policy, dict) or (
        settlement_policy.get("provider_output_is_evidence_only") is not True
        or settlement_policy.get("provider_grants_settlement") is not False
    ):
        residuals.append(
            residual_ready(
                "settlement_blocker",
                source,
                "Provider manifest must state output is evidence only and grants no settlement.",
                "ccr.provider.manifest",
            )
        )
    return residuals


def _report(
    manifest: dict[str, Any],
    residuals: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    accepted = not blockers
    return {
        "accepted": accepted,
        "blockers": blockers,
        "external_execution": False,
        "manifest_hash": _hash_json(manifest) if manifest else "",
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "provider_id": str(manifest.get("provider_id", "")) if manifest else "",
        "residuals": residuals,
        "schema_version": "ccr.provider_manifest_report.v1",
        "settled": False,
        "source": source,
    }


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


def _hash_json(value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
