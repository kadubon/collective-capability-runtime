# SPDX-License-Identifier: Apache-2.0
"""CCR/PIC cross-repo conformance report builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.bundles.validate import validate_bundle
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

REQUIRED_PARITY_FIELDS = ("schema_version", "ok", "settled")


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
    for name, report in (("ccr", ccr["data"]), ("pic", pic["data"])):
        for field in REQUIRED_PARITY_FIELDS:
            if field not in report:
                residuals.append(
                    residual_ready(
                        "missing_evidence",
                        name,
                        f"{name.upper()} report is missing parity field: {field}",
                        "ccr.conformance.parity",
                    )
                )
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
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "pic_evidence_only": True,
        "pic_report_ref": pic_report.name,
        "residual_ready": residuals,
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
