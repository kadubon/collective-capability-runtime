# SPDX-License-Identifier: Apache-2.0
"""Local external ingest facades."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.claims.audit import audit_claims
from ccr.claims.extract import extract_claims_from_text
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_text_bounded, residual_ready

MAX_TRACE_BYTES = 1_000_000
MAX_REPO_FILES = 2_000


def ingest_trace(path: Path) -> dict[str, Any]:
    """Inspect an external trace as candidate-only input without mutating runtime."""

    read = read_text_bounded(path, max_bytes=MAX_TRACE_BYTES, source="ccr.ingest.trace")
    if not read.get("ok"):
        return _failure_report("ccr.external_ingest_trace.v1", [read["residual_ready"]])
    source = str(read["display"])
    extract = extract_claims_from_text(str(read["text"]), source=source)
    audit = audit_claims(extract["claims"], source=source, fail_on=[])
    residuals = [item for item in audit.get("residual_ready", []) if isinstance(item, dict)]
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "candidate_only": True,
        "claim_count": extract["claim_count"],
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_ready": residuals,
        "schema_version": "ccr.external_ingest_trace.v1",
        "settled": False,
        "source": source,
    }


def ingest_repo(path: Path) -> dict[str, Any]:
    """Inspect a repository path as candidate-only input without executing commands."""

    if not path.exists() or not path.is_dir():
        residual = residual_ready(
            "missing_evidence",
            str(path),
            "Repository ingest path is missing or not a directory.",
            "ccr.ingest.repo",
        )
        return _failure_report("ccr.external_ingest_repo.v1", [residual])
    files = [
        item
        for item in sorted(path.rglob("*"), key=lambda entry: str(entry))
        if item.is_file() and ".git" not in item.parts
    ]
    residuals: list[dict[str, Any]] = []
    if len(files) > MAX_REPO_FILES:
        residuals.append(
            residual_ready(
                "queue_overload",
                path.name,
                "Repository ingest file count exceeds local facade bound.",
                "ccr.ingest.repo",
            )
        )
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "candidate_only": True,
        "external_execution": False,
        "file_count": min(len(files), MAX_REPO_FILES),
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_ready": residuals,
        "schema_version": "ccr.external_ingest_repo.v1",
        "settled": False,
        "source": path.name,
    }


def _failure_report(schema_version: str, residuals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted": False,
        "blockers": _blocker_kinds(residuals),
        "candidate_only": True,
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": False,
        "residual_ready": residuals,
        "schema_version": schema_version,
        "settled": False,
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
