# SPDX-License-Identifier: Apache-2.0
"""Validate local ASI-proxy mission bundles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import read_json
from ccr.mission.model import FIXED_CREATED_AT, MISSION_NON_CLAIMS

MAX_BUNDLE_FILES = 500
MAX_BUNDLE_FILE_BYTES = 2_000_000
KNOWN_RESIDUAL_KINDS = {
    "authority_gap",
    "candidate_only_reason",
    "dependency_gap",
    "hazard",
    "identity_gap",
    "missing_evidence",
    "negative_liquidity",
    "other",
    "provider_missing",
    "queue_overload",
    "safe_command_hint",
    "scope_gap",
    "settlement_blocker",
    "stale_source",
    "unverified_claim",
    "validation_error",
}


def validate_bundle(bundle: Path, *, profile: str = "development") -> dict[str, Any]:
    """Validate a local mission bundle without executing actions."""

    blockers: list[str] = []
    residual_ready: list[dict[str, Any]] = []
    objects: list[tuple[Path, dict[str, Any]]] = []
    root = bundle.resolve()
    if not root.exists() or not root.is_dir():
        _add_blocker(blockers, residual_ready, "missing_bundle", str(bundle), "Bundle is missing.")
        return _report(bundle, profile, blockers, residual_ready, [])

    for path in _iter_json_files(root, blockers, residual_ready):
        try:
            resolved = path.resolve()
            resolved.relative_to(root)
        except ValueError:
            _add_blocker(
                blockers,
                residual_ready,
                "path_traversal",
                str(path),
                "Bundle path resolves outside the bundle root.",
            )
            continue
        if path.stat().st_size > MAX_BUNDLE_FILE_BYTES:
            _add_blocker(
                blockers,
                residual_ready,
                "bundle_file_too_large",
                str(path),
                "Bundle JSON file exceeds local size bound.",
            )
            continue
        data = read_json(path)
        if not isinstance(data, dict):
            _add_blocker(
                blockers,
                residual_ready,
                "bundle_json_not_object",
                str(path),
                "Bundle JSON files must contain objects.",
            )
            continue
        objects.append((path, data))
        if not data.get("schema_version"):
            _add_blocker(
                blockers,
                residual_ready,
                "missing_schema_version",
                str(path),
                "Bundle object is missing schema_version.",
            )

    has_target = any(_is_target(data) for _, data in objects)
    has_baseline = any(_is_baseline(data) for _, data in objects)
    has_non_claims = any(isinstance(data.get("non_claims"), list) for _, data in objects)
    if not has_target:
        _add_blocker(blockers, residual_ready, "missing_target", str(bundle), "Target is missing.")
    if not has_baseline:
        _add_blocker(
            blockers,
            residual_ready,
            "missing_baseline",
            str(bundle),
            "Baseline upper envelope is missing.",
        )
    if not has_non_claims:
        _add_blocker(
            blockers,
            residual_ready,
            "missing_non_claims",
            str(bundle),
            "Bundle must expose non_claims.",
        )

    for path, data in objects:
        _validate_object(path, data, blockers, residual_ready)

    return _report(bundle, profile, blockers, residual_ready, objects)


def _iter_json_files(
    root: Path,
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
) -> list[Path]:
    files = [path for path in sorted(root.rglob("*.json"), key=lambda item: str(item))]
    if len(files) > MAX_BUNDLE_FILES:
        _add_blocker(
            blockers,
            residual_ready,
            "bundle_file_count_exceeded",
            str(root),
            "Bundle exceeds local file count bound.",
        )
        return files[:MAX_BUNDLE_FILES]
    return files


def _validate_object(
    path: Path,
    data: dict[str, Any],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
) -> None:
    for residual in _collect_residuals(data):
        kind = str(residual.get("kind", ""))
        if not kind:
            _add_blocker(
                blockers,
                residual_ready,
                "residual_missing_kind",
                str(path),
                "Residual object is missing kind.",
            )
        elif kind not in KNOWN_RESIDUAL_KINDS:
            _add_blocker(
                blockers,
                residual_ready,
                "unknown_residual_kind",
                str(path),
                f"Residual kind is unknown: {kind}",
            )
    if _bool_key(data, "executed") or _bool_key(data, "external_execution"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_execution",
            str(path),
            "Bundle must not encode implicit execution.",
        )
    if _bool_key(data, "network_call_performed"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_network_call",
            str(path),
            "Bundle must not encode implicit network calls.",
        )
    if _bool_key(data, "settled"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_settlement",
            str(path),
            "Bundle settlement must fail closed unless separate CCR settlement evidence exists.",
        )
    if _bool_key(data, "capital_admitted") and not _has_capital_refs(data):
        _add_blocker(
            blockers,
            residual_ready,
            "capital_admission_without_refs",
            str(path),
            "capital_admitted=true requires transport/finality/baseline witness refs.",
        )
    if _cache_or_index_as_proof(data):
        _add_blocker(
            blockers,
            residual_ready,
            "cache_or_index_as_proof",
            str(path),
            "Cache or index hits must not be treated as proof.",
        )


def _collect_residuals(value: Any) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "kind" in value and ("blocking" in value or "residual_id" in value):
            residuals.append(value)
        for key, item in value.items():
            if key in {"residuals", "residual_ready", "blockers"} or isinstance(item, dict | list):
                residuals.extend(_collect_residuals(item))
    elif isinstance(value, list):
        for item in value:
            residuals.extend(_collect_residuals(item))
    return residuals


def _bool_key(data: dict[str, Any], key: str) -> bool:
    return data.get(key) is True


def _has_capital_refs(data: dict[str, Any]) -> bool:
    required = {"baseline_ref", "transport_ref", "finality_ref"}
    return required.issubset(data)


def _cache_or_index_as_proof(data: Any) -> bool:
    if isinstance(data, dict):
        keys = {str(key).lower() for key in data}
        if ("cache_hit" in keys or "index_hit" in keys) and (
            data.get("accepted") is True or data.get("settled") is True or data.get("proof") is True
        ):
            return True
        return any(_cache_or_index_as_proof(value) for value in data.values())
    if isinstance(data, list):
        return any(_cache_or_index_as_proof(item) for item in data)
    return False


def _is_target(data: dict[str, Any]) -> bool:
    return data.get("schema_version") == "ccr.asi_proxy_target.v1" or "target_id" in data


def _is_baseline(data: dict[str, Any]) -> bool:
    return data.get("schema_version") == "ccr.baseline_upper_envelope.v1" or "baseline_id" in data


def _add_blocker(
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    kind: str,
    location: str,
    description: str,
) -> None:
    blockers.append(kind)
    residual_ready.append(
        {
            "blocking": True,
            "created_at": FIXED_CREATED_AT,
            "description": description,
            "extensions": {"bundle_location": location},
            "kind": "validation_error",
            "object_id": location,
            "object_type": "report",
            "refs": [location],
            "repair_hint": "Repair the bundle artifact and rerun ccr bundle validate.",
            "residual_id": stable_id("residual", "bundle", kind, location, description),
            "schema_version": "ccr.residual.v0.1",
            "severity": "high",
            "source": "ccr.bundle.validate",
            "status": "open",
        }
    )


def _report(
    bundle: Path,
    profile: str,
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    objects: list[tuple[Path, dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "accepted": False,
        "blockers": sorted(set(blockers)),
        "bundle": str(bundle),
        "capital_admitted": False,
        "created_at": FIXED_CREATED_AT,
        "executed": False,
        "external_execution": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "object_count": len(objects),
        "ok": not blockers,
        "profile": profile,
        "residual_ready": residual_ready,
        "schema_version": "ccr.bundle_validate.v1",
        "settled": False,
    }
