from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ccr.bundles.validate import validate_bundle
from ccr.claims.audit import audit_claim_file
from ccr.cli import main
from ccr.io import read_json, write_json_atomic
from ccr.schemas.validation import validate_instance
from ccr.workbench.markdown import render_markdown_report
from tests.conftest import REPO_ROOT


def test_claim_overclaim_matrix(tmp_path: Path) -> None:
    source = tmp_path / "claims.md"
    source.write_text(
        "\n".join(
            [
                "CCR is real ASI.",
                "CCR detects real ASI.",
                "CCR creates real ASI.",
                "CCR updates model weights.",
                "PIC acceptance settles CCR.",
                "Provider output is a settlement oracle.",
                "CCR execution_available means executed.",
                "CCR preflight means dispatch.",
                "CCR physical readiness proves physical outcome.",
                "CCR cache hit is proof.",
                "CCR index hit is proof.",
                "CCR safe command means authority.",
                "CCR MCP descriptor grants authority.",
                "CCR A2A handoff grants delegated authority.",
                "CCR conformance report proves settlement.",
                "CCR observation verifier proves physical outcome.",
                "CCR provider registry grants authority.",
                "CCR does not detect real ASI.",
                "CCR conformance report is evidence only and not settlement.",
                "CCR observation verifier must not be physical outcome proof.",
            ]
        ),
        encoding="utf-8",
    )

    report = audit_claim_file(source)

    assert report["ok"] is False
    assert report["overclaim_count"] == 17
    assert "CCR does not detect real ASI." in report["non_claims"]
    assert "CCR conformance report is evidence only and not settlement." in report["non_claims"]
    assert "CCR observation verifier must not be physical outcome proof." in report["non_claims"]


def test_claim_invalid_inputs_return_residual_ready(tmp_path: Path) -> None:
    binary = tmp_path / "binary.md"
    binary.write_bytes(b"\x00\x01\x02")
    invalid_utf8 = tmp_path / "invalid.md"
    invalid_utf8.write_bytes(b"\xff\xfe invalid")

    binary_report = audit_claim_file(binary)
    invalid_report = audit_claim_file(invalid_utf8)

    assert binary_report["ok"] is False
    assert binary_report["residual_ready"][0]["extensions"]["finding_kind"] == "input_binary"
    assert invalid_report["ok"] is False
    assert invalid_report["residual_ready"][0]["extensions"]["finding_kind"] == "input_decode_error"


def test_claim_audit_fail_on_policies(tmp_path: Path, capsys: Any) -> None:
    source = tmp_path / "claims.md"
    source.write_text("CCR coordinates packets.\n", encoding="utf-8")

    assert (
        main(
            [
                "claim",
                "audit",
                "--input",
                str(source),
                "--fail-on",
                "unsupported_claim",
                "--json",
            ]
        )
        != 0
    )
    report = json.loads(capsys.readouterr().out)
    assert "unsupported_claim" in report["policy_failures"]

    broken = tmp_path / "broken.md"
    broken.write_bytes(b"\x00\x01")
    assert (
        main(
            [
                "claim",
                "audit",
                "--input",
                str(broken),
                "--fail-on",
                "schema_error",
                "--json",
            ]
        )
        != 0
    )
    broken_report = json.loads(capsys.readouterr().out)
    assert "schema_error" in broken_report["policy_failures"]


def test_bundle_validate_rejects_path_traversal_ref(tmp_path: Path) -> None:
    bundle = _copy_quickstart_bundle(tmp_path)
    bundle_json = read_json(bundle / "bundle.json")
    bundle_json["files"] = ["../outside.json"]
    write_json_atomic(bundle / "bundle.json", bundle_json, overwrite=True)

    report = validate_bundle(bundle)
    validation = validate_instance("bundle-validate-report", report)

    assert report["ok"] is False
    assert "path_traversal" in report["blockers"]
    assert validation.ok is True


def test_bundle_validate_rejects_malformed_json(tmp_path: Path) -> None:
    bundle = _copy_quickstart_bundle(tmp_path)
    (bundle / "broken.json").write_text("{", encoding="utf-8")

    report = validate_bundle(bundle)
    validation = validate_instance("bundle-validate-report", report)

    assert report["ok"] is False
    assert "malformed_json" in report["blockers"]
    assert validation.ok is True


def test_bundle_validate_requires_schema_valid_target_and_reference_closure(
    tmp_path: Path,
) -> None:
    bundle = _copy_quickstart_bundle(tmp_path)
    target = read_json(bundle / "target.json")
    del target["capability_basis"]
    write_json_atomic(bundle / "target.json", target, overwrite=True)
    bundle_json = read_json(bundle / "bundle.json")
    bundle_json["baseline_ref"] = "baseline:missing"
    write_json_atomic(bundle / "bundle.json", bundle_json, overwrite=True)

    report = validate_bundle(bundle)

    assert report["ok"] is False
    assert "missing_target" in report["blockers"]
    assert "schema_validation_failed" in report["blockers"]
    assert "unresolved_reference" in report["blockers"]


def test_markdown_report_escapes_controlled_text() -> None:
    markdown = render_markdown_report(
        {
            "accepted": False,
            "baseline_ref": "baseline:<x>",
            "blocking_residual_count": 1,
            "candidate_only_count": 0,
            "duplicate_count": 0,
            "external_execution": False,
            "mission_id": "mission:<script>",
            "network_call_performed": False,
            "next_safe_action": {
                "command": "ccr mission next --mission mission:test --compact --json",
                "external_execution": False,
                "writes_runtime": False,
            },
            "non_claims": ["CCR does not detect real ASI."],
            "packet_status_summary": {},
            "positive_packet_count": 0,
            "profile": "development",
            "quarantined_count": 0,
            "settled": False,
            "speculative_count": 0,
            "target_ref": "target:<x>",
            "top_residuals": [
                {
                    "blocking": True,
                    "description": "<script>alert(1)</script>\n| not a table",
                    "kind": "validation_error",
                    "residual_id": "residual:test",
                }
            ],
        }
    )

    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "| not a table" in markdown
    assert "\n| not a table" not in markdown


def _copy_quickstart_bundle(tmp_path: Path) -> Path:
    source = REPO_ROOT / "examples" / "asi_proxy_mission_bundle"
    destination = tmp_path / "bundle"
    shutil.copytree(source, destination)
    return destination
