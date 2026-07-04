# SPDX-License-Identifier: Apache-2.0
"""Markdown rendering for workbench reports."""

from __future__ import annotations

from typing import Any


def render_markdown_report(report: dict[str, Any]) -> str:
    """Render a deterministic human-readable workbench report."""

    next_action = report.get("next_safe_action")
    command = (
        str(next_action.get("command", "")) if isinstance(next_action, dict) else str(next_action)
    )
    lines = [
        "# CCR Workbench Report",
        "",
        f"Mission: {report.get('mission_id', '')}",
        f"Profile: {report.get('profile', '')}",
        f"Target: {report.get('target_ref', '')}",
        f"Baseline: {report.get('baseline_ref', '')}",
        f"Accepted: {_bool(report.get('accepted', False))}",
        f"Settled: {_bool(report.get('settled', False))}",
        f"External execution: {_bool(report.get('external_execution', False))}",
        "",
        "## Packet Status",
    ]
    packet_summary = report.get("packet_status_summary")
    if isinstance(packet_summary, dict):
        for status in sorted(packet_summary):
            lines.append(f"- {status}: {packet_summary[status]}")
    lines.extend(
        [
            f"- positive contribution packets: {report.get('positive_packet_count', 0)}",
            f"- candidate-only packets: {report.get('candidate_only_count', 0)}",
            f"- duplicate packets: {report.get('duplicate_count', 0)}",
            f"- speculative packets: {report.get('speculative_count', 0)}",
            f"- quarantined packets: {report.get('quarantined_count', 0)}",
            "",
            "## Residuals",
            f"Blocking residuals: {report.get('blocking_residual_count', 0)}",
        ]
    )
    top_residuals = report.get("top_residuals")
    if isinstance(top_residuals, list) and top_residuals:
        for residual in top_residuals:
            if isinstance(residual, dict):
                lines.append(
                    "- "
                    + str(residual.get("residual_id", ""))
                    + " "
                    + str(residual.get("kind", ""))
                    + ": "
                    + str(residual.get("description", ""))
                )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Next Safe Action",
            f"`{command}`",
            "",
            "## Boundaries",
            "- Provider output is evidence only, not settlement.",
            "- Operation readiness is not execution.",
            "- Physical readiness is not physical outcome proof.",
            "",
            "## Non-Claims",
        ]
    )
    for item in report.get("non_claims", []):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def _bool(value: Any) -> str:
    return "true" if bool(value) else "false"
