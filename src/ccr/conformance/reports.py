# SPDX-License-Identifier: Apache-2.0
"""CCR/PIC cross-repo conformance report builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.bundles.validate import validate_bundle
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

REQUIRED_PARITY_FIELDS = (
    "schema_version",
    "ok",
    "accepted",
    "settled",
    "executed",
    "external_execution",
    "network_call_performed",
    "capital_admitted",
    "certified_acceleration_candidate",
    "certified_acceleration_interval_candidate",
    "blockers",
    "non_claims",
)
REQUIRED_DERIVED_PARITY_FIELDS = ("residual_kinds", "hashes", "refs")


def conformance_bundle(bundle: Path) -> dict[str, Any]:
    """Validate a CCR bundle for cross-repo evidence exchange."""

    validation = validate_bundle(bundle)
    residuals = list(validation.get("residual_ready", []))
    for field in ("observed_parity", "non_claims", "blockers"):
        if field not in validation:
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    str(bundle),
                    f"CCR bundle validation report is missing parity field: {field}",
                    "ccr.conformance.bundle",
                )
            )
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "bundle": str(bundle),
        "bundle_report": validation,
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_ready": residuals,
        "schema_version": "ccr.cross_repo_conformance_report.v1",
        "settled": False,
    }


def conformance_parity(ccr_report: Path, pic_report: Path) -> dict[str, Any]:
    """Compare local CCR and PIC evidence reports without executing either repo."""

    ccr = _read_json(ccr_report, source="ccr.conformance.parity.ccr")
    pic = _read_json(pic_report, source="ccr.conformance.parity.pic")
    residuals = [*ccr["residuals"], *pic["residuals"]]
    missing_by_report: dict[str, list[str]] = {}
    residual_kinds_by_report = {
        "ccr": _residual_kinds(ccr["data"]),
        "pic": _residual_kinds(pic["data"]),
    }
    hash_fields_by_report = {
        "ccr": _hash_fields(ccr["data"]),
        "pic": _hash_fields(pic["data"]),
    }
    ref_fields_by_report = {
        "ccr": _ref_fields(ccr["data"]),
        "pic": _ref_fields(pic["data"]),
    }
    for name, report in (("ccr", ccr["data"]), ("pic", pic["data"])):
        missing: list[str] = []
        for field in REQUIRED_PARITY_FIELDS:
            if field not in report:
                missing.append(field)
                residuals.append(
                    residual_ready(
                        "missing_evidence",
                        name,
                        f"{name.upper()} report is missing parity field: {field}",
                        "ccr.conformance.parity",
                    )
                )
        if not residual_kinds_by_report[name]:
            missing.append("residual_kinds")
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    name,
                    f"{name.upper()} report does not expose residual kinds/blockers.",
                    "ccr.conformance.parity",
                )
            )
        if not hash_fields_by_report[name]:
            missing.append("hashes")
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    name,
                    f"{name.upper()} report does not expose any hash field.",
                    "ccr.conformance.parity",
                )
            )
        if not ref_fields_by_report[name]:
            missing.append("refs")
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    name,
                    f"{name.upper()} report does not expose any reference field.",
                    "ccr.conformance.parity",
                )
            )
        missing_by_report[name] = sorted(set(missing))
    if pic["data"].get("settled") is True:
        residuals.append(
            residual_ready(
                "settlement_blocker",
                "pic",
                "PIC parity input is treated as evidence only and cannot grant CCR settlement.",
                "ccr.conformance.parity",
            )
        )
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "ccr_report_ref": ccr_report.name,
        "external_execution": False,
        "hash_fields_by_report": hash_fields_by_report,
        "missing_by_report": missing_by_report,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "parity_fields": [*REQUIRED_PARITY_FIELDS, *REQUIRED_DERIVED_PARITY_FIELDS],
        "pic_evidence_only": True,
        "pic_report_ref": pic_report.name,
        "ref_fields_by_report": ref_fields_by_report,
        "residual_ready": residuals,
        "residual_kind_delta": {
            "ccr_only": sorted(residual_kinds_by_report["ccr"] - residual_kinds_by_report["pic"]),
            "pic_only": sorted(residual_kinds_by_report["pic"] - residual_kinds_by_report["ccr"]),
            "shared": sorted(residual_kinds_by_report["ccr"] & residual_kinds_by_report["pic"]),
        },
        "residual_kinds_by_report": {
            "ccr": sorted(residual_kinds_by_report["ccr"]),
            "pic": sorted(residual_kinds_by_report["pic"]),
        },
        "schema_version": "ccr.parity_report.v1",
        "settled": False,
    }


def _read_json(path: Path, *, source: str) -> dict[str, Any]:
    read = read_json_bounded(path, source=source)
    if not read.get("ok"):
        return {"data": {}, "residuals": [read["residual_ready"]]}
    return {"data": read["data"], "residuals": []}


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


def _residual_kinds(report: dict[str, Any]) -> set[str]:
    kinds: set[str] = set()
    blockers = report.get("blockers")
    if isinstance(blockers, list):
        kinds.update(str(item) for item in blockers if str(item))
    for key in ("residual_ready", "residuals", "top_residuals"):
        value = report.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    kind = item.get("kind") or item.get("finding_kind")
                    if kind:
                        kinds.add(str(kind))
    return kinds


def _hash_fields(report: dict[str, Any]) -> list[str]:
    fields = []
    for key in report:
        key_lower = str(key).lower()
        if key_lower == "hashes" or key_lower.endswith("_hash") or "hashes" in key_lower:
            fields.append(str(key))
    return sorted(fields)


def _ref_fields(report: dict[str, Any]) -> list[str]:
    fields = []
    for key, value in report.items():
        key_lower = str(key).lower()
        if (
            key_lower == "refs"
            or key_lower.endswith("_ref")
            or key_lower.endswith("_refs")
            or key_lower.endswith("_report_ref")
        ) or (isinstance(value, dict) and _ref_fields(value)):
            fields.append(str(key))
    return sorted(set(fields))
