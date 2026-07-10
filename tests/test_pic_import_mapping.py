from __future__ import annotations

import json

from ccr.adapters.pic import PicVerifierProvider
from ccr.cli import cmd_integrate, cmd_provider_import
from ccr.packets.store import load_packet, submit_packet
from ccr.residuals.store import iter_residuals
from tests.conftest import example_json


def test_accepted_true_settled_false_imports_not_settled():
    report = {
        "accepted": True,
        "packet_id": "packet.pic.interop",
        "settled": False,
    }
    normalized = PicVerifierProvider().normalize_report(report)
    assert normalized["ccr_status"] == "checked"
    assert normalized["ccr_status"] != "settled"


def test_workflow_usable_and_pic_settled_true_never_settle_ccr_directly():
    report = {
        "packet_id": "packet.pic.interop",
        "settled": True,
        "workflow_usable": True,
    }

    normalized = PicVerifierProvider().normalize_report(report)

    assert normalized["accepted"] is True
    assert normalized["settled"] is True
    assert normalized["settled_candidate"] is True
    assert normalized["ccr_status"] == "checked"
    assert normalized["ccr_status"] != "settled"


def test_pic_v050_phase_plan_fields_are_preserved():
    report = example_json("examples/pic_interop/pic_v050_phase_plan_report.json")

    normalized = PicVerifierProvider().normalize_report(report)

    assert normalized["workflow_usable"] is True
    assert normalized["bottlenecks"]
    assert normalized["cannot_promote_because"]
    assert normalized["phase_gap_vector"]["verified_composability"] == 0.5
    assert normalized["ccr_status"] == "provisional"


def test_safe_commands_become_task_hints_not_executed(runtime_root, tmp_path):
    packet = example_json("examples/pic_interop/packet_for_pic.json")
    submit_packet(runtime_root, packet)
    report = example_json("examples/pic_interop/pic_import_example.json")
    report_path = tmp_path / "pic_report.json"

    report_path.write_text(json.dumps(report), encoding="utf-8")

    class Args:
        root = str(runtime_root)
        report = str(report_path)

    assert cmd_integrate(Args()) == 0
    updated, _path, status = load_packet(runtime_root, "packet.pic.interop")
    assert status == "candidate"
    assert updated["status"] == "candidate"
    residuals = list(iter_residuals(runtime_root, status="open"))
    assert any(item["kind"] == "candidate_only_reason" for item in residuals)
    assert any(item["kind"] == "settlement_blocker" for item in residuals)
    tasks = list((runtime_root / "tasks" / "open").glob("*.json"))
    assert tasks


def test_pic_provider_import_preserves_v050_blockers_and_safe_commands(runtime_root, tmp_path):
    packet = example_json("examples/pic_interop/packet_for_pic.json")
    submit_packet(runtime_root, packet)
    report = example_json("examples/pic_interop/pic_v050_collective_certificate_candidate.json")
    report_path = tmp_path / "pic_v050_certificate.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    class Args:
        provider = "pic"
        report = str(report_path)
        root = str(runtime_root)

    assert cmd_provider_import(Args()) == 0
    updated, _path, status = load_packet(runtime_root, "packet.pic.interop")
    assert status == "candidate"
    assert updated["status"] == "candidate"
    assert updated["verifier_reports"][-1]["provider"] == "pic"
    assert updated["verifier_reports"][-1]["settled"] is True
    residuals = list(iter_residuals(runtime_root, status="open"))
    descriptions = "\n".join(item["description"] for item in residuals)
    assert "cannot promote because" in descriptions
    assert "missing obligation" in descriptions
    tasks = list((runtime_root / "tasks" / "open").glob("*.json"))
    assert tasks
