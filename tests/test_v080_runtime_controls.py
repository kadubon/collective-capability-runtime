from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.extensions import (
    foundry_allocate,
    foundry_simulate_allocation,
    operation_dispatch,
    phase_acceleration_report,
    phase_capital_witness_import,
    phase_target_check,
    provider_circuit_open,
)


class _FakeDispatchProvider:
    provider_name = "fake"

    def __init__(self) -> None:
        self.executed = False

    def plan(self, *, action: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
        return {
            "action": action,
            "network_call_performed": False,
            "ok": True,
            "provider": self.provider_name,
        }

    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        root: Path,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        self.executed = True
        return {"network_call_performed": True, "ok": True}


def _ready_plan() -> dict[str, Any]:
    return {
        "constraints": {
            "allowed_commands": [],
            "requires_execute_flag": True,
            "requires_provider_config": True,
        },
        "executed": False,
        "execution_blockers": [],
        "non_claims": [],
        "operations": [],
        "plan_id": "plan:v080",
        "real_world_operation_ready": True,
        "residuals": [],
        "schema_version": "ccr.trc_operation_plan.v1",
        "settled": False,
    }


def test_capital_witness_import_is_idempotent(runtime_root: Path, tmp_path: Path) -> None:
    source = tmp_path / "capital.jsonl"
    witness = {
        "baseline_ref": "baseline:demo",
        "coordinate": "coord:x",
        "finality_ref": "finality:x",
        "finality_valid": True,
        "gauge_compatible": True,
        "hazard_constrained": True,
        "mission_valid": True,
        "raw_net_solvent": True,
        "signed_surplus_lower_bound": 2,
        "transport_ref": "transport:x",
        "transport_valid": True,
        "value_estimand_type": "causal",
        "witness_id": "witness:x",
    }
    source.write_text(json.dumps(witness) + "\n", encoding="utf-8")

    first = phase_capital_witness_import(runtime_root, file=source, provider="pic")
    second = phase_capital_witness_import(runtime_root, file=source, provider="pic")

    assert first["imported_witness_ids"] == ["witness:x"]
    assert second["duplicate_witness_ids"] == ["witness:x"]


def test_acceleration_report_fails_closed_without_baseline(runtime_root: Path) -> None:
    report = phase_acceleration_report(
        runtime_root,
        target={
            "authority_envelope": {"status": "approved"},
            "baseline_upper_envelope_ref": "baseline:missing",
            "capability_basis": ["capability:x"],
            "capability_envelope": {"status": "accepted"},
            "externality_law": {"status": "accepted"},
            "generated_law": {"status": "accepted"},
            "hazard_envelope": {"status": "accepted"},
            "horizon": "P7D",
            "mission_law": {"status": "accepted"},
            "raw_net_capital_floor": 0,
            "target_id": "target:v080",
            "target_set": {"thresholds": {"coord:x": 1}},
            "target_validity_certificate_ref": "tvc:1",
            "viability_set": {"status": "accepted"},
        },
        baseline={},
        capital_witnesses=[
            {
                "baseline_ref": "baseline:missing",
                "coordinate": "coord:x",
                "finality_ref": "finality:x",
                "finality_valid": True,
                "gauge_compatible": True,
                "hazard_constrained": True,
                "mission_valid": True,
                "raw_net_solvent": True,
                "signed_surplus_lower_bound": 10,
                "transport_ref": "transport:x",
                "transport_valid": True,
                "value_estimand_type": "proxy_only",
            }
        ],
    )

    assert report["certified_acceleration_candidate"] is False
    assert report["ok"] is False
    assert "missing_baseline_policy_class" in report["blockers"]
    assert "proxy_only_non_contributing" in report["blockers"]


def test_target_status_checks_fail_closed() -> None:
    report = phase_target_check(
        {
            "authority_envelope": {"status": "present"},
            "baseline_upper_envelope_ref": "baseline:demo",
            "capability_basis": ["capability:x"],
            "capability_envelope": {"status": "accepted"},
            "externality_law": {"status": "accepted"},
            "generated_law": {"status": "accepted"},
            "hazard_envelope": {"status": "accepted"},
            "horizon": "P7D",
            "mission_law": {"status": "accepted"},
            "raw_net_capital_floor": 0,
            "target_id": "target:status",
            "target_set": {"thresholds": {"coord:x": 1}},
            "target_validity_certificate_ref": "tvc:1",
            "viability_set": {"status": "accepted"},
        }
    )

    assert report["ok"] is False
    assert report["authority_ok"] is False
    assert "authority_envelope_not_approved" in report["blockers"]


def test_foundry_phase_response_allocation_is_advisory(runtime_root: Path) -> None:
    missing = foundry_allocate(runtime_root, strategy="phase-response")
    accepted = foundry_allocate(
        runtime_root,
        strategy="phase-response",
        response_report={
            "accepted": True,
            "blockers": [],
            "ok": True,
            "residuals": [],
            "schema_version": "pic.phase_response_control_step.v1",
            "settled": False,
            "utility_interval": [0.5, 0.5],
        },
    )

    assert missing["ok"] is False
    assert "response_report_required" in missing["blockers"]
    assert accepted["ok"] is True
    assert accepted["mutated_runtime"] is False
    assert accepted["allocation"]["evidence_acquisition_priority"] >= 70


def test_foundry_simulate_allocation_preserves_diagnostic_reserve() -> None:
    report = foundry_simulate_allocation(
        {
            "active_cuts": [
                {"cut_kind": "baseline_refresh_cut", "priority": 40},
                {"cut_kind": "capital_admission_cut", "priority": 80},
            ]
        },
        {"diagnostic_reserve_floor": 2, "total_effort": 10},
    )

    assert report["ok"] is True
    assert report["mutated_runtime"] is False
    assert report["diagnostic_reserve_preserved"] is True
    assert {item["cut_kind"] for item in report["allocations"]} == {
        "baseline_refresh_cut",
        "capital_admission_cut",
    }


def test_provider_circuit_blocks_operation_execute(
    runtime_root: Path,
    monkeypatch: Any,
) -> None:
    fake = _FakeDispatchProvider()

    import ccr.providers.registry as registry

    monkeypatch.setattr(registry, "get_provider", lambda name: fake)
    provider_circuit_open(runtime_root, provider="fake", reason="test cooldown")

    report = operation_dispatch(
        runtime_root,
        plan=_ready_plan(),
        provider_name="fake",
        config={
            "allow_execute": True,
            "allowed_provider_classes": ["fake"],
            "operator_approval_ref": "approval:test",
            "provider_class": "fake",
            "side_effect_policy": "controlled_provider_allowed",
        },
        execute=True,
    )

    assert report["ok"] is False
    assert report["network_call_performed"] is False
    assert report["residual_ready"]["kind"] == "provider_circuit_open"
    assert fake.executed is False
