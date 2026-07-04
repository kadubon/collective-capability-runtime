from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.schemas.validation import validate_instance
from tests.conftest import REPO_ROOT

ACCEL_EXAMPLES = REPO_ROOT / "examples" / "asi_proxy_acceleration_bundle"


def test_mcp_gate_cli_smoke(capsys: Any) -> None:
    descriptor = ACCEL_EXAMPLES / "mcp_descriptor.good.json"
    invocation = ACCEL_EXAMPLES / "mcp_invocation.good.json"

    assert main(["mcp", "inspect-descriptor", "--file", str(descriptor), "--json"]) == 0
    descriptor_report = json.loads(capsys.readouterr().out)
    assert descriptor_report["ok"] is True
    assert validate_instance("mcp-tool-descriptor-report", descriptor_report).ok is True

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
        == 0
    )
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["executed"] is False
    assert preflight["network_call_performed"] is False
    assert validate_instance("mcp-tool-invocation-preflight", preflight).ok is True


def test_mcp_gate_blocks_descriptor_rug_pull(capsys: Any) -> None:
    descriptor = ACCEL_EXAMPLES / "mcp_descriptor.rug_pull.json"

    assert main(["mcp", "inspect-descriptor", "--file", str(descriptor), "--json"]) != 0
    report = json.loads(capsys.readouterr().out)

    assert report["ok"] is False
    assert "stale_source" in report["blockers"]
    assert "validation_error" in report["blockers"]


def test_a2a_gate_cli_smoke(capsys: Any) -> None:
    card = ACCEL_EXAMPLES / "a2a_agent_card.good.json"
    handoff = ACCEL_EXAMPLES / "a2a_handoff.good.json"

    assert main(["a2a", "inspect-card", "--file", str(card), "--json"]) == 0
    card_report = json.loads(capsys.readouterr().out)
    assert card_report["ok"] is True
    assert validate_instance("a2a-agent-card-report", card_report).ok is True

    assert (
        main(
            [
                "a2a",
                "preflight-handoff",
                "--handoff",
                str(handoff),
                "--card",
                str(card),
                "--json",
            ]
        )
        == 0
    )
    handoff_report = json.loads(capsys.readouterr().out)
    assert handoff_report["delegated_tool_execution"] is False
    assert validate_instance("a2a-task-handoff-report", handoff_report).ok is True


def test_provider_manifest_conformance_cli_smoke(capsys: Any) -> None:
    manifest = ACCEL_EXAMPLES / "provider_manifest.good.json"

    assert main(["provider", "manifest", "--file", str(manifest), "--json"]) == 0
    manifest_report = json.loads(capsys.readouterr().out)
    assert manifest_report["ok"] is True
    assert validate_instance("provider-manifest-report", manifest_report).ok is True

    assert main(["provider", "conformance", "--file", str(manifest), "--json"]) == 0
    conformance = json.loads(capsys.readouterr().out)
    assert conformance["ok"] is True
    assert conformance["conformance_profile"] == "ccr-provider-static-v1"
    assert validate_instance("provider-conformance-report", conformance).ok is True


def test_external_ingest_facade_cli_smoke(tmp_path: Path, capsys: Any) -> None:
    trace = tmp_path / "trace.md"
    trace.write_text("CCR preserves residuals. Evidence: trace.md\n", encoding="utf-8")

    assert main(["ingest", "trace", "--input", str(trace), "--json"]) == 0
    trace_report = json.loads(capsys.readouterr().out)
    assert trace_report["candidate_only"] is True
    assert trace_report["mutated_runtime"] is False

    assert main(["ingest", "repo", "--path", str(tmp_path), "--json"]) == 0
    repo_report = json.loads(capsys.readouterr().out)
    assert repo_report["candidate_only"] is True
    assert repo_report["network_call_performed"] is False
