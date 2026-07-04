from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.extensions import make_packet
from ccr.io import read_json
from ccr.mission.ingest import ingest_mission
from ccr.mission.init import initialize_mission
from ccr.mission.model import load_mission_state, merge_state_refs, save_mission_state
from ccr.mission.status import mission_status
from ccr.packets.store import submit_packet
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.schemas.validation import validate_instance
from ccr.workbench.summary import build_workbench_report


def test_mission_scope_isolation(tmp_path: Path) -> None:
    initialize_mission(tmp_path, name="alpha")
    initialize_mission(tmp_path, name="beta")
    packet_alpha = _mission_packet("packet:alpha:checked", "mission:alpha", status="checked")
    packet_beta = _mission_packet("packet:beta:checked", "mission:beta", status="checked")
    submit_packet(tmp_path, packet_alpha)
    submit_packet(tmp_path, packet_beta)
    residual_alpha = build_residual(
        kind="settlement_blocker",
        description="Alpha-only blocker.",
        blocking=True,
        object_type="packet",
        object_id="packet:alpha:checked",
        refs=["packet:alpha:checked"],
        source="test",
        extensions={"x_ccr_mission_id": "mission:alpha"},
    )
    save_residual(tmp_path, residual_alpha)
    state_alpha = merge_state_refs(
        load_mission_state(tmp_path, "mission:alpha"),
        packet_refs=["packet:alpha:checked"],
        residual_refs=[str(residual_alpha["residual_id"])],
    )
    state_beta = merge_state_refs(
        load_mission_state(tmp_path, "mission:beta"),
        packet_refs=["packet:beta:checked"],
    )
    save_mission_state(tmp_path, state_alpha)
    save_mission_state(tmp_path, state_beta)

    report_alpha = build_workbench_report(tmp_path, mission_id="mission:alpha")
    report_beta = build_workbench_report(tmp_path, mission_id="mission:beta")
    status_beta = mission_status(tmp_path, mission_id="mission:beta")

    assert report_alpha["blocking_residual_count"] == 1
    assert report_beta["blocking_residual_count"] == 0
    assert report_beta["accepted"] is True
    assert status_beta["packet_counts"] == {"checked": 1}
    assert status_beta["residual_counts"] == {}


def test_report_fail_on_missing_mission(tmp_path: Path, capsys: Any) -> None:
    report_path = tmp_path / "missing.md"
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "report",
                "--mission",
                "mission:missing",
                "--out",
                str(report_path),
            ]
        )
        == 0
    )
    no_policy = json.loads(capsys.readouterr().out)
    assert no_policy["ok"] is True
    assert no_policy["report"]["accepted"] is False

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "mission",
                "report",
                "--mission",
                "mission:missing",
                "--out",
                str(report_path),
                "--fail-on",
                "missing_mission",
            ]
        )
        != 0
    )
    policy = json.loads(capsys.readouterr().out)
    assert policy["ok"] is False
    assert policy["policy_failures"] == ["missing_mission"]


def test_missing_mission_workbench_report_is_schema_valid(tmp_path: Path) -> None:
    report = build_workbench_report(tmp_path, mission_id="mission:missing")

    validation = validate_instance("workbench-report", report)

    assert report["ok"] is False
    assert validation.ok is True


def test_mission_ingest_preserves_all_residuals(tmp_path: Path) -> None:
    initialize_mission(tmp_path, name="residuals")
    source = tmp_path / "source.md"
    source.write_text(
        "CCR creates real ASI.\n\n"
        "CCR preserves residuals for review.\n\n"
        "CCR does not detect real ASI.\n",
        encoding="utf-8",
    )

    report = ingest_mission(
        tmp_path,
        mission_id="mission:residuals",
        source_format="markdown",
        input_path=source,
    )
    state = read_json(tmp_path / "missions" / "state" / "mission_residuals.json")

    assert report["ok"] is True
    assert report["overclaim_count"] == 1
    assert report["residual_ready_count"] >= 2
    assert len(report["residual_ids"]) == report["residual_ready_count"]
    assert sorted(state["residual_refs"]) == sorted(report["residual_ids"])


def test_mission_ingest_invalid_utf8_is_schema_valid_failure(tmp_path: Path) -> None:
    initialize_mission(tmp_path, name="bad-input")
    source = tmp_path / "bad.md"
    source.write_bytes(b"\xff\xfe not utf8")

    report = ingest_mission(
        tmp_path,
        mission_id="mission:bad-input",
        source_format="markdown",
        input_path=source,
    )
    validation = validate_instance("mission-run-report", report)

    assert report["ok"] is False
    assert report["network_call_performed"] is False
    assert validation.ok is True
    assert report["residual_ready"]["extensions"]["finding_kind"] == "input_decode_error"


def test_mission_ingest_unsupported_format_is_schema_valid_failure(tmp_path: Path) -> None:
    initialize_mission(tmp_path, name="bad-format")
    source = tmp_path / "source.txt"
    source.write_text("CCR preserves residuals.\n", encoding="utf-8")

    report = ingest_mission(
        tmp_path,
        mission_id="mission:bad-format",
        source_format="txt",
        input_path=source,
    )
    validation = validate_instance("mission-run-report", report)

    assert report["ok"] is False
    assert validation.ok is True
    assert report["residual_ready"]["extensions"]["finding_kind"] == "unsupported_source_format"


def _mission_packet(packet_id: str, mission_id: str, *, status: str) -> dict[str, Any]:
    packet = make_packet(
        packet_id=packet_id,
        summary=f"Scoped packet for {mission_id}.",
        claim_text=f"CCR has a scoped packet for {mission_id}. Evidence: test",
        packet_type="claim",
    )
    packet["status"] = status
    packet.setdefault("extensions", {})
    packet["extensions"]["x_ccr_mission_id"] = mission_id
    return packet
