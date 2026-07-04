# SPDX-License-Identifier: Apache-2.0
"""Static workbench export."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import pretty_dumps, write_json_atomic
from ccr.mission.model import MISSION_NON_CLAIMS, mission_scope
from ccr.safe_io import safe_relative_display
from ccr.workbench.summary import build_workbench_report


def export_static_workbench(root: Path, *, mission_id: str, out: Path) -> dict[str, Any]:
    """Export a no-network static HTML workbench for one mission."""

    report = build_workbench_report(root, mission_id=mission_id)
    scope = mission_scope(root, mission_id)
    packets = scope["packets"] if scope.get("ok") else []
    residuals = scope["residuals"] if scope.get("ok") else []
    out.mkdir(parents=True, exist_ok=True)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(data_dir / "workbench-report.json", report, overwrite=True)
    write_json_atomic(data_dir / "packets.json", _public_records(packets), overwrite=True)
    write_json_atomic(data_dir / "residuals.json", _public_records(residuals), overwrite=True)
    (out / "index.html").write_text(
        _page(
            "CCR Workbench",
            _summary_html(report)
            + _table_html(
                "Top residuals",
                report.get("top_residuals", []),
                ["residual_id", "kind", "severity", "blocking", "description"],
            ),
        ),
        encoding="utf-8",
        newline="\n",
    )
    (out / "packets.html").write_text(
        _page(
            "Packets",
            _table_html("Packets", packets, ["packet_id", "status", "packet_type", "summary"]),
        ),
        encoding="utf-8",
        newline="\n",
    )
    (out / "residuals.html").write_text(
        _page(
            "Residuals",
            _table_html(
                "Residuals",
                residuals,
                ["residual_id", "kind", "severity", "blocking", "description"],
            ),
        ),
        encoding="utf-8",
        newline="\n",
    )
    report_id = stable_id("static-workbench", mission_id, report)
    return {
        "data_files": [
            "data/workbench-report.json",
            "data/packets.json",
            "data/residuals.json",
        ],
        "external_assets": False,
        "external_execution": False,
        "html_files": ["index.html", "packets.html", "residuals.html"],
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": True,
        "out": safe_relative_display(out, root=out.parent),
        "report_id": report_id,
        "schema_version": "ccr.static_workbench_export_report.v1",
        "settled": False,
    }


def _page(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #1f2937; }}
nav a {{ margin-right: 1rem; color: #14532d; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
th, td {{ border: 1px solid #d1d5db; padding: .45rem; text-align: left; vertical-align: top; }}
th {{ background: #f3f4f6; }}
code {{ background: #f3f4f6; padding: .1rem .25rem; }}
</style>
</head>
<body>
<nav>
<a href="index.html">Overview</a>
<a href="packets.html">Packets</a>
<a href="residuals.html">Residuals</a>
</nav>
{body}
</body>
</html>
"""


def _summary_html(report: dict[str, Any]) -> str:
    rows = [
        ("mission_id", report.get("mission_id", "")),
        ("profile", report.get("profile", "")),
        ("accepted", report.get("accepted", False)),
        ("settled", report.get("settled", False)),
        ("blocking_residual_count", report.get("blocking_residual_count", 0)),
        ("candidate_only_count", report.get("candidate_only_count", 0)),
    ]
    body = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in rows
    )
    non_claims = html.escape(pretty_dumps(report.get("non_claims", [])))
    return f"<h1>CCR Workbench</h1><table>{body}</table><h2>Non-claims</h2><pre>{non_claims}</pre>"


def _table_html(title: str, rows: Any, columns: list[str]) -> str:
    records = rows if isinstance(rows, list) else []
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = ""
    for row in records:
        if not isinstance(row, dict):
            continue
        body += "<tr>"
        for column in columns:
            body += f"<td>{html.escape(str(row.get(column, '')))}</td>"
        body += "</tr>"
    return (
        f"<h1>{html.escape(title)}</h1><table><thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _public_records(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    safe: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        safe.append(_strip_absolute_paths(record))
    return safe


def _strip_absolute_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _strip_absolute_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip_absolute_paths(item) for item in value]
    if isinstance(value, str) and (":\\" in value or value.startswith("/")):
        return Path(value).name
    return value
