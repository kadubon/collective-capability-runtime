from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.schemas.validation import validate_instance
from tests.conftest import REPO_ROOT


def test_operation_replay_manifest_and_verifier(tmp_path: Path, capsys: Any) -> None:
    dispatch = tmp_path / "dispatch.json"
    observation = tmp_path / "observation.json"
    manifest = tmp_path / "manifest.json"
    verifier = tmp_path / "verifier.json"
    dispatch.write_text(
        json.dumps({"executed": True, "provider_dispatch_ready": True}), encoding="utf-8"
    )
    observation.write_text(
        json.dumps(
            {
                "accepted": True,
                "hazard_followup_complete": True,
                "incident_unresolved": False,
                "rollback_verified": True,
            }
        ),
        encoding="utf-8",
    )
    verifier.write_text(
        json.dumps(
            {
                "accepted": True,
                "hazard_followup_complete": True,
                "incident_unresolved": False,
                "rollback_verified": True,
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "operation",
                "replay-manifest",
                "--dispatch-report",
                str(dispatch),
                "--observation",
                str(observation),
                "--out",
                str(manifest),
                "--json",
            ]
        )
        == 0
    )
    replay = json.loads(capsys.readouterr().out)
    assert replay["executed"] is True
    assert replay["external_execution"] is False
    assert replay["physical_outcome_proven"] is False
    assert replay["provider_dispatch_ready"] is False
    assert replay["source_dispatch_executed"] is True
    assert manifest.exists()
    assert validate_instance("operation-replay-manifest", replay).ok is True

    assert (
        main(
            [
                "operation",
                "verify-observation",
                "--manifest",
                str(manifest),
                "--verifier",
                str(verifier),
                "--json",
            ]
        )
        == 0
    )
    verification = json.loads(capsys.readouterr().out)
    assert verification["ok"] is True
    assert verification["physical_outcome_proven"] is False
    assert verification["settled"] is False
    assert validate_instance("observation-verification-report", verification).ok is True


def test_operation_verifier_rejects_dynamic_code(tmp_path: Path, capsys: Any) -> None:
    manifest = tmp_path / "manifest.json"
    verifier = tmp_path / "verifier.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_id": "operation-replay:test",
                "residual_ready": [],
                "schema_version": "ccr.operation_replay_manifest.v1",
            }
        ),
        encoding="utf-8",
    )
    verifier.write_text(
        json.dumps(
            {
                "accepted": True,
                "command": "python verifier.py",
                "hazard_followup_complete": True,
                "incident_unresolved": False,
                "rollback_verified": True,
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "operation",
                "verify-observation",
                "--manifest",
                str(manifest),
                "--verifier",
                str(verifier),
                "--json",
            ]
        )
        != 0
    )
    verification = json.loads(capsys.readouterr().out)
    assert "authority_gap" in verification["blockers"]
    assert verification["physical_outcome_proven"] is False
    assert validate_instance("observation-verification-report", verification).ok is True


def test_operation_replay_example_fixtures_smoke(tmp_path: Path, capsys: Any) -> None:
    fixture_root = REPO_ROOT / "examples" / "asi_proxy_acceleration_bundle"
    manifest = tmp_path / "replay-manifest.json"

    assert (
        main(
            [
                "operation",
                "replay-manifest",
                "--dispatch-report",
                str(fixture_root / "dispatch_report.example.json"),
                "--observation",
                str(fixture_root / "observation.example.json"),
                "--out",
                str(manifest),
                "--json",
            ]
        )
        == 0
    )
    replay = json.loads(capsys.readouterr().out)
    assert replay["executed"] is True
    assert replay["physical_outcome_proven"] is False

    assert (
        main(
            [
                "operation",
                "verify-observation",
                "--manifest",
                str(manifest),
                "--verifier",
                str(fixture_root / "observation_verifier.good.json"),
                "--json",
            ]
        )
        == 0
    )
    verification = json.loads(capsys.readouterr().out)
    assert verification["ok"] is True
    assert verification["physical_outcome_proven"] is False
