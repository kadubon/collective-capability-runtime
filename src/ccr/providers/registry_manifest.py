# SPDX-License-Identifier: Apache-2.0
"""Static provider plugin registry manifest validation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.providers.manifest import inspect_provider_manifest
from ccr.safe_io import is_path_within_root, read_json_bounded, residual_ready
from ccr.schemas.validation import validate_instance

SAFE_SIDE_EFFECT_CLASSES = {"none", "read_only", "read-only", "dry_run_only", "dry-run-only"}
KNOWN_PROVIDER_CLASSES = {"static", "manifest", "http", "pic", "custom"}


def validate_registry_manifest(path: Path) -> dict[str, Any]:
    """Validate a static provider registry manifest without importing providers."""

    read = read_json_bounded(path, source="ccr.provider.registry")
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _report(path, {}, [residual])
    registry = read["data"]
    residuals = []
    validation = validate_instance("provider-registry", registry)
    if not validation.ok:
        residuals.append(
            residual_ready(
                "validation_error",
                path.name,
                "Provider registry failed schema validation.",
                "ccr.provider.registry",
                extensions={"schema_errors": [issue.to_json() for issue in validation.errors]},
            )
        )
    residuals.extend(_registry_residuals(path, registry))
    return _report(path, registry, residuals)


def list_registry(path: Path) -> dict[str, Any]:
    """List provider registry entries only when static validation passes."""

    report = validate_registry_manifest(path)
    entries = report.get("providers", []) if report.get("ok") else []
    return {
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": bool(report.get("ok")),
        "providers": entries,
        "registry_report": report,
        "schema_version": "ccr.provider_registry_list.v1",
        "settled": False,
    }


def _registry_residuals(path: Path, registry: dict[str, Any]) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    entries = registry.get("providers")
    if not isinstance(entries, list):
        return [
            residual_ready(
                "validation_error",
                path.name,
                "Provider registry manifest must contain providers list.",
                "ccr.provider.registry",
            )
        ]
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            residuals.append(
                residual_ready(
                    "validation_error",
                    path.name,
                    "Provider registry entry must be an object.",
                    "ccr.provider.registry",
                )
            )
            continue
        provider_id = str(entry.get("provider_id", ""))
        if not provider_id:
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    path.name,
                    "Provider registry entry is missing provider_id.",
                    "ccr.provider.registry",
                )
            )
        elif provider_id in seen:
            residuals.append(
                residual_ready(
                    "validation_error",
                    provider_id,
                    f"Provider registry contains duplicate provider_id: {provider_id}",
                    "ccr.provider.registry",
                )
            )
        seen.add(provider_id)
        provider_class = str(entry.get("provider_class", "static"))
        if provider_class not in KNOWN_PROVIDER_CLASSES:
            residuals.append(
                residual_ready(
                    "validation_error",
                    provider_id,
                    f"Provider registry class is unknown: {provider_class}",
                    "ccr.provider.registry",
                )
            )
        side_effect = str(entry.get("side_effect_class", "none")).lower()
        if side_effect not in SAFE_SIDE_EFFECT_CLASSES:
            residuals.append(
                residual_ready(
                    "authority_gap",
                    provider_id,
                    f"Provider registry side_effect_class is unsafe: {side_effect}",
                    "ccr.provider.registry",
                )
            )
        residuals.extend(_manifest_ref_residuals(path, entry, provider_id=provider_id))
    return residuals


def _manifest_ref_residuals(
    registry_path: Path, entry: dict[str, Any], *, provider_id: str
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    manifest_ref = entry.get("manifest_path") or entry.get("manifest")
    if not isinstance(manifest_ref, str) or not manifest_ref:
        residuals.append(
            residual_ready(
                "missing_evidence",
                provider_id,
                "Provider registry entry is missing manifest_path.",
                "ccr.provider.registry",
            )
        )
        return residuals
    manifest_path = (registry_path.parent / manifest_ref).resolve()
    if Path(manifest_ref).is_absolute() or not is_path_within_root(
        manifest_path, registry_path.parent
    ):
        residuals.append(
            residual_ready(
                "validation_error",
                provider_id,
                "Provider registry manifest_path resolves outside the registry directory.",
                "ccr.provider.registry",
            )
        )
        return residuals
    if not manifest_path.exists():
        residuals.append(
            residual_ready(
                "missing_evidence",
                provider_id,
                f"Provider registry manifest_path is missing: {manifest_ref}",
                "ccr.provider.registry",
            )
        )
        return residuals
    manifest_report = inspect_provider_manifest(manifest_path)
    residuals.extend(
        residual for residual in manifest_report.get("residuals", []) if isinstance(residual, dict)
    )
    expected_hash = entry.get("manifest_hash") or entry.get("sha256")
    if isinstance(expected_hash, str) and expected_hash:
        actual_hash = _hash_json(_read_json_data(manifest_path))
        if expected_hash != actual_hash:
            residuals.append(
                residual_ready(
                    "stale_source",
                    provider_id,
                    "Provider registry manifest hash does not match the manifest file.",
                    "ccr.provider.registry",
                    extensions={"actual_hash": actual_hash, "expected_hash": expected_hash},
                )
            )
    return residuals


def _report(
    path: Path, registry: dict[str, Any], residuals: list[dict[str, Any]]
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    raw_entries = registry.get("providers")
    entries = raw_entries if isinstance(raw_entries, list) else []
    providers = [
        {
            "manifest_path": str(entry.get("manifest_path", "")),
            "provider_class": str(entry.get("provider_class", "static")),
            "provider_id": str(entry.get("provider_id", "")),
            "side_effect_class": str(entry.get("side_effect_class", "none")),
        }
        for entry in entries
        if isinstance(entry, dict)
    ]
    return {
        "blockers": blockers,
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "providers": providers,
        "registry_hash": _hash_json(registry) if registry else "",
        "residual_ready": residuals,
        "schema_version": "ccr.provider_registry_report.v1",
        "settled": False,
        "source": path.name,
    }


def _read_json_data(path: Path) -> dict[str, Any]:
    read = read_json_bounded(path, source="ccr.provider.registry.manifest")
    if read.get("ok") and isinstance(read.get("data"), dict):
        return cast(dict[str, Any], read["data"])
    return {}


def _hash_json(value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _blocker_kinds(residuals: list[dict[str, Any]]) -> list[str]:
    kinds: list[str] = []
    for residual in residuals:
        if residual.get("blocking"):
            extensions = residual.get("extensions")
            if isinstance(extensions, dict) and extensions.get("finding_kind"):
                kinds.append(str(extensions["finding_kind"]))
            else:
                kinds.append(str(residual.get("kind", "validation_error")))
    return sorted(set(kinds))
