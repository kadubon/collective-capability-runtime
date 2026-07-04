# SPDX-License-Identifier: Apache-2.0
"""Validate local ASI-proxy mission bundles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import (
    FIXED_CREATED_AT,
    is_path_within_root,
    read_json_bounded,
    safe_relative_display,
)
from ccr.safe_io import (
    residual_ready as make_residual_ready,
)
from ccr.schemas.loader import SCHEMA_FILENAMES, expected_schema_version
from ccr.schemas.validation import validate_instance

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
SCHEMA_KIND_BY_VERSION = {
    **{
        version: kind
        for kind in SCHEMA_FILENAMES
        for version in [expected_schema_version(kind)]
        if version
    },
    "ccr.asi_quickstart.v1": "mission-run-report",
    "ccr.mission_ingest.v1": "mission-run-report",
    "ccr.mission_next.compact.v1": "mission-run-report",
    "ccr.mission_next.v1": "mission-run-report",
    "ccr.mission_status.v1": "mission-run-report",
}
OBJECT_ID_KEYS = (
    "baseline_id",
    "bundle_id",
    "mission_id",
    "packet_id",
    "residual_id",
    "report_id",
    "target_id",
    "task_id",
)
LOCAL_REF_PREFIXES = (
    "baseline:",
    "bundle:",
    "mission:",
    "packet:",
    "report:",
    "residual:",
    "target:",
    "task:",
)
PATH_REF_KEYS = {
    "baseline_path",
    "file",
    "input_file",
    "loop_state_path",
    "mission_path",
    "output_file",
    "path",
    "target_path",
}
HASH_KEYS = ("sha256", "content_sha256", "hash")


def validate_bundle(bundle: Path, *, profile: str = "development") -> dict[str, Any]:
    """Validate a local mission bundle without executing actions."""

    blockers: list[str] = []
    residual_ready: list[dict[str, Any]] = []
    objects: list[tuple[Path, dict[str, Any]]] = []
    schema_kinds: dict[Path, str] = {}
    valid_object_ids: set[str] = set()
    root = bundle.resolve()
    if not root.exists() or not root.is_dir():
        _add_blocker(blockers, residual_ready, "missing_bundle", str(bundle), "Bundle is missing.")
        return _report(bundle, profile, blockers, residual_ready, [], {})

    for path in _iter_json_files(root, blockers, residual_ready):
        read = read_json_bounded(
            path,
            max_bytes=MAX_BUNDLE_FILE_BYTES,
            root=root,
            source="ccr.bundle.validate",
        )
        if not read.get("ok"):
            _add_ready(blockers, residual_ready, read["residual_ready"])
            continue
        data = read["data"]
        objects.append((path, data))
        schema_version = str(data.get("schema_version", ""))
        if not schema_version:
            _add_blocker(
                blockers,
                residual_ready,
                "missing_schema_version",
                _display(path, root),
                "Bundle object is missing schema_version.",
            )
            continue
        schema_kind = SCHEMA_KIND_BY_VERSION.get(schema_version)
        if schema_kind is None:
            _add_blocker(
                blockers,
                residual_ready,
                "unknown_schema_version",
                _display(path, root),
                f"Bundle object uses unknown schema_version: {schema_version}",
            )
            continue
        validation = validate_instance(schema_kind, data)
        if not validation.ok:
            _add_blocker(
                blockers,
                residual_ready,
                "schema_validation_failed",
                _display(path, root),
                f"Bundle object failed {schema_kind} schema validation.",
                extensions={"schema_errors": [issue.to_json() for issue in validation.errors]},
            )
            continue
        schema_kinds[path] = schema_kind
        object_id = _object_id(data)
        if object_id:
            valid_object_ids.add(object_id)

    has_target = any(kind == "asi-proxy-target" for kind in schema_kinds.values())
    has_baseline = any(kind == "baseline-upper-envelope" for kind in schema_kinds.values())
    has_non_claims = any(_has_required_non_claims(data) for _, data in objects)
    if not has_target:
        _add_blocker(
            blockers,
            residual_ready,
            "missing_target",
            str(bundle),
            "Bundle must contain a schema-valid ASI proxy target.",
        )
    if not has_baseline:
        _add_blocker(
            blockers,
            residual_ready,
            "missing_baseline",
            str(bundle),
            "Bundle must contain a schema-valid baseline upper envelope.",
        )
    if not has_non_claims:
        _add_blocker(
            blockers,
            residual_ready,
            "missing_non_claims",
            str(bundle),
            "Bundle must expose the ASI-proxy non-claim boundaries.",
        )

    for path, data in objects:
        _validate_object(path, data, blockers, residual_ready, root=root)
        _validate_non_claims(path, data, blockers, residual_ready, root=root)
        _validate_path_refs(path, data, blockers, residual_ready, root=root)
    _validate_reference_closure(objects, valid_object_ids, blockers, residual_ready, root=root)
    _validate_manifest_file_closure(objects, blockers, residual_ready, root=root)
    _validate_mission_target_baseline_closure(objects, blockers, residual_ready, root=root)

    observed_parity = {
        "baseline_present": has_baseline,
        "reference_closed": "unresolved_reference" not in blockers,
        "schema_bound": not any(
            blocker
            in {"missing_schema_version", "schema_validation_failed", "unknown_schema_version"}
            for blocker in blockers
        ),
        "target_present": has_target,
    }
    return _report(bundle, profile, blockers, residual_ready, objects, observed_parity)


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
            _display(root, root),
            "Bundle exceeds local file count bound.",
        )
        return files[:MAX_BUNDLE_FILES]
    return files


def _validate_object(
    path: Path,
    data: dict[str, Any],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    display = _display(path, root)
    for residual in _collect_residuals(data):
        kind = str(residual.get("kind", ""))
        if not kind:
            _add_blocker(
                blockers,
                residual_ready,
                "residual_missing_kind",
                display,
                "Residual object is missing kind.",
            )
        elif kind not in KNOWN_RESIDUAL_KINDS:
            _add_blocker(
                blockers,
                residual_ready,
                "unknown_residual_kind",
                display,
                f"Residual kind is unknown: {kind}",
            )
    if _bool_key(data, "executed") or _bool_key(data, "external_execution"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_execution",
            display,
            "Bundle must not encode implicit execution.",
        )
    if _bool_key(data, "network_call_performed"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_network_call",
            display,
            "Bundle must not encode implicit network calls.",
        )
    if _bool_key(data, "settled"):
        _add_blocker(
            blockers,
            residual_ready,
            "implicit_settlement",
            display,
            "Bundle settlement must fail closed unless separate CCR settlement evidence exists.",
        )
    if _bool_key(data, "capital_admitted") and not _has_capital_refs(data):
        _add_blocker(
            blockers,
            residual_ready,
            "capital_admission_without_refs",
            display,
            "capital_admitted=true requires transport/finality/baseline witness refs.",
        )
    if _cache_or_index_as_proof(data):
        _add_blocker(
            blockers,
            residual_ready,
            "cache_or_index_as_proof",
            display,
            "Cache or index hits must not be treated as proof.",
        )


def _validate_non_claims(
    path: Path,
    data: dict[str, Any],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    if "non_claims" not in data:
        return
    if _has_required_non_claims(data):
        return
    _add_blocker(
        blockers,
        residual_ready,
        "missing_non_claims",
        f"{_display(path, root)}:non_claims",
        "Bundle object non_claims must include all ASI-proxy mission non-claim boundaries.",
    )


def _validate_path_refs(
    path: Path,
    data: dict[str, Any],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    for key, value, holder in _iter_path_refs(data):
        if not value or "://" in value:
            continue
        candidate = (path.parent / value).resolve()
        display = f"{_display(path, root)}:{key}"
        if Path(value).is_absolute() or not is_path_within_root(candidate, root):
            _add_blocker(
                blockers,
                residual_ready,
                "path_traversal",
                display,
                f"Bundle path reference resolves outside the bundle root: {value}",
            )
            continue
        expected_hash = _expected_hash(holder)
        if expected_hash is None:
            if candidate.exists() and candidate.is_file():
                _add_residual(
                    residual_ready,
                    "missing_evidence",
                    display,
                    f"Path reference has no content hash: {value}",
                    blocking=False,
                    severity="info",
                )
            else:
                _add_blocker(
                    blockers,
                    residual_ready,
                    "path_ref_missing",
                    display,
                    f"Bundle path reference is missing and has no content hash: {value}",
                )
            continue
        if expected_hash == "unknown":
            _add_residual(
                residual_ready,
                "missing_evidence",
                display,
                f"Path reference uses unknown content hash: {value}",
                blocking=False,
                severity="low",
            )
            continue
        if not candidate.exists() or not candidate.is_file():
            _add_blocker(
                blockers,
                residual_ready,
                "hashed_file_missing",
                display,
                f"Hashed bundle path is missing: {value}",
            )
            continue
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if digest.lower() != expected_hash.lower():
            _add_blocker(
                blockers,
                residual_ready,
                "hash_mismatch",
                display,
                f"Bundle path hash mismatch for {value}.",
            )


def _validate_reference_closure(
    objects: list[tuple[Path, dict[str, Any]]],
    valid_object_ids: set[str],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    for path, data in objects:
        for key, ref in _iter_local_refs(data):
            if ref not in valid_object_ids:
                _add_blocker(
                    blockers,
                    residual_ready,
                    "unresolved_reference",
                    f"{_display(path, root)}:{key}",
                    f"Bundle local reference is not backed by a schema-valid object: {ref}",
                )


def _validate_manifest_file_closure(
    objects: list[tuple[Path, dict[str, Any]]],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    bundle_objects = [(path, data) for path, data in objects if data.get("bundle_id")]
    for path, data in bundle_objects:
        files = data.get("files")
        if files is None:
            continue
        declared = _declared_files(files)
        display = _display(path, root)
        if not declared:
            _add_blocker(
                blockers,
                residual_ready,
                "bundle_manifest_files_empty",
                display,
                "Bundle manifest files list is present but empty or malformed.",
            )
            continue
        for relative in declared:
            candidate = (path.parent / relative).resolve()
            if Path(relative).is_absolute() or not is_path_within_root(candidate, root):
                _add_blocker(
                    blockers,
                    residual_ready,
                    "path_traversal",
                    f"{display}:files",
                    f"Bundle manifest file reference resolves outside root: {relative}",
                )
            elif not candidate.exists() or not candidate.is_file():
                _add_blocker(
                    blockers,
                    residual_ready,
                    "bundle_manifest_file_missing",
                    f"{display}:files",
                    f"Bundle manifest file reference is missing: {relative}",
                )
        object_paths = {
            _display(object_path, path.parent.resolve())
            for object_path, _ in objects
            if object_path != path
        }
        missing_from_manifest = sorted(object_paths - declared)
        if missing_from_manifest:
            _add_blocker(
                blockers,
                residual_ready,
                "bundle_manifest_files_not_closed",
                f"{display}:files",
                "Bundle manifest files list does not cover every JSON object in the bundle.",
                extensions={"missing_files": missing_from_manifest},
            )


def _validate_mission_target_baseline_closure(
    objects: list[tuple[Path, dict[str, Any]]],
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    *,
    root: Path,
) -> None:
    missions = [(path, data) for path, data in objects if data.get("mission_id")]
    targets = {
        str(data.get("target_id")): (path, data)
        for path, data in objects
        if isinstance(data.get("target_id"), str)
    }
    baselines = {
        str(data.get("baseline_id")): (path, data)
        for path, data in objects
        if isinstance(data.get("baseline_id"), str)
    }
    for mission_path_value, mission in missions:
        target_ref = str(mission.get("asi_proxy_target_ref", ""))
        baseline_ref = str(mission.get("baseline_ref", ""))
        display = _display(mission_path_value, root)
        target_pair = targets.get(target_ref)
        baseline_pair = baselines.get(baseline_ref)
        if target_ref and target_pair is None:
            _add_blocker(
                blockers,
                residual_ready,
                "mission_target_ref_unresolved",
                f"{display}:asi_proxy_target_ref",
                f"Mission target ref is not backed by a target object: {target_ref}",
            )
        if baseline_ref and baseline_pair is None:
            _add_blocker(
                blockers,
                residual_ready,
                "mission_baseline_ref_unresolved",
                f"{display}:baseline_ref",
                f"Mission baseline ref is not backed by a baseline object: {baseline_ref}",
            )
        if target_pair is None or baseline_pair is None:
            continue
        _, target = target_pair
        if str(target.get("baseline_upper_envelope_ref", "")) != baseline_ref:
            _add_blocker(
                blockers,
                residual_ready,
                "target_baseline_ref_mismatch",
                f"{_display(target_pair[0], root)}:baseline_upper_envelope_ref",
                "Target baseline_upper_envelope_ref does not match mission baseline_ref.",
                extensions={
                    "mission_baseline_ref": baseline_ref,
                    "target_baseline_upper_envelope_ref": str(
                        target.get("baseline_upper_envelope_ref", "")
                    ),
                },
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


def _iter_path_refs(value: Any, *, key: str = "") -> list[tuple[str, str, dict[str, Any]]]:
    refs: list[tuple[str, str, dict[str, Any]]] = []
    if isinstance(value, dict):
        for child_key, item in value.items():
            child_key_text = str(child_key)
            if _is_path_key(child_key_text):
                if isinstance(item, str):
                    refs.append((child_key_text, item, value))
                elif isinstance(item, list):
                    for entry in item:
                        if isinstance(entry, str):
                            refs.append((child_key_text, entry, value))
            if isinstance(item, dict | list):
                refs.extend(_iter_path_refs(item, key=child_key_text))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_iter_path_refs(item, key=key))
    return refs


def _iter_local_refs(value: Any, *, key: str = "") -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for child_key, item in value.items():
            child_key_text = str(child_key)
            if _is_ref_key(child_key_text):
                if isinstance(item, str) and _looks_local_ref(item):
                    refs.append((child_key_text, item))
                elif isinstance(item, list):
                    refs.extend(
                        (child_key_text, str(entry))
                        for entry in item
                        if isinstance(entry, str) and _looks_local_ref(entry)
                    )
            if isinstance(item, dict | list):
                refs.extend(_iter_local_refs(item, key=child_key_text))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_iter_local_refs(item, key=key))
    return refs


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


def _object_id(data: dict[str, Any]) -> str:
    for key in OBJECT_ID_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _has_required_non_claims(data: dict[str, Any]) -> bool:
    values = data.get("non_claims")
    if not isinstance(values, list):
        return False
    normalized = {str(item).strip().lower() for item in values}
    required = {item.lower() for item in MISSION_NON_CLAIMS}
    if required.issubset(normalized):
        return True
    text = "\n".join(normalized)
    return (
        "does not detect real asi" in text
        and "does not grant execution authority" in text
        and ("not physical outcome proof" in text or "physical outcome proof" in text)
        and "provider output is evidence only" in text
        and "pic output is evidence only" in text
    )


def _is_path_key(key: str) -> bool:
    lowered = key.lower()
    return (
        lowered in PATH_REF_KEYS
        or lowered.endswith("_path")
        or lowered.endswith("_file")
        or lowered == "files"
    )


def _is_ref_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.endswith("_ref") or lowered.endswith("_refs")


def _looks_local_ref(value: str) -> bool:
    return value.startswith(LOCAL_REF_PREFIXES)


def _expected_hash(holder: dict[str, Any]) -> str | None:
    for key in HASH_KEYS:
        value = holder.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _declared_files(files: Any) -> set[str]:
    declared: set[str] = set()
    if not isinstance(files, list):
        return declared
    for item in files:
        if isinstance(item, str) and item:
            declared.add(item.replace("\\", "/"))
        elif isinstance(item, dict):
            raw = item.get("path") or item.get("file")
            if isinstance(raw, str) and raw:
                declared.add(raw.replace("\\", "/"))
    return declared


def _add_blocker(
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    kind: str,
    location: str,
    description: str,
    *,
    extensions: dict[str, Any] | None = None,
) -> None:
    blockers.append(kind)
    _add_residual(
        residual_ready,
        kind,
        location,
        description,
        blocking=True,
        severity="high",
        extensions=extensions,
    )


def _add_ready(
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    residual: dict[str, Any],
) -> None:
    residual_ready.append(residual)
    if residual.get("blocking"):
        extensions = residual.get("extensions")
        if isinstance(extensions, dict) and extensions.get("finding_kind"):
            blockers.append(str(extensions["finding_kind"]))
        else:
            blockers.append(str(residual.get("kind", "validation_error")))


def _add_residual(
    residual_ready: list[dict[str, Any]],
    kind: str,
    location: str,
    description: str,
    *,
    blocking: bool,
    severity: str,
    extensions: dict[str, Any] | None = None,
) -> None:
    residual_ready.append(
        make_residual_ready(
            kind,
            location,
            description,
            "ccr.bundle.validate",
            blocking=blocking,
            severity=severity,
            extensions={"bundle_location": location, **(extensions or {})},
        )
    )


def _display(path: Path, root: Path) -> str:
    return safe_relative_display(path, root=root)


def _report(
    bundle: Path,
    profile: str,
    blockers: list[str],
    residual_ready: list[dict[str, Any]],
    objects: list[tuple[Path, dict[str, Any]]],
    observed_parity: dict[str, bool],
) -> dict[str, Any]:
    parity = {
        "baseline_present": bool(observed_parity.get("baseline_present", False)),
        "reference_closed": bool(observed_parity.get("reference_closed", False)),
        "schema_bound": bool(observed_parity.get("schema_bound", False)),
        "target_present": bool(observed_parity.get("target_present", False)),
    }
    return {
        "accepted": False,
        "blockers": sorted(set(blockers)),
        "bundle": str(bundle),
        "capital_admitted": False,
        "created_at": FIXED_CREATED_AT,
        "executed": False,
        "external_execution": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "object_count": len(objects),
        "observed_parity": parity,
        "ok": not blockers,
        "profile": profile,
        "residual_ready": residual_ready,
        "schema_version": "ccr.bundle_validate.v1",
        "settled": False,
    }
