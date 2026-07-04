from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main


def test_mission_runtime_init_ingest_next_and_markdown_report(
    tmp_path: Path,
    capsys: Any,
) -> None:
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "init",
                "--name",
                "demo",
                "--profile",
                "development",
                "--template",
                "local-asi-proxy",
                "--json",
            ]
        )
        == 0
    )
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["mission_id"] == "mission:demo"
    assert init_payload["external_execution"] is False

    source = tmp_path / "source.md"
    source.write_text(
        "# Mission note\n\nCCR preserves residuals as local protocol data.\n\n"
        "```text\nCCR creates real ASI.\n```\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "ingest",
                "--mission",
                "mission:demo",
                "--from",
                "markdown",
                "--input",
                str(source),
                "--json",
            ]
        )
        == 0
    )
    ingest_payload = json.loads(capsys.readouterr().out)
    assert ingest_payload["schema_version"] == "ccr.mission_ingest.v1"
    assert ingest_payload["mutated_runtime"] is True
    assert ingest_payload["external_execution"] is False
    assert ingest_payload["ingested_packet_ids"]

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "next",
                "--mission",
                "mission:demo",
                "--compact",
                "--json",
            ]
        )
        == 0
    )
    next_payload = json.loads(capsys.readouterr().out)
    assert next_payload["next_safe_action"] == (
        "ccr mission next --mission mission:demo --compact --json"
    )
    assert next_payload["settled"] is False

    report = tmp_path / "CCR_WORKBENCH.md"
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "report",
                "--mission",
                "mission:demo",
                "--format",
                "markdown",
                "--out",
                str(report),
            ]
        )
        == 0
    )
    report_payload = json.loads(capsys.readouterr().out)
    assert report_payload["ok"] is True
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Settled: false" in text
    assert "Provider output is evidence only" in text
