from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.io import json_file_name, read_json
from ccr.mission.init import initialize_mission


def test_ingest_trace_writes_mission_candidates_and_redacts_secret(
    runtime_root: Path, tmp_path: Path, capsys: Any
) -> None:
    init = initialize_mission(runtime_root, name="ingest")
    trace = tmp_path / "trace.md"
    trace.write_text(
        "CCR can preserve residuals.\napi_key=SECRET-12345\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--root",
                str(runtime_root),
                "ingest",
                "trace",
                "--input",
                str(trace),
                "--mission",
                str(init["mission_id"]),
                "--write-candidates",
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["mutated_runtime"] is True
    assert report["ingested_packet_ids"]
    packet_path = (
        runtime_root
        / "packets"
        / "candidate"
        / json_file_name(str(report["ingested_packet_ids"][0]))
    )
    packet = read_json(packet_path)
    assert packet["extensions"]["x_ccr_mission_id"] == init["mission_id"]
    assert "SECRET-12345" not in json.dumps(packet)


def test_ingest_repo_skips_binary_without_execution(
    runtime_root: Path, tmp_path: Path, capsys: Any
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("CCR candidate claim.\n", encoding="utf-8")
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02")

    assert main(["--root", str(runtime_root), "ingest", "repo", "--path", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["candidate_only"] is True
    assert report["mutated_runtime"] is False
    assert report["network_call_performed"] is False
    assert any(residual["blocking"] is False for residual in report["residual_ready"])
