from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.extensions import (
    loop_export_bundle,
    loop_import_report,
    loop_init,
    loop_next,
)
from ccr.residuals.store import iter_residuals


def _target() -> dict[str, Any]:
    return {
        "authority_envelope": {"status": "approved"},
        "baseline_upper_envelope_ref": "baseline:loop",
        "capability_basis": ["capability:x"],
        "capability_envelope": {"status": "accepted"},
        "confidence_budget": {"alpha": 0.05},
        "externality_law": {"status": "accepted"},
        "generated_law": {"status": "accepted"},
        "hazard_envelope": {"status": "accepted"},
        "horizon": "P7D",
        "mission_law": {"status": "accepted"},
        "raw_net_capital_floor": 0,
        "target_id": "target:loop",
        "target_set": {"thresholds": {"coord:x": 1}},
        "target_validity_certificate_ref": "tvc:loop",
        "time_uniform_evidence": True,
        "viability_set": {"status": "accepted"},
    }


def _baseline() -> dict[str, Any]:
    return {
        "baseline_id": "baseline:loop",
        "baseline_policy_class": "upper-envelope",
        "confidence_budget": {"alpha": 0.05},
        "control_observability": {"status": "accepted"},
        "envelope_coordinates": {"coord:x": 0},
        "model_toolchain_environment_versions": {"python": "3"},
        "path_law_refs": ["law:loop"],
        "refresh_contract": {"max_age": "P1D"},
        "resource_envelope": {"cpu": 1},
        "upper_bound_method": "empirical",
    }


def _witness() -> dict[str, Any]:
    return {
        "baseline_ref": "baseline:loop",
        "coordinate": "coord:x",
        "finality_ref": "finality:loop",
        "finality_valid": True,
        "gauge_compatible": True,
        "hazard_constrained": True,
        "mission_valid": True,
        "raw_net_solvent": True,
        "signed_surplus_lower_bound": 2,
        "transport_ref": "transport:loop",
        "transport_valid": True,
        "value_estimand_type": "causal",
        "witness_id": "witness:loop",
    }


def test_loop_next_is_advisory_and_read_only(runtime_root: Path) -> None:
    loop_init(runtime_root, target=_target(), baseline=_baseline())

    before_tasks = len(list((runtime_root / "tasks").rglob("*.json")))
    report = loop_next(runtime_root)
    compact = loop_next(runtime_root, compact=True)
    after_tasks = len(list((runtime_root / "tasks").rglob("*.json")))

    assert report["schema_version"] == "ccr.loop_next.v1"
    assert report["mode"] == "advisory"
    assert report["mutated_runtime"] is False
    assert report["recommended_action"]["external_execution"] is False
    assert report["recommended_action"]["writes_runtime"] is False
    assert report["recommended_action"]["safe_command"]
    assert compact["schema_version"] == "ccr.loop_next.compact.v1"
    assert compact["next_safe_action"]
    assert before_tasks == after_tasks


def test_loop_import_report_materializes_safe_local_objects(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "pic-report.json"
    report_path.write_text(
        json.dumps(
            {
                "capital_witnesses": [_witness()],
                "residuals": [
                    {
                        "blocking": True,
                        "description": "Imported PIC residual",
                        "kind": "mission_validity_certificate_required",
                    }
                ],
                "schema_version": "pic.loop_bundle_report.v1",
                "settled": False,
            }
        ),
        encoding="utf-8",
    )

    report = loop_import_report(runtime_root, file=report_path, provider="pic")
    residuals = list(iter_residuals(runtime_root, status="open"))
    witnesses = list((runtime_root / "phase" / "capital_witnesses").glob("*.json"))

    assert report["ok"] is True
    assert report["mutated_runtime"] is True
    assert report["materialized"]["witness_ids"] == ["witness:loop"]
    assert residuals
    assert residuals[0]["kind"] == "other"
    assert residuals[0]["extensions"]["x_imported_residual_kind"] == (
        "mission_validity_certificate_required"
    )
    assert witnesses


def test_loop_export_bundle_writes_required_agent_files(runtime_root: Path, tmp_path: Path) -> None:
    loop_init(runtime_root, target=_target(), baseline=_baseline())
    report_path = tmp_path / "pic-report.json"
    report_path.write_text(json.dumps({"capital_witnesses": [_witness()]}), encoding="utf-8")
    loop_import_report(runtime_root, file=report_path, provider="pic")

    bundle = loop_export_bundle(runtime_root, output_dir=tmp_path / "bundle")
    names = {Path(path).name for path in bundle["written_files"]}

    assert bundle["ok"] is True
    assert {
        "a2a_gate_binding.example.json",
        "baseline_upper_envelope.json",
        "capital_witnesses.jsonl",
        "ccr_loop_state.json",
        "foundry_active_cuts.json",
        "mcp_gate_binding.example.json",
        "observation_residuals.example.json",
        "performance_report.example.json",
        "phase_acceleration_interval_report.expected.json",
        "pic_extraction_pipeline.example.json",
        "pic_token_admissibility.example.json",
        "target.json",
    }.issubset(names)


def test_loop_cli_next_compact(runtime_root: Path, tmp_path: Path, capsys: Any) -> None:
    target = tmp_path / "target.json"
    baseline = tmp_path / "baseline.json"
    target.write_text(json.dumps(_target()), encoding="utf-8")
    baseline.write_text(json.dumps(_baseline()), encoding="utf-8")

    assert (
        main(
            [
                "--root",
                str(runtime_root),
                "loop",
                "init",
                "--target",
                str(target),
                "--baseline",
                str(baseline),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--root", str(runtime_root), "loop", "next", "--compact", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema_version"] == "ccr.loop_next.compact.v1"
    assert payload["ok"] is True
    assert payload["next_safe_action"]
    assert payload["recommended_action"]["external_execution"] is False
