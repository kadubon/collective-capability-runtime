# SPDX-License-Identifier: Apache-2.0
"""Provider manifest and conformance checks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready
from ccr.schemas.loader import SCHEMA_FILENAMES
from ccr.schemas.validation import validate_instance

SAFE_SIDE_EFFECT_POLICIES = {"none", "read_only", "read-only", "dry_run_only", "dry-run-only"}
SAFE_NETWORK_POLICIES = {"none", "disabled", "explicit_source_only", "local_only", "local-only"}
KNOWN_SCHEMA_KINDS = {*SCHEMA_FILENAMES, "residual_ready"}
KNOWN_EXECUTION_MODES = {
    "candidate_only",
    "dry_run",
    "evidence_only",
    "import",
    "normalize",
    "plan",
    "static",
}
FORBIDDEN_DYNAMIC_KEYS = {
    "dynamic_import",
    "entrypoint",
    "exec",
    "execute",
    "import_path",
    "load_provider",
    "module",
    "plugin_module",
}


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
    residuals.extend(_optional_contract_residuals(manifest, source=source))
    return residuals


def _optional_contract_residuals(manifest: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    execution_modes = manifest.get("execution_modes")
    if execution_modes is not None:
        if not isinstance(execution_modes, list):
            residuals.append(
                residual_ready(
                    "validation_error",
                    source,
                    "Provider execution_modes must be a list.",
                    "ccr.provider.manifest",
                )
            )
        else:
            for mode in execution_modes:
                mode_text = str(mode)
                if mode_text not in KNOWN_EXECUTION_MODES:
                    residuals.append(
                        residual_ready(
                            "authority_gap",
                            source,
                            f"Provider execution mode is unknown or unsafe: {mode_text}",
                            "ccr.provider.manifest",
                        )
                    )
    output_schemas = manifest.get("output_schemas")
    if output_schemas is not None:
        if not isinstance(output_schemas, list):
            residuals.append(
                residual_ready(
                    "validation_error",
                    source,
                    "Provider output_schemas must be a list.",
                    "ccr.provider.manifest",
                )
            )
        else:
            for schema in output_schemas:
                schema_text = str(schema)
                if schema_text not in KNOWN_SCHEMA_KINDS:
                    residuals.append(
                        residual_ready(
                            "validation_error",
                            source,
                            f"Provider output schema is not a known CCR schema kind: {schema_text}",
                            "ccr.provider.manifest",
                        )
                    )
    safe_command_handling = manifest.get("safe_command_handling")
    if safe_command_handling is not None:
        safe_text = canonical_dumps(safe_command_handling).lower()
        if "task_hint" not in safe_text and "task-hint" not in safe_text:
            residuals.append(
                residual_ready(
                    "safe_command_hint",
                    source,
                    "Provider safe_command_handling must route safe commands as task hints only.",
                    "ccr.provider.manifest",
                )
            )
        if "execute" in safe_text or "shell" in safe_text or "subprocess" in safe_text:
            residuals.append(
                residual_ready(
                    "authority_gap",
                    source,
                    "Provider safe_command_handling must not request shell execution.",
                    "ccr.provider.manifest",
                )
            )
    if manifest.get("network_required") is True:
        network_policy = str(manifest.get("network_policy", "unknown")).lower()
        if network_policy not in {"explicit_source_only"}:
            residuals.append(
                residual_ready(
                    "authority_gap",
                    source,
                    "Provider network_required=true requires explicit_source_only network_policy.",
                    "ccr.provider.manifest",
                )
            )
    side_effect_class = manifest.get("side_effect_class")
    if (
        side_effect_class is not None
        and str(side_effect_class).lower() not in SAFE_SIDE_EFFECT_POLICIES
    ):
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"Provider side_effect_class is not static-safe: {side_effect_class}",
                "ccr.provider.manifest",
            )
        )
    if _contains_forbidden_dynamic_key(manifest):
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "Provider manifest contains dynamic import/loading/execution fields.",
                "ccr.provider.manifest",
            )
        )
    return residuals


def _contains_forbidden_dynamic_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_DYNAMIC_KEYS:
                return True
            if _contains_forbidden_dynamic_key(item):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_dynamic_key(item) for item in value)
    return False


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
