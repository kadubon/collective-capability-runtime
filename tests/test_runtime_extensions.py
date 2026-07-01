from __future__ import annotations

import json
from pathlib import Path

from ccr.extensions import (
    demo_pic_roundtrip,
    distill_seed,
    experiment_compare,
    experiment_export_pic,
    experiment_init,
    foundry_dashboard,
    import_residual_jsonl,
    import_task_jsonl,
    make_packet,
    make_task,
    operation_dispatch,
    operation_plan_from_pic_trace,
    residual_emit_tasks,
    residual_rank,
    schedule_diagnose,
    schedule_emit_sqot_report,
    schedule_rebalance,
    workcell_create,
    workcell_integrate,
    workcell_next,
    workcell_submit,
)
from ccr.io import write_json_atomic
from ccr.packets.store import submit_packet
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.schemas.validation import validate_instance
from ccr.tasks.store import iter_tasks

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_demo_pic_roundtrip_is_disposable_and_candidate_only() -> None:
    report = demo_pic_roundtrip(execute_pic=False)

    assert report["ok"] is True
    assert report["demo_root_discarded"] is True
    assert report["settled"] is False
    assert report["phase"]["open_residual_count"] == 2
    assert report["phase"]["task_counts"]["open"] == 2


def test_workcell_roundtrip_preserves_residuals(runtime_root: Path, tmp_path: Path) -> None:
    created = workcell_create(runtime_root, template="packet-distillation", name="alpha")
    repeated = workcell_create(runtime_root, template="packet-distillation", name="alpha")

    assert len(created["created_tasks"]) == 7
    assert repeated["created_tasks"] == []
    assert len(repeated["existing_tasks"]) == 7
    assert workcell_next(runtime_root, role="generator")["task"]["role"] == "generator"

    submission = tmp_path / "submission.json"
    write_json_atomic(
        submission,
        {
            "residuals": [
                {
                    "blocking": True,
                    "description": "Witness is missing.",
                    "kind": "missing_evidence",
                }
            ],
            "summary": "Candidate output with one residual.",
        },
    )
    submitted = workcell_submit(runtime_root, workcell="alpha", file=submission)
    integrated = workcell_integrate(
        runtime_root,
        workcell="alpha",
        strategy="residual-preserving",
    )

    assert len(submitted["residuals"]) == 1
    assert integrated["settled"] is False
    assert submitted["residuals"][0] in integrated["open_residuals_preserved"]


def test_distill_seed_creates_candidate_packet_and_residual(tmp_path: Path) -> None:
    seed = tmp_path / "seed.md"
    seed.write_text("Candidate claim without evidence.\n", encoding="utf-8")
    report = distill_seed(seed, tmp_path / "out")

    assert report["settled"] is False
    assert len(report["packets_created"]) == 1
    assert report["residuals_created"][0]["kind"] == "missing_evidence"
    assert [stage["name"] for stage in report["pipeline_stages"]] == [
        "segmentation",
        "candidate_mining",
        "canonicalization",
        "leakage_check_placeholder",
        "dependency_graph_extraction",
        "minimal_interface_summary",
        "verifier_binding",
        "packet_proposal",
    ]


def test_foundry_dashboard_counts_candidate_inflow_without_progress(
    runtime_root: Path,
) -> None:
    packet = make_packet(
        packet_id="packet:foundry:candidate",
        summary="Candidate packet for dashboard.",
        claim_text="Candidate packets do not count as positive settled progress.",
        packet_type="workflow",
    )
    submit_packet(runtime_root, packet)

    dashboard = foundry_dashboard(runtime_root)

    assert dashboard["metrics"]["candidate_inflow"] == 1
    assert dashboard["metrics"]["positive_progress_packets"] == 0
    assert any(item["kind"] == "candidate_only_volume" for item in dashboard["bottlenecks"])
    assert dashboard["settled"] is False


def test_residual_rank_and_emit_tasks_keep_residuals_open(runtime_root: Path) -> None:
    blocking = build_residual(
        kind="settlement_blocker",
        description="Baseline is stale.",
        blocking=True,
        object_type="packet",
        object_id="packet:test",
        source="test",
    )
    nonblocking = build_residual(
        kind="candidate_only_reason",
        description="Candidate source is unchecked.",
        blocking=False,
        object_type="packet",
        object_id="packet:test",
        source="test",
    )
    save_residual(runtime_root, blocking)
    save_residual(runtime_root, nonblocking)

    ranked = residual_rank(runtime_root)["ranked_residuals"]
    emitted = residual_emit_tasks(runtime_root, top=1)["tasks"]

    assert ranked[0]["residual_id"] == blocking["residual_id"]
    assert emitted[0]["constraints"]["allowed_commands"] == []
    assert validate_instance("task", emitted[0], root=runtime_root).ok


def test_experiment_compare_and_pic_export_are_candidate_only(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    experiment_init(runtime_root, suite="demo")
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    mismatch = tmp_path / "mismatch.json"
    write_json_atomic(
        baseline,
        {
            "cost": 1.0,
            "resource_envelope": {"budget": 1.0, "time": 1.0},
            "solver": "baseline",
            "success_score": 0.2,
            "verifier_calls": 1,
        },
    )
    write_json_atomic(
        candidate,
        {
            "cost": 1.0,
            "resource_envelope": {"budget": 1.0, "time": 1.0},
            "solver": "collective",
            "success_score": 0.4,
            "verifier_calls": 1,
        },
    )
    write_json_atomic(
        mismatch,
        {
            "cost": 2.0,
            "resource_envelope": {"budget": 2.0, "time": 1.0},
            "solver": "mismatch",
            "success_score": 0.9,
            "verifier_calls": 1,
        },
    )

    matched = experiment_compare(baseline, candidate)
    unmatched = experiment_compare(baseline, mismatch)
    export = experiment_export_pic(runtime_root, suite="demo", output=tmp_path / "pic.json")

    assert matched["resource_matched"] is True
    assert matched["delta"] == 0.2
    assert matched["settled"] is False
    assert unmatched["resource_matched"] is False
    assert unmatched["residual_ready"]["kind"] == "settlement_blocker"
    assert export["report"]["settled"] is False


def test_schedule_reports_unknown_reserve_as_residual_ready(runtime_root: Path) -> None:
    diagnose = schedule_diagnose(runtime_root)
    rebalance = schedule_rebalance(runtime_root, dry_run=True)
    sqot = schedule_emit_sqot_report(runtime_root)

    assert diagnose["diagnostic_reserve"] == "unknown"
    assert diagnose["residual_ready"][0]["kind"] == "queue_overload"
    assert rebalance["mutated"] is False
    assert sqot["schema_version"] == "pic.sqot_queue_report.v1"


def test_trc_operation_plan_requires_pic_checked_operation_ready_trace(
    runtime_root: Path,
) -> None:
    incomplete = operation_plan_from_pic_trace(
        {
            "execution_available": False,
            "execution_blockers": ["missing_authority_envelope"],
            "residuals": [],
            "schema_version": "pic.trc_trace_report.v1",
            "settled": False,
            "trace_id": "trace:incomplete",
            "trc_trace_nf": {"steps": []},
        }
    )
    complete = operation_plan_from_pic_trace(
        {
            "execution_available": True,
            "execution_blockers": [],
            "residuals": [],
            "schema_version": "pic.trc_trace_report.v1",
            "settled": False,
            "trace_id": "trace:complete",
            "real_world_operation_gate": {"operation_ready": True},
            "trc_trace_nf": {
                "evaluation_clock": "2026-07-01T00:00:00Z",
                "steps": [
                    {
                        "action_type": "tool-call",
                        "authority_envelope": {
                            "expires_at": "2099-01-01T00:00:00Z",
                            "issuer": "operator:test",
                            "scopes": ["local_fixture", "local-test", "environment:local-test"],
                            "status": "approved",
                        },
                        "input_ref": "input:fixture",
                        "output_ref": "output:fixture",
                        "postcondition": {"fixture_written": True},
                        "precondition": {"fixture_exists": True},
                        "resource_use": {"budget": 1, "units": "fixture"},
                        "rollback_escrow_obligation": {"rollback": "delete fixture output"},
                        "step_id": "s1",
                        "tolerance_ledger": {"observation_error": 0.0},
                        "tool_call": "fixture-provider",
                        "validity_domain": {"environment": "local-test"},
                    }
                ]
            },
        }
    )
    dispatch = operation_dispatch(
        runtime_root,
        plan=complete,
        provider_name="http",
        execute=False,
    )

    assert incomplete["real_world_operation_ready"] is False
    assert "trace_not_execution_available" in incomplete["execution_blockers"]
    assert complete["real_world_operation_ready"] is True
    assert complete["executed"] is False
    assert complete["constraints"]["allowed_commands"] == []
    assert validate_instance("trc-operation-plan", complete, root=runtime_root).ok
    assert dispatch["ok"] is True
    assert dispatch["executed"] is False
    assert dispatch["network_call_performed"] is False

    scope_mismatch = operation_plan_from_pic_trace(
        {
            "execution_available": True,
            "execution_blockers": [],
            "residuals": [],
            "schema_version": "pic.trc_trace_report.v1",
            "settled": False,
            "trace_id": "trace:scope-mismatch",
            "real_world_operation_gate": {"operation_ready": True},
            "trc_trace_nf": {
                "evaluation_clock": "2026-07-01T00:00:00Z",
                "steps": [
                    {
                        "authority_envelope": {
                            "expires_at": "2099-01-01T00:00:00Z",
                            "scope": "other-domain",
                            "status": "approved",
                        },
                        "step_id": "s1",
                        "validity_domain": {"environment": "local-test"},
                    }
                ],
            },
        }
    )
    execute_without_approval = operation_dispatch(
        runtime_root,
        plan=complete,
        provider_name="http",
        config={
            "allow_execute": True,
            "endpoint": "https://example.invalid/ccr",
            "side_effect_policy": "provider_webhook_allowed",
        },
        execute=True,
    )

    assert scope_mismatch["real_world_operation_ready"] is False
    assert "authority_scope_mismatch" in scope_mismatch["execution_blockers"]
    assert execute_without_approval["ok"] is False
    assert execute_without_approval["executed"] is False
    assert execute_without_approval["residual_ready"]["kind"] == "operator_approval_required"


def test_import_jsonl_validates_each_line_and_reports_duplicates(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    task = make_task(
        kind="packet_repair",
        title="Repair packet",
        objective="Repair imported packet residual.",
        role="integrator",
        source="test",
    )
    residual = build_residual(
        kind="settlement_blocker",
        description="Imported blocker.",
        blocking=True,
        object_type="packet",
        object_id="packet:import",
        source="pic",
    )
    task_jsonl = tmp_path / "tasks.jsonl"
    residual_jsonl = tmp_path / "residuals.jsonl"
    task_jsonl.write_text(
        "\n".join([json.dumps(task), json.dumps(task), "{bad"]) + "\n",
        encoding="utf-8",
    )
    residual_jsonl.write_text(
        "\n".join([json.dumps(residual), json.dumps(residual), "[]"]) + "\n",
        encoding="utf-8",
    )

    task_import = import_task_jsonl(runtime_root, file=task_jsonl, provider="pic")
    residual_import = import_residual_jsonl(runtime_root, file=residual_jsonl, provider="pic")

    assert task_import["imported"] == [task["task_id"]]
    assert task_import["duplicates"] == [task["task_id"]]
    assert task_import["diagnostics"]
    assert residual_import["imported"] == [residual["residual_id"]]
    assert residual_import["duplicates"] == [residual["residual_id"]]
    assert residual_import["diagnostics"][0]["message"] == "line is not an object"
    assert any(item["task_id"] == task["task_id"] for item in iter_tasks(runtime_root))


def test_asi_proxy_bundle_examples_validate_and_import(runtime_root: Path) -> None:
    bundle = REPO_ROOT / "examples" / "asi_proxy_benchmark_bundle"
    candidate = bundle / "packets" / "candidate" / "packet.benchmark.candidate.json"
    checked = bundle / "packets" / "checked" / "packet.benchmark.checked.json"
    residual = bundle / "residuals" / "open" / "residual.benchmark.baseline.json"
    operation_plan = bundle / "trc_operation_plan.json"

    for packet_path in (candidate, checked):
        data = json.loads(packet_path.read_text(encoding="utf-8"))
        assert validate_instance("packet", data, root=runtime_root).ok
    residual_data = json.loads(residual.read_text(encoding="utf-8"))
    assert validate_instance("residual", residual_data, root=runtime_root).ok
    operation_data = json.loads(operation_plan.read_text(encoding="utf-8"))
    assert validate_instance("trc-operation-plan", operation_data, root=runtime_root).ok
    assert operation_data["real_world_operation_ready"] is False
    assert operation_data["executed"] is False

    task_import = import_task_jsonl(
        runtime_root,
        file=bundle / "tasks.jsonl",
        provider="pic",
    )
    residual_import = import_residual_jsonl(
        runtime_root,
        file=bundle / "residuals.jsonl",
        provider="pic",
    )
    runtime_export = json.loads((bundle / "runtime_report_for_pic.json").read_text())

    assert task_import["imported"] == ["task:benchmark:residual-repair"]
    assert residual_import["imported"] == ["residual:benchmark:baseline"]
    assert runtime_export["settled"] is False
    assert runtime_export["candidate_only_reasons"]
