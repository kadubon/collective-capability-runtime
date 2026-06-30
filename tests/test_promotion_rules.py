from __future__ import annotations

from ccr.packets.promotion import promote_packet
from ccr.packets.store import submit_packet
from ccr.residuals.store import iter_residuals
from tests.conftest import example_json


def test_candidate_cannot_become_settled_without_verifier(runtime_root):
    packet = example_json("examples/minimal/packet.json")
    submit_packet(runtime_root, packet)
    result = promote_packet(runtime_root, packet["packet_id"], target="settled")
    assert result["ok"] is False
    assert any("invalid status transition" in reason for reason in result["reasons"])
    residuals = list(iter_residuals(runtime_root, status="open"))
    assert residuals


def test_blocking_residual_prevents_settled_promotion(runtime_root):
    packet = example_json("examples/minimal/packet.json")
    packet["status"] = "checked"
    packet["verifier_reports"] = [
        {
            "accepted": True,
            "blocking_residuals": [],
            "provider": "pic",
            "ref": "reports/pic/example.json",
            "report_id": "report.pic.accepted",
            "settled": False,
        }
    ]
    packet["extensions"] = {
        "settlement": {
            "integration_policy_passed": True,
            "lineage_closed": True,
            "target_satisfied": True,
        }
    }
    packet["residuals"] = [
        {
            "blocking": True,
            "description": "Remaining blocker.",
            "kind": "settlement_blocker",
            "repair_hint": "Resolve blocker.",
            "residual_id": "residual.blocking",
            "severity": "high",
        }
    ]
    submit_packet(runtime_root, packet)
    result = promote_packet(runtime_root, packet["packet_id"], target="settled")
    assert result["ok"] is False
    assert "blocking residuals prevent settlement" in result["reasons"]
