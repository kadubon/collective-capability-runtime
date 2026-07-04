from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.schemas.validation import validate_instance
from tests.conftest import REPO_ROOT


def test_cross_repo_conformance_bundle_smoke(capsys: Any) -> None:
    bundle = REPO_ROOT / "examples" / "asi_proxy_mission_bundle"

    assert main(["conformance", "bundle", "--bundle", str(bundle), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["external_execution"] is False
    assert validate_instance("cross-repo-conformance-report", report).ok is True


def test_cross_repo_parity_blocks_pic_settlement(tmp_path: Path, capsys: Any) -> None:
    ccr_report = tmp_path / "ccr.json"
    pic_report = tmp_path / "pic.json"
    ccr_report.write_text(
        json.dumps({"ok": True, "schema_version": "ccr.report.v1", "settled": False}),
        encoding="utf-8",
    )
    pic_report.write_text(
        json.dumps({"ok": True, "schema_version": "pic.report.v1", "settled": True}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "conformance",
                "parity",
                "--ccr-report",
                str(ccr_report),
                "--pic-report",
                str(pic_report),
                "--json",
            ]
        )
        != 0
    )
    report = json.loads(capsys.readouterr().out)

    assert "settlement_blocker" in report["blockers"]
    assert report["pic_evidence_only"] is True
    assert validate_instance("parity-report", report).ok is True
