from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.io import read_json


def test_asi_quickstart_creates_local_non_executing_mission(
    tmp_path: Path,
    capsys: Any,
) -> None:
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "asi",
                "quickstart",
                "--profile",
                "development",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == "ccr.asi_quickstart.v1"
    assert payload["mission_id"] == "mission:quickstart"
    assert payload["settled"] is False
    assert payload["external_execution"] is False
    assert payload["next_safe_action"] == (
        "ccr mission next --mission mission:quickstart --compact --json"
    )
    assert "not_real_asi_proof" in payload["non_claims"]
    for key in ("mission", "target", "baseline", "loop_state", "report", "packet"):
        assert Path(payload["created"][key]).exists()

    state = read_json(tmp_path / "missions" / "state" / "mission_quickstart.json")
    assert state["external_execution"] is False
    assert state["settled"] is False
    assert state["packet_refs"] == ["packet:quickstart:mission-candidate"]


def test_asi_quickstart_mission_next_compact_is_advisory(
    tmp_path: Path,
    capsys: Any,
) -> None:
    assert main(["--root", str(tmp_path), "asi", "quickstart", "--json"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "next",
                "--mission",
                "mission:quickstart",
                "--compact",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == "ccr.mission_next.compact.v1"
    assert payload["mission_id"] == "mission:quickstart"
    assert payload["recommended_action"]["external_execution"] is False
    assert payload["recommended_action"]["writes_runtime"] is False
    assert payload["settled"] is False
