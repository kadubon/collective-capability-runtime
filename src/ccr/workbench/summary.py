# SPDX-License-Identifier: Apache-2.0
"""Workbench report summary builder."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.constants import PACKET_STATUSES
from ccr.io import json_file_name, pretty_dumps, write_json_atomic
from ccr.mission.model import MISSION_NON_CLAIMS, load_mission, load_mission_state, mission_path
from ccr.packets.store import iter_packets
from ccr.residuals.store import iter_residuals, linked_open_blocking_residuals
from ccr.workbench.markdown import render_markdown_report


def build_workbench_report(root: Path, *, mission_id: str) -> dict[str, Any]:
    """Build a mission workbench report without executing external actions."""

    if not mission_path(root, mission_id).exists():
        residual = {
            "blocking": True,
            "description": f"Mission not found: {mission_id}",
            "kind": "missing_mission",
            "residual_id": f"residual:missing-mission:{mission_id.replace(':', '_')}",
        }
        return {
            "accepted": False,
            "blocking_residual_count": 1,
            "candidate_only_count": 0,
            "external_execution": False,
            "mission_id": mission_id,
            "non_claims": list(MISSION_NON_CLAIMS),
            "ok": False,
            "positive_packet_count": 0,
            "schema_version": "ccr.workbench_report.v1",
            "settled": False,
            "top_residuals": [residual],
        }
    mission = load_mission(root, mission_id)
    state = load_mission_state(root, mission_id)
    packets = _mission_packets(root, state)
    packet_summary = {status: 0 for status in PACKET_STATUSES}
    for packet in packets:
        packet_summary[str(packet.get("status", "candidate"))] = (
            packet_summary.get(str(packet.get("status", "candidate")), 0) + 1
        )
    positive_packets = [
        packet
        for packet in packets
        if packet.get("status") in {"checked", "settled"}
        and not linked_open_blocking_residuals(root, str(packet.get("packet_id", "")))
    ]
    candidate_only_count = sum(
        1
        for packet in packets
        if packet.get("status") in {"raw", "proposed", "candidate", "provisional", "speculative"}
    )
    duplicate_count = sum(1 for packet in packets if _is_duplicate(packet))
    blocking_residuals = [
        residual for residual in iter_residuals(root, status="open") if residual.get("blocking")
    ]
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
    return report


def write_report_artifact(root: Path, report: dict[str, Any]) -> Path:
    """Write a JSON workbench report under the runtime root."""

    mission_id = str(report.get("mission_id", "mission:unknown"))
    path = root / "reports" / "workbench" / json_file_name(f"workbench:{mission_id}")
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
        "ok": True,
        "out": str(out),
        "report": report,
        "schema_version": "ccr.workbench_report_write.v1",
        "settled": False,
    }


def _mission_packets(root: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    refs = state.get("packet_refs")
    ref_set = {str(item) for item in refs} if isinstance(refs, list) else set()
    packets = iter_packets(root)
    if not ref_set:
        return packets
    return [packet for packet in packets if str(packet.get("packet_id", "")) in ref_set]


def _is_duplicate(packet: dict[str, Any]) -> bool:
    extensions = packet.get("extensions")
    if isinstance(extensions, dict) and extensions.get("x_duplicate") is True:
        return True
    return bool(packet.get("duplicate_of"))


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
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
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
