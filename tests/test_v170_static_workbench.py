from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.mission.init import initialize_mission
from ccr.schemas.validation import validate_instance


def test_static_workbench_export_has_local_assets_only(
    runtime_root: Path, tmp_path: Path, capsys: Any
) -> None:
    init = initialize_mission(runtime_root, name="static")
    out = tmp_path / "site"

    assert (
        main(
            [
                "--root",
                str(runtime_root),
                "workbench",
                "export",
                "--mission",
                str(init["mission_id"]),
                "--format",
                "static-html",
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["external_assets"] is False
    assert (out / "index.html").exists()
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "http://" not in html
    assert "https://" not in html
    assert "<script" not in html.lower()
    assert validate_instance("static-workbench-export-report", report).ok is True
