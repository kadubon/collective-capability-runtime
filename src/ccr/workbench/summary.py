# SPDX-License-Identifier: Apache-2.0
"""Workbench report summary builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.constants import PACKET_STATUSES
from ccr.io import json_file_name, pretty_dumps, write_json_atomic
from ccr.mission.model import MISSION_NON_CLAIMS, load_mission, mission_path, mission_scope
from ccr.safe_io import residual_ready
from ccr.schemas.validation import validate_instance
from ccr.workbench.markdown import render_markdown_report


def build_workbench_report(root: Path, *, mission_id: str) -> dict[str, Any]:
    """Build a mission workbench report without executing external actions."""

    if not mission_path(root, mission_id).exists():
        residual = residual_ready(
            "missing_mission",
            mission_id,
            f"Mission not found: {mission_id}",
            "ccr.workbench",
        )
        report = _failure_report(
            mission_id,
            profile=None,
            residual=residual,
            target_ref="",
            baseline_ref="",
        )
        _validate_workbench_report(root, report)
        return report
    mission = load_mission(root, mission_id)
    scope = mission_scope(root, mission_id)
    if not scope["ok"]:
        report = _failure_report(
            mission_id,
            profile=mission.get("profile"),
            residual=scope["residual_ready"],
            target_ref=str(mission.get("asi_proxy_target_ref", "")),
            baseline_ref=str(mission.get("baseline_ref", "")),
        )
        _validate_workbench_report(root, report)
        return report
    packets = [packet for packet in scope["packets"] if isinstance(packet, dict)]
    packet_summary = {status: 0 for status in PACKET_STATUSES}
    for packet in packets:
        packet_summary[str(packet.get("status", "candidate"))] = (
            packet_summary.get(str(packet.get("status", "candidate")), 0) + 1
        )
    positive_packets = [
        packet
        for packet in packets
        if packet.get("status") in {"checked", "settled"}
        and not [
            residual
            for residual in scope["residuals"]
            if residual.get("blocking")
            and (
                residual.get("object_id") == packet.get("packet_id")
                or packet.get("packet_id") in _residual_refs(residual)
            )
        ]
    ]
    candidate_only_count = sum(
        1
        for packet in packets
        if packet.get("status") in {"raw", "proposed", "candidate", "provisional", "speculative"}
    )
    duplicate_count = sum(1 for packet in packets if _is_duplicate(packet))
    blocking_residuals = [residual for residual in scope["residuals"] if residual.get("blocking")]
    top_residuals = [_residual_summary(item) for item in _rank_residuals(blocking_residuals)[:5]]
    accepted = bool(positive_packets) and not blocking_residuals
    report = {
        "accepted": accepted,
        "authority_status": mission.get("authority_envelope", {}).get("status", "unknown")
        if isinstance(mission.get("authority_envelope"), dict)
        else "unknown",
        "baseline_ref": mission.get("baseline_ref"),
        "blocking_residual_count": len(blocking_residuals),
        "candidate_only_count": candidate_only_count,
        "duplicate_count": duplicate_count,
        "external_execution": False,
        "hazard_status": mission.get("hazard_envelope", {}).get("status", "unknown")
        if isinstance(mission.get("hazard_envelope"), dict)
        else "unknown",
        "mission_id": mission_id,
        "mission_summary": {
            "authority_scope": mission.get("authority_envelope", {}).get("scope", "unknown")
            if isinstance(mission.get("authority_envelope"), dict)
            else "unknown",
            "template": mission.get("template", "unknown"),
        },
        "mutated_runtime": False,
        "network_call_performed": False,
        "next_safe_action": {
            "command": f"ccr mission next --mission {mission_id} --compact --json",
            "external_execution": False,
            "writes_runtime": False,
        },
        "non_claims": sorted(set([*list(mission.get("non_claims", [])), *MISSION_NON_CLAIMS])),
        "ok": accepted,
        "operation_readiness_boundary": {
            "operation_ready_is_not_execution": True,
            "physical_ready_is_not_outcome_proof": True,
        },
        "packet_status_summary": packet_summary,
        "positive_packet_count": len(positive_packets),
        "profile": mission.get("profile"),
        "provider_evidence_boundary": {
            "pic_output_is_settlement": False,
            "provider_output_is_evidence_only": True,
        },
        "quarantined_count": packet_summary.get("quarantined", 0),
        "repair_hints": _repair_hints(top_residuals),
        "schema_version": "ccr.workbench_report.v1",
        "settled": False,
        "speculative_count": packet_summary.get("speculative", 0),
        "target_ref": mission.get("asi_proxy_target_ref"),
        "top_residuals": top_residuals,
    }
    _validate_workbench_report(root, report)
    return report


def write_report_artifact(root: Path, report: dict[str, Any]) -> Path:
    """Write a JSON workbench report under the runtime root."""

    mission_id = str(report.get("mission_id", "mission:unknown"))
    path = root / "reports" / "workbench" / json_file_name(f"workbench:{mission_id}")
    _validate_workbench_report(root, report)
    write_json_atomic(path, report, overwrite=True)
    return path


def write_workbench_report(
    root: Path,
    *,
    mission_id: str,
    report_format: str,
    out: Path,
) -> dict[str, Any]:
    """Write a workbench report to an explicit output path."""

    report = build_workbench_report(root, mission_id=mission_id)
    _validate_workbench_report(root, report)
    out.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "json":
        out.write_text(pretty_dumps(report) + "\n", encoding="utf-8", newline="\n")
    elif report_format == "markdown":
        out.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")
    else:
        raise ValueError("workbench format must be markdown or json")
    return {
        "external_execution": False,
        "format": report_format,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "ok": True,
        "out": str(out),
        "report": report,
        "schema_version": "ccr.workbench_report_write.v1",
        "settled": False,
    }


def _failure_report(
    mission_id: str,
    *,
    profile: Any,
    residual: dict[str, Any],
    target_ref: str,
    baseline_ref: str,
) -> dict[str, Any]:
    return {
        "accepted": False,
        "baseline_ref": baseline_ref,
        "blocking_residual_count": 1,
        "candidate_only_count": 0,
        "duplicate_count": 0,
        "external_execution": False,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "next_safe_action": {
            "command": f"ccr mission status --mission {mission_id} --json",
            "external_execution": False,
            "writes_runtime": False,
        },
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": False,
        "packet_status_summary": {status: 0 for status in PACKET_STATUSES},
        "positive_packet_count": 0,
        "profile": profile,
        "quarantined_count": 0,
        "repair_hints": [str(residual.get("repair_hint", ""))],
        "schema_version": "ccr.workbench_report.v1",
        "settled": False,
        "speculative_count": 0,
        "target_ref": target_ref,
        "top_residuals": [_residual_summary(residual)],
    }


def _is_duplicate(packet: dict[str, Any]) -> bool:
    extensions = packet.get("extensions")
    if isinstance(extensions, dict) and extensions.get("x_duplicate") is True:
        return True
    return bool(packet.get("duplicate_of"))


def _residual_refs(residual: dict[str, Any]) -> list[Any]:
    refs = residual.get("refs")
    return refs if isinstance(refs, list) else []


def _rank_residuals(residuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity = {"critical": 100, "high": 80, "medium": 50, "low": 20, "info": 5}
    return sorted(
        residuals,
        key=lambda item: (
            -severity.get(str(item.get("severity", "medium")), 50),
            str(item.get("kind", "")),
            str(item.get("residual_id", "")),
        ),
    )


def _residual_summary(residual: dict[str, Any]) -> dict[str, Any]:
    extensions = residual.get("extensions")
    finding_kind = (
        str(extensions.get("finding_kind", ""))
        if isinstance(extensions, dict) and extensions.get("finding_kind")
        else ""
    )
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
        "finding_kind": finding_kind,
        "kind": str(residual.get("kind", "other")),
        "repair_hint": str(residual.get("repair_hint", "")),
        "residual_id": str(residual.get("residual_id", "")),
        "severity": str(residual.get("severity", "medium")),
    }


def _repair_hints(top_residuals: list[dict[str, Any]]) -> list[str]:
    hints = [str(item.get("repair_hint", "")) for item in top_residuals]
    hints = [hint for hint in hints if hint]
    if hints:
        return hints
    return ["Run ccr mission next --compact for the next advisory action."]


def _validate_workbench_report(root: Path, report: dict[str, Any]) -> None:
    validation = validate_instance("workbench-report", report, root=root)
    if not validation.ok:
        messages = "; ".join(issue.message for issue in validation.errors)
        raise ValueError(f"invalid workbench report: {messages}")
