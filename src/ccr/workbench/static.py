# SPDX-License-Identifier: Apache-2.0
"""Static workbench export."""

from __future__ import annotations

import hashlib
import html
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import canonical_dumps, pretty_dumps, write_json_atomic
from ccr.mission.model import MISSION_NON_CLAIMS, load_mission, mission_path, mission_scope
from ccr.residuals.market import residual_market
from ccr.safe_io import safe_relative_display
from ccr.workbench.summary import build_workbench_report


def export_static_workbench(root: Path, *, mission_id: str, out: Path) -> dict[str, Any]:
    """Export a no-network static HTML workbench for one mission."""

    report = build_workbench_report(root, mission_id=mission_id)
    scope = mission_scope(root, mission_id)
    mission = _public_mission(root, mission_id)
    market = residual_market(root, mission_id=mission_id)
    packets = scope["packets"] if scope.get("ok") else []
    residuals = scope["residuals"] if scope.get("ok") else []
    out.mkdir(parents=True, exist_ok=True)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(data_dir / "workbench-report.json", report, overwrite=True)
    write_json_atomic(data_dir / "packets.json", _public_records(packets), overwrite=True)
    write_json_atomic(data_dir / "residuals.json", _public_records(residuals), overwrite=True)
    write_json_atomic(
        data_dir / "residual-market.json", _strip_absolute_paths(market), overwrite=True
    )
    write_json_atomic(data_dir / "mission.json", _strip_absolute_paths(mission), overwrite=True)
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
    (out / "phase.html").write_text(
        _page("Phase", _object_html("Mission phase boundary", _phase_summary(report, mission))),
        encoding="utf-8",
        newline="\n",
    )
    (out / "operations.html").write_text(
        _page(
            "Operations",
            _object_html("Operation boundary", _operation_summary(report, market)),
        ),
        encoding="utf-8",
        newline="\n",
    )
    html_files = [
        "index.html",
        "packets.html",
        "residuals.html",
        "phase.html",
        "operations.html",
    ]
    data_files = [
        "data/workbench-report.json",
        "data/packets.json",
        "data/residuals.json",
        "data/residual-market.json",
        "data/mission.json",
        "data/manifest.json",
    ]
    pre_manifest_files = [
        path for path in [*html_files, *data_files] if path != "data/manifest.json"
    ]
    manifest = {
        "data_files": data_files,
        "external_assets": False,
        "file_hashes": _file_hashes(out, pre_manifest_files),
        "html_files": html_files,
        "mission_id": mission_id,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "schema_version": "ccr.static_workbench_manifest.v1",
        "settled": False,
    }
    write_json_atomic(data_dir / "manifest.json", manifest, overwrite=True)
    file_hashes = _file_hashes(out, [*html_files, *data_files])
    report_id = stable_id("static-workbench", mission_id, report)
    return {
        "data_files": data_files,
        "external_assets": False,
        "external_execution": False,
        "file_hashes": file_hashes,
        "html_files": html_files,
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
<a href="phase.html">Phase</a>
<a href="operations.html">Operations</a>
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
    hashes = html.escape(_object_hash(report))
    return (
        f"<h1>CCR Workbench</h1><table>{body}</table>"
        f"<h2>Report hash source</h2><pre>{hashes}</pre>"
        f"<h2>Non-claims</h2><pre>{non_claims}</pre>"
    )


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


def _public_mission(root: Path, mission_id: str) -> dict[str, Any]:
    if not mission_path(root, mission_id).exists():
        return {
            "mission_id": mission_id,
            "ok": False,
            "schema_version": "ccr.static_workbench_missing_mission.v1",
        }
    mission = _strip_absolute_paths(load_mission(root, mission_id))
    return mission if isinstance(mission, dict) else {}


def _phase_summary(report: dict[str, Any], mission: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": report.get("accepted", False),
        "authority_envelope": mission.get("authority_envelope", {}),
        "baseline_ref": report.get("baseline_ref", ""),
        "blocking_residual_count": report.get("blocking_residual_count", 0),
        "external_execution": False,
        "hazard_envelope": mission.get("hazard_envelope", {}),
        "mission_id": report.get("mission_id", ""),
        "network_call_performed": False,
        "settled": False,
        "target_ref": report.get("target_ref", ""),
    }


def _operation_summary(report: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    return {
        "blocking_residual_count": report.get("blocking_residual_count", 0),
        "dispatch_performed": False,
        "external_execution": False,
        "network_call_performed": False,
        "operation_ready_is_not_execution": True,
        "physical_outcome_proven": False,
        "provider_dispatch_ready": False,
        "residual_market_count": market.get("residual_count", 0),
        "settled": False,
    }


def _object_html(title: str, value: Any) -> str:
    return f"<h1>{html.escape(title)}</h1><pre>{html.escape(pretty_dumps(value))}</pre>"


def _file_hashes(root: Path, relative_paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in relative_paths:
        path = root / relative
        if not path.exists() or not path.is_file():
            continue
        hashes[relative] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
    return hashes


def _object_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_dumps(value).encode('utf-8')).hexdigest()}"


def _strip_absolute_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _strip_absolute_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip_absolute_paths(item) for item in value]
    if isinstance(value, str) and (":\\" in value or value.startswith("/")):
        return Path(value).name
    return value
