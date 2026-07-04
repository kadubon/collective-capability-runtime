from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.mission.init import initialize_mission
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.schemas.validation import validate_instance


def test_residual_market_bounty_and_diff(runtime_root: Path, tmp_path: Path, capsys: Any) -> None:
    init = initialize_mission(runtime_root, name="market")
    mission_id = str(init["mission_id"])
    residual = build_residual(
        kind="missing_evidence",
        description="Need verifier evidence.",
        blocking=True,
        object_type="runtime",
        object_id=mission_id,
        severity="high",
        refs=[mission_id],
        source="test",
        repair_hint="Collect static verifier evidence.",
        extensions={"x_ccr_mission_id": mission_id},
    )
    save_residual(runtime_root, residual)

    assert (
        main(
            [
                "--root",
                str(runtime_root),
                "residual",
                "market",
                "--mission",
                mission_id,
                "--json",
            ]
        )
        == 0
    )
    before = json.loads(capsys.readouterr().out)
    assert before["market"][0]["recommended_role"] == "librarian"
    assert validate_instance("residual-market", before).ok is True

    assert (
        main(
            [
                "--root",
                str(runtime_root),
                "residual",
                "bounty",
                "--residual",
                str(residual["residual_id"]),
                "--mission",
                mission_id,
                "--emit",
                "task",
                "--json",
            ]
        )
        == 0
    )
    bounty = json.loads(capsys.readouterr().out)
    assert bounty["mutated_runtime"] is True
    assert bounty["emitted_task_id"]
    assert validate_instance("residual-bounty", bounty).ok is True

    before_path = tmp_path / "before.json"
    after_path = tmp_path / "after.json"
    before_path.write_text(json.dumps(before), encoding="utf-8")
    after_report: dict[str, Any] = {**before, "market": []}
    after_path.write_text(json.dumps(after_report), encoding="utf-8")
    assert (
        main(
            [
                "residual",
                "diff",
                "--before",
                str(before_path),
                "--after",
                str(after_path),
                "--json",
            ]
        )
        == 0
    )
    diff = json.loads(capsys.readouterr().out)
    assert str(residual["residual_id"]) in diff["removed_residual_ids"]
    assert validate_instance("residual-diff", diff).ok is True
