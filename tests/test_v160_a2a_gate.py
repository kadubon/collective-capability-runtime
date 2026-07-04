from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.gates.a2a import inspect_agent_card, preflight_handoff
from ccr.schemas.validation import validate_instance


def _write_json(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_a2a_gate_blocks_endpoint_without_provenance(tmp_path: Path) -> None:
    card = _write_json(
        tmp_path / "card.json",
        {
            "agent_id": "agent:remote",
            "declared_authority": {"scope": "read-only"},
            "endpoint": "https://example.invalid/a2a",
        },
    )

    report = inspect_agent_card(card)

    assert report["ok"] is False
    assert "missing_evidence" in report["blockers"]
    assert report["external_execution"] is False
    assert validate_instance("a2a-agent-card-report", report).ok is True


def test_a2a_gate_allows_fixture_endpoint_only_with_policy(tmp_path: Path) -> None:
    card = _write_json(
        tmp_path / "card.json",
        {
            "agent_id": "agent:remote",
            "declared_authority": {"scope": "read-only"},
            "endpoint": "https://example.invalid/a2a",
        },
    )
    policy = _write_json(tmp_path / "policy.json", {"allow_fixture_endpoint_provenance": True})

    report = inspect_agent_card(card, policy_path=policy, profile="development")

    assert report["ok"] is True
    assert report["residuals"][0]["blocking"] is False


def test_a2a_gate_blocks_production_missing_replay_nonce(tmp_path: Path, capsys: Any) -> None:
    card = _write_json(
        tmp_path / "card.json",
        {
            "agent_id": "agent:fixture",
            "capabilities": ["diagnostic_read"],
            "declared_authority": {"scope": "read-only"},
        },
    )
    handoff = _write_json(
        tmp_path / "handoff.json",
        {
            "agent_card_ref": "agent:fixture",
            "declared_authority": {"scope": "read-only"},
            "handoff_id": "handoff:fixture",
            "handoff_scope": "read-only",
            "idempotency_key": "idem",
        },
    )

    assert (
        main(
            [
                "a2a",
                "preflight-handoff",
                "--handoff",
                str(handoff),
                "--card",
                str(card),
                "--profile",
                "production",
                "--json",
            ]
        )
        != 0
    )
    report = json.loads(capsys.readouterr().out)

    assert "missing_evidence" in report["blockers"]
    assert report["delegated_tool_execution"] is False
    assert report["executed"] is False
    assert report["external_execution"] is False
    assert validate_instance("a2a-task-handoff-report", report).ok is True


def test_a2a_gate_blocks_agent_card_mismatch(tmp_path: Path) -> None:
    card = _write_json(
        tmp_path / "card.json",
        {"agent_id": "agent:a", "declared_authority": {"scope": "read-only"}},
    )
    handoff = _write_json(
        tmp_path / "handoff.json",
        {
            "agent_card_ref": "agent:b",
            "declared_authority": {"scope": "read-only"},
            "handoff_id": "handoff:fixture",
            "handoff_scope": "read-only",
            "idempotency_key": "idem",
            "replay_nonce": "nonce",
        },
    )

    report = preflight_handoff(handoff, card_path=card)

    assert report["ok"] is False
    assert "identity_gap" in report["blockers"]
