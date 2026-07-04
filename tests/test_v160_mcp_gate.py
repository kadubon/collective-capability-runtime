from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.gates.mcp import inspect_descriptor
from ccr.schemas.validation import validate_instance


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_mcp_gate_blocks_approved_hash_mismatch(tmp_path: Path) -> None:
    descriptor = _write_json(
        tmp_path / "descriptor.json",
        {
            "egress_policy": "none",
            "server_id": "fixture",
            "side_effect_class": "read_only",
            "tool_name": "read",
        },
    )

    report = inspect_descriptor(descriptor, approved_hash="sha256:bad")

    assert report["ok"] is False
    assert "stale_source" in report["blockers"]
    assert report["external_execution"] is False
    assert report["provider_dispatch_ready"] is False
    assert validate_instance("mcp-tool-descriptor-report", report).ok is True


def test_mcp_gate_blocks_descriptor_report_drift_and_tool_mismatch(
    tmp_path: Path, capsys: Any
) -> None:
    descriptor = _write_json(
        tmp_path / "descriptor.json",
        {
            "egress_policy": "none",
            "server_id": "fixture",
            "side_effect_class": "read_only",
            "tool_name": "read",
        },
    )
    invocation = _write_json(
        tmp_path / "invocation.json",
        {"dispatch": False, "execute": False, "tool_name": "write"},
    )
    descriptor_report = _write_json(
        tmp_path / "descriptor-report.json",
        {
            "accepted": True,
            "descriptor_hash": "sha256:old",
            "ok": True,
            "schema_version": "ccr.mcp_tool_descriptor_report.v1",
        },
    )

    assert (
        main(
            [
                "mcp",
                "preflight",
                "--descriptor",
                str(descriptor),
                "--invocation",
                str(invocation),
                "--descriptor-report",
                str(descriptor_report),
                "--json",
            ]
        )
        != 0
    )
    report = json.loads(capsys.readouterr().out)

    assert "stale_source" in report["blockers"]
    assert "validation_error" in report["blockers"]
    assert report["executed"] is False
    assert report["external_execution"] is False
    assert report["network_call_performed"] is False
    assert report["provider_dispatch_ready"] is False
    assert validate_instance("mcp-tool-invocation-preflight", report).ok is True


def test_mcp_gate_blocks_legacy_boolean_disagreement(tmp_path: Path) -> None:
    descriptor = _write_json(
        tmp_path / "descriptor.json",
        {
            "egress_policy": "none",
            "server_id": "fixture",
            "side_effect_class": "read_only",
            "tool_name": "read",
        },
    )
    invocation = _write_json(
        tmp_path / "invocation.json",
        {
            "accepted": True,
            "dispatch": False,
            "execute": False,
            "ok": False,
            "tool_name": "read",
        },
    )

    assert (
        main(
            [
                "mcp",
                "preflight",
                "--descriptor",
                str(descriptor),
                "--invocation",
                str(invocation),
                "--json",
            ]
        )
        != 0
    )
