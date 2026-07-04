from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.schemas.validation import validate_instance


def test_operation_replay_manifest_and_verifier(tmp_path: Path, capsys: Any) -> None:
    dispatch = tmp_path / "dispatch.json"
    observation = tmp_path / "observation.json"
    manifest = tmp_path / "manifest.json"
    verifier = tmp_path / "verifier.json"
    dispatch.write_text(
        json.dumps({"executed": False, "provider_dispatch_ready": False}),
        encoding="utf-8",
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
    assert replay["executed"] is False
    assert replay["provider_dispatch_ready"] is False
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
    assert verification["settled"] is False
    assert validate_instance("observation-verification-report", verification).ok is True
