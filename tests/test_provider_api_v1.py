from __future__ import annotations

import json

from ccr.cli import cmd_provider_execute, cmd_provider_import, cmd_verify
from ccr.packets.store import load_packet, submit_packet
from ccr.providers.http import HttpProvider
from ccr.residuals.store import iter_residuals
from tests.conftest import example_json


def test_http_provider_plan_performs_no_network_call(tmp_path):
    plan = HttpProvider().plan(
        action="webhook",
        payload={"accepted": True},
        root=tmp_path,
    )

    assert plan["dry_run"] is True
    assert plan["network_call_performed"] is False


def test_http_provider_execute_requires_explicit_config_allowance(tmp_path):
    report = HttpProvider().execute(
        action="webhook",
        payload={"accepted": True},
        root=tmp_path,
        config={"endpoint": "https://example.invalid", "method": "POST"},
    )

    assert report["ok"] is False
    assert report["network_call_performed"] is False


def test_provider_execute_cli_requires_execute_flag(runtime_root, tmp_path, capsys):
    config_path = tmp_path / "http-config.json"
    config_path.write_text(
        json.dumps(
            {
                "allow_execute": True,
                "byte_limit": 1024,
                "endpoint": "https://example.invalid",
                "method": "POST",
                "timeout_seconds": 1,
            }
        ),
        encoding="utf-8",
    )

    class Args:
        action = "webhook"
        config = str(config_path)
        execute = False
        file = None
        packet_id = None
        profile = "development"
        provider = "http"
        root = str(runtime_root)

    assert cmd_provider_execute(Args()) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["residual_ready"]["kind"] == "authority_gap"


def test_http_provider_import_materializes_residuals_and_task_hints(runtime_root, tmp_path):
    submit_packet(
        runtime_root,
        example_json("examples/phase_formation/packets/checked/packet.phase.integrator.json"),
    )
    report = example_json("examples/phase_formation/mock_http_report.json")
    report_path = tmp_path / "http_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    class Args:
        provider = "http"
        report = str(report_path)
        root = str(runtime_root)

    assert cmd_provider_import(Args()) == 0
    packet, _path, status = load_packet(runtime_root, "packet.phase.integrator")
    assert status == "checked"
    assert packet["verifier_reports"][-1]["provider"] == "http"
    residuals = list(iter_residuals(runtime_root, status="open"))
    assert any(item["kind"] == "candidate_only_reason" for item in residuals)
    assert any(item["kind"] == "settlement_blocker" for item in residuals)
    assert list((runtime_root / "tasks" / "open").glob("*.json"))


def test_pic_missing_returns_residual_ready_not_crash(runtime_root, monkeypatch, capsys):
    submit_packet(runtime_root, example_json("examples/minimal/packet.json"))

    class MissingPic:
        def availability(self):
            return {"available": False, "provider": "pic"}

        def plan_verify(self, packet, profile, packet_path):
            return {
                "packet_id": packet["packet_id"],
                "packet_path": packet_path,
                "profile": profile,
            }

    monkeypatch.setattr("ccr.cli.PicVerifierProvider", MissingPic)

    class Args:
        execute = False
        packet_id = "packet.minimal"
        profile = "development"
        provider = "pic"
        root = str(runtime_root)
        timeout = 60

    assert cmd_verify(Args()) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["residual_ready"]["kind"] == "provider_missing"
