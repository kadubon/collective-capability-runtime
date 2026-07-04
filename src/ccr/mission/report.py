# SPDX-License-Identifier: Apache-2.0
"""Mission report facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.workbench.markdown import render_markdown_report
from ccr.workbench.summary import build_workbench_report


def write_mission_report(
    root: Path,
    *,
    mission_id: str,
    report_format: str,
    out: Path,
) -> dict[str, Any]:
    """Write a mission workbench report."""

    report = build_workbench_report(root, mission_id=mission_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "markdown":
        out.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")
    elif report_format == "json":
        from ccr.io import pretty_dumps

        out.write_text(pretty_dumps(report) + "\n", encoding="utf-8", newline="\n")
    else:
        raise ValueError("mission report format must be markdown or json")
    return {
        "external_execution": False,
        "format": report_format,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "ok": True,
        "out": str(out),
        "report": report,
        "schema_version": "ccr.mission_report_write.v1",
        "settled": False,
    }
