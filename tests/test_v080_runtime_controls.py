from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.extensions import (
    foundry_allocate,
    foundry_simulate_allocation,
    operation_dispatch,
    operation_observe,
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


def _ready_preflight(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "accepted": True,
        "executed": False,
        "execution_blockers": [],
        "ok": True,
        "operation_plan": plan,
        "operation_ready": True,
        "physical_dispatch_ready": False,
        "provider": "fake",
        "provider_dispatch_ready": True,
        "residuals": [],
        "schema_version": "ccr.trc_operation_preflight.v1",
        "settled": False,
        "side_effect_policy": "controlled_provider_allowed",
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


def test_operation_dispatch_dry_run_is_not_preflighted(
    runtime_root: Path,
    monkeypatch: Any,
) -> None:
    fake = _FakeDispatchProvider()

    import ccr.providers.registry as registry

    monkeypatch.setattr(registry, "get_provider", lambda name: fake)

    report = operation_dispatch(runtime_root, plan=_ready_plan(), provider_name="fake")

    assert report["ok"] is True
    assert report["mode"] == "dry_run"
    assert report["dispatchable"] is False
    assert report["validation_status"] == "not_preflighted"
    assert report["requires_preflight"] is True
    assert report["requires_execute"] is True
    assert report["executed"] is False
    assert report["network_call_performed"] is False
    assert fake.executed is False


def test_operation_dispatch_dry_run_preflight_validation(
    runtime_root: Path,
    monkeypatch: Any,
) -> None:
    fake = _FakeDispatchProvider()
    plan = _ready_plan()

    import ccr.providers.registry as registry

    monkeypatch.setattr(registry, "get_provider", lambda name: fake)

    valid = operation_dispatch(
        runtime_root,
        plan=plan,
        provider_name="fake",
        config={"allow_execute": True},
        preflight=_ready_preflight(plan),
    )
    blocked_preflight = {**_ready_preflight(plan), "provider_dispatch_ready": False}
    blocked = operation_dispatch(
        runtime_root,
        plan=plan,
        provider_name="fake",
        config={"allow_execute": True},
        preflight=blocked_preflight,
    )

    assert valid["mode"] == "dry_run_preflight_validation"
    assert valid["dispatchable"] is False
    assert valid["dispatchable_if_execute"] is True
    assert valid["validation_status"] == "dispatchable_if_execute"
    assert valid["network_call_performed"] is False
    assert blocked["ok"] is False
    assert blocked["validation_status"] == "blocked"
    assert "preflight_not_dispatch_ready" in blocked["execution_blockers"]
    assert fake.executed is False


def test_operation_observe_reports_required_residual_taxonomy() -> None:
    report = operation_observe(
        dispatch_report={"executed": False, "provider": "fake"},
        observation={
            "physical_actuation_observed": True,
            "physical_outcome_observed": True,
        },
    )
    kinds = {item["kind"] for item in report["residuals"]}

    assert report["dispatch_executed"] is False
    assert report["physical_outcome_proven"] is False
    assert report["observation_residual_count"] == len(report["residuals"])
    assert "dispatch_report_not_executed" in kinds
    assert "observation_verifier_required" in kinds
    assert "physical_outcome_verifier_required" in kinds
    assert "incident_review_required" in kinds
    assert report["repair_task_candidates"]


def test_acceleration_report_exposes_interval_candidate(runtime_root: Path) -> None:
    report = phase_acceleration_report(
        runtime_root,
        target={
            "authority_envelope": {"status": "approved"},
            "baseline_upper_envelope_ref": "baseline:demo",
            "capability_basis": ["capability:x"],
            "capability_envelope": {"status": "accepted"},
            "confidence_budget": {"alpha": 0.05},
            "externality_law": {"status": "accepted"},
            "generated_law": {"status": "accepted"},
            "hazard_envelope": {"status": "accepted"},
            "horizon": "P7D",
            "mission_law": {"status": "accepted"},
            "raw_net_capital_floor": 0,
            "target_id": "target:interval",
            "target_set": {"thresholds": {"coord:x": 1}},
            "target_validity_certificate_ref": "tvc:1",
            "time_uniform_evidence": True,
            "viability_set": {"status": "accepted"},
        },
        baseline={
            "baseline_id": "baseline:demo",
            "baseline_policy_class": "upper-envelope",
            "confidence_budget": {"alpha": 0.05},
            "control_observability": {"status": "accepted"},
            "envelope_coordinates": {"coord:x": 0},
            "model_toolchain_environment_versions": {"python": "3"},
            "path_law_refs": ["law:1"],
            "refresh_contract": {"max_age": "P1D"},
            "resource_envelope": {"cpu": 1},
            "upper_bound_method": "empirical",
        },
        capital_witnesses=[
            {
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
            }
        ],
    )

    assert report["certified_acceleration_candidate"] is True
    assert report["certified_acceleration_interval_candidate"] is False
    assert report["margin_interval"] is not None
    assert report["interval_residuals"]
    assert "missing_transport_error_upper_bound" in {
        item["kind"] for item in report["interval_residuals"]
    }
