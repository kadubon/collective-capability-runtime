# SPDX-License-Identifier: Apache-2.0
"""Local external ingest facades."""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.claims.audit import audit_claims
from ccr.claims.extract import extract_claims_from_text
from ccr.extensions import make_packet
from ccr.ids import stable_id
from ccr.mission.model import (
    MISSION_NON_CLAIMS,
    load_mission,
    load_mission_state,
    merge_state_refs,
    mission_path,
    save_mission_state,
)
from ccr.packets.store import submit_packet
from ccr.residuals.store import save_residual
from ccr.safe_io import read_text_bounded, residual_ready

MAX_TRACE_BYTES = 1_000_000
MAX_REPO_FILES = 2_000
MAX_REPO_FILE_BYTES = 250_000
MAX_INGESTED_FILES = 50
MAX_INGESTED_CLAIMS = 20
EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "ccr_runtime",
    "dist",
    "node_modules",
    "packets",
    "reports",
    "residuals",
    "tasks",
}
SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)\b\s*[:=]\s*([^\s,'\"]+)"
)


def ingest_trace(
    path: Path,
    *,
    root: Path | None = None,
    mission_id: str | None = None,
    source_format: str = "auto",
    write_candidates: bool = False,
) -> dict[str, Any]:
    """Inspect an external trace as candidate-only input without mutating runtime."""

    if source_format not in {"auto", "jsonl", "markdown"}:
        residual = residual_ready(
            "validation_error",
            path.name,
            f"Unsupported trace ingest format: {source_format}",
            "ccr.ingest.trace",
        )
        return _failure_report("ccr.external_ingest_report.v1", [residual])
    read = read_text_bounded(path, max_bytes=MAX_TRACE_BYTES, source="ccr.ingest.trace")
    if not read.get("ok"):
        return _failure_report("ccr.external_ingest_trace.v1", [read["residual_ready"]])
    source = str(read["display"])
    redacted_text = _redact_secrets(str(read["text"]))
    extract = extract_claims_from_text(redacted_text, source=source)
    audit = audit_claims(extract["claims"], source=source, fail_on=[])
    residuals = [item for item in audit.get("residual_ready", []) if isinstance(item, dict)]
    materialized = _maybe_materialize(
        root,
        mission_id=mission_id,
        write_candidates=write_candidates,
        sources=[{"source": source, "text": redacted_text, "claims": extract["claims"]}],
        residuals=residuals,
    )
    residuals = [*residuals, *materialized["residual_ready"]]
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "candidate_only": True,
        "claim_count": extract["claim_count"],
        "external_execution": False,
        "format": source_format,
        "ingested_packet_ids": materialized["packet_ids"],
        "mission_id": mission_id or "",
        "mutated_runtime": materialized["mutated_runtime"],
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_ready": residuals,
        "residual_ids": materialized["residual_ids"],
        "schema_version": "ccr.external_ingest_report.v1",
        "settled": False,
        "source": source,
        "write_candidates": write_candidates,
    }


def ingest_repo(
    path: Path,
    *,
    root: Path | None = None,
    mission_id: str | None = None,
    write_candidates: bool = False,
) -> dict[str, Any]:
    """Inspect a repository path as candidate-only input without executing commands."""

    if not path.exists() or not path.is_dir():
        residual = residual_ready(
            "missing_evidence",
            str(path),
            "Repository ingest path is missing or not a directory.",
            "ccr.ingest.repo",
        )
        return _failure_report("ccr.external_ingest_report.v1", [residual])
    files = [
        item for item in sorted(path.rglob("*"), key=lambda entry: str(entry)) if item.is_file()
    ]
    eligible = [item for item in files if not _is_excluded_repo_path(item, path)]
    residuals: list[dict[str, Any]] = []
    if len(eligible) > MAX_REPO_FILES:
        residuals.append(
            residual_ready(
                "queue_overload",
                path.name,
                "Repository ingest file count exceeds local facade bound.",
                "ccr.ingest.repo",
            )
        )
    sources: list[dict[str, Any]] = []
    claim_count = 0
    for item in eligible[:MAX_INGESTED_FILES]:
        read = read_text_bounded(
            item,
            max_bytes=MAX_REPO_FILE_BYTES,
            root=path,
            source="ccr.ingest.repo",
        )
        if not read.get("ok"):
            raw = read["residual_ready"]
            residuals.append(
                {
                    **raw,
                    "blocking": False,
                    "severity": "info",
                    "description": f"Repository ingest skipped file: {raw.get('description', '')}",
                }
            )
            continue
        source = str(read["display"])
        text = _redact_secrets(str(read["text"]))
        extract = extract_claims_from_text(text, source=source)
        claim_count += int(extract["claim_count"])
        audit = audit_claims(extract["claims"], source=source, fail_on=[])
        residuals.extend(item for item in audit.get("residual_ready", []) if isinstance(item, dict))
        sources.append({"source": source, "text": text, "claims": extract["claims"]})
    materialized = _maybe_materialize(
        root,
        mission_id=mission_id,
        write_candidates=write_candidates,
        sources=sources,
        residuals=residuals,
    )
    residuals = [*residuals, *materialized["residual_ready"]]
    blockers = _blocker_kinds(residuals)
    return {
        "accepted": not blockers,
        "blockers": blockers,
        "candidate_only": True,
        "claim_count": claim_count,
        "external_execution": False,
        "file_count": min(len(eligible), MAX_REPO_FILES),
        "ingested_packet_ids": materialized["packet_ids"],
        "mission_id": mission_id or "",
        "mutated_runtime": materialized["mutated_runtime"],
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_ready": residuals,
        "residual_ids": materialized["residual_ids"],
        "schema_version": "ccr.external_ingest_report.v1",
        "settled": False,
        "source": path.name,
        "write_candidates": write_candidates,
    }


def _failure_report(schema_version: str, residuals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "accepted": False,
        "blockers": _blocker_kinds(residuals),
        "candidate_only": True,
        "external_execution": False,
        "ingested_packet_ids": [],
        "mission_id": "",
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": False,
        "residual_ready": residuals,
        "residual_ids": [],
        "schema_version": schema_version,
        "settled": False,
        "write_candidates": False,
    }


def _maybe_materialize(
    root: Path | None,
    *,
    mission_id: str | None,
    write_candidates: bool,
    sources: list[dict[str, Any]],
    residuals: list[dict[str, Any]],
) -> dict[str, Any]:
    if not write_candidates and not mission_id:
        return {
            "mutated_runtime": False,
            "packet_ids": [],
            "residual_ids": [],
            "residual_ready": [],
        }
    if not root or not mission_id:
        residual = residual_ready(
            "missing_evidence",
            mission_id or "mission:missing",
            "Mission ingest requires --mission, --root, and --write-candidates.",
            "ccr.ingest",
        )
        return {
            "mutated_runtime": False,
            "packet_ids": [],
            "residual_ids": [],
            "residual_ready": [residual],
        }
    if not write_candidates:
        return {
            "mutated_runtime": False,
            "packet_ids": [],
            "residual_ids": [],
            "residual_ready": [],
        }
    if not mission_path(root, mission_id).exists():
        residual = residual_ready(
            "missing_mission",
            mission_id,
            f"Mission not found: {mission_id}",
            "ccr.ingest",
        )
        return {
            "mutated_runtime": False,
            "packet_ids": [],
            "residual_ids": [],
            "residual_ready": [residual],
        }
    mission = load_mission(root, mission_id)
    state = load_mission_state(root, mission_id)
    if not state:
        residual = residual_ready(
            "missing_mission_state",
            mission_id,
            f"Mission state not found for {mission_id}.",
            "ccr.ingest",
        )
        return {
            "mutated_runtime": False,
            "packet_ids": [],
            "residual_ids": [],
            "residual_ready": [residual],
        }
    packet_ids: list[str] = []
    packet_paths: list[str] = []
    for source in sources:
        source_ref = str(source["source"])
        raw_claims = source.get("claims")
        claims = raw_claims if isinstance(raw_claims, list) else []
        for claim in claims[:MAX_INGESTED_CLAIMS]:
            if not isinstance(claim, dict):
                continue
            packet_id = stable_id("packet:ingest", mission_id, source_ref, claim.get("claim_id"))
            packet = make_packet(
                packet_id=packet_id,
                summary=f"External ingest candidate from {source_ref}.",
                claim_text=str(claim.get("text", "")),
                packet_type="trace",
            )
            packet.setdefault("extensions", {})
            packet["extensions"].update(
                {
                    "x_ccr_claim_id": claim.get("claim_id"),
                    "x_ccr_ingest_source": source_ref,
                    "x_ccr_mission_id": mission_id,
                    "x_source_line": claim.get("line"),
                }
            )
            packet["provenance"]["source_refs"] = [source_ref]
            with suppress(FileExistsError):
                packet_paths.append(str(submit_packet(root, packet)))
            packet_ids.append(packet_id)
    residual_ids: list[str] = []
    for residual in residuals:
        prepared = _mission_residual(residual, mission_id=mission_id)
        save_residual(root, prepared, overwrite=True)
        residual_ids.append(str(prepared["residual_id"]))
    state = merge_state_refs(state, packet_refs=packet_ids, residual_refs=residual_ids)
    save_mission_state(root, state)
    workspace = mission.get("packet_workspace")
    if isinstance(workspace, dict):
        workspace["candidate_refs"] = sorted(
            set([*workspace.get("candidate_refs", []), *packet_ids])
        )
        workspace["packet_refs"] = sorted(set([*workspace.get("packet_refs", []), *packet_ids]))
        from ccr.io import write_json_atomic

        write_json_atomic(mission_path(root, mission_id), mission, overwrite=True)
    append_event(
        root,
        make_event(
            action="ingest.external",
            object_type="runtime",
            object_id=mission_id,
            status_before=None,
            status_after="candidate_packets",
            refs=[*packet_paths],
            residuals=residual_ids,
            note="External ingest creates local candidate packets/residuals only.",
        ),
    )
    return {
        "mutated_runtime": True,
        "packet_ids": sorted(set(packet_ids)),
        "residual_ids": sorted(set(residual_ids)),
        "residual_ready": [],
    }


def _mission_residual(residual: dict[str, Any], *, mission_id: str) -> dict[str, Any]:
    prepared = dict(residual)
    refs = prepared.get("refs")
    ref_set = {str(item) for item in refs} if isinstance(refs, list) else set()
    ref_set.add(mission_id)
    prepared["refs"] = sorted(ref_set)
    extensions = prepared.get("extensions")
    extension_map = dict(extensions) if isinstance(extensions, dict) else {}
    extension_map["x_ccr_mission_id"] = mission_id
    prepared["extensions"] = extension_map
    return prepared


def _redact_secrets(text: str) -> str:
    return SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)


def _is_excluded_repo_path(path: Path, root: Path) -> bool:
    try:
        parts = path.resolve().relative_to(root.resolve()).parts
    except (OSError, ValueError):
        return True
    lowered = {part.lower() for part in parts}
    if lowered & EXCLUDED_DIR_NAMES:
        return True
    return path.name in {"ccr.sqlite", "uv.lock"}


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
