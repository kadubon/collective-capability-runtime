# SPDX-License-Identifier: Apache-2.0
"""Markdown report rendering."""

from __future__ import annotations

from pathlib import Path

from ccr.reports.json_report import phase_report
from ccr.residuals.store import iter_residuals


def render_markdown_report(root: Path) -> str:
    """Render a residual-preserving human report."""

    report = phase_report(root)
    lines = [
        "# Collective Capability Runtime Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- PIC reports: `{report['pic_report_count']}`",
        f"- Open residuals: `{report['open_residual_count']}`",
        f"- Blocking residuals: `{report['blocking_residual_count']}`",
        "",
        "## Packet Counts",
        "",
    ]
    for status, count in report["packet_counts"].items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Task Counts", ""])
    for status, count in report["task_counts"].items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Residuals", ""])
    residuals = list(iter_residuals(root, status="open"))
    if not residuals:
        lines.append("- No open residuals.")
    for residual in residuals:
        marker = "blocking" if residual.get("blocking") else "non-blocking"
        lines.append(
            f"- `{residual.get('residual_id')}` [{marker}] "
            f"{residual.get('kind')}: {residual.get('description')}"
        )
    lines.extend(["", "## Non-Claims", ""])
    for item in report["non_claims"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)
