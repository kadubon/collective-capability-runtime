# SPDX-License-Identifier: Apache-2.0
"""Additive CCR orchestration features.

These helpers keep CCR on the runtime/orchestration side.  PIC reports and
tasks are imported as candidate work, hints, residuals, and diagnostics.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccr.adapters.pic import PicVerifierProvider
from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.constants import CONFIG_FILENAME, NON_CLAIMS, RUNTIME_DIRECTORIES
from ccr.ids import stable_id
from ccr.io import canonical_dumps, json_file_name, read_json, write_json_atomic
from ccr.packets.store import iter_packets, submit_packet
from ccr.reports.json_report import phase_report
from ccr.residuals.model import build_residual
from ccr.residuals.store import iter_residuals, save_residual
from ccr.runtime.init import init_runtime
from ccr.runtime.state import packet_counts, task_counts
from ccr.schemas.validation import validate_instance
from ccr.tasks.scheduler import next_task
from ccr.tasks.store import iter_tasks, submit_task, validate_task

FIXED_CREATED_AT = "1970-01-01T00:00:00Z"
WORKCELL_ROLES = (
    "generator",
    "skeptic",
    "formalizer",
    "implementer",
    "verifier",
    "integrator",
    "scheduler",
)
WORKCELL_TEMPLATES = {
    "benchmark-compare",
    "packet-distillation",
    "pic-roundtrip",
    "residual-repair",
}


def demo_pic_roundtrip(*, execute_pic: bool = False) -> dict[str, Any]:
    """Run a deterministic PIC roundtrip demo in a temporary runtime."""

    with tempfile.TemporaryDirectory(prefix="ccr-pic-roundtrip-") as temp:
        root = Path(temp)
        _init_file_runtime(root)
        task = make_task(
            kind="packet_repair",
            title="Demo packet work",
            objective="Create one candidate packet for PIC-compatible verification planning.",
            role="generator",
            source="ccr.demo.pic-roundtrip",
        )
        submit_task(root, task)
        packet = make_packet(
            packet_id="packet:demo:pic-roundtrip",
            summary="Candidate packet for CCR/PIC roundtrip demo.",
            claim_text="CCR can preserve PIC candidate-only reasons as residuals.",
            packet_type="workflow",
        )
        submit_packet(root, packet)
        provider = PicVerifierProvider()
        availability = provider.availability()
        plan = provider.plan_verify(packet, profile="development", packet_path="demo")
        provider_report = _mock_pic_report(packet["packet_id"])
        executed = False
        if execute_pic and availability.get("available"):
            provider_report = provider.execute_verify(
                packet,
                profile="development",
                packet_path="demo",
                timeout_seconds=30,
            )
            executed = True
        normalized = provider.normalize_report(provider_report)
        residual_ids = _materialize_pic_like_residuals(root, normalized)
        safe_hint_ids = _materialize_safe_hints(root, normalized)
        phase = phase_report(root)
        return {
            "demo_root_discarded": True,
            "executed_pic": executed,
            "non_claims": list(NON_CLAIMS),
            "ok": True,
            "packet_id": packet["packet_id"],
            "phase": phase,
            "pic_plan": plan,
            "provider_available": bool(availability.get("available")),
            "residuals_created": residual_ids,
            "safe_command_task_hints": safe_hint_ids,
            "schema_version": "ccr.demo.pic_roundtrip.v1",
            "settled": False,
            "task_id": task["task_id"],
        }


def workcell_create(root: Path, *, template: str, name: str) -> dict[str, Any]:
    """Create an idempotent workcell backed by normal CCR tasks."""

    if template not in WORKCELL_TEMPLATES:
        raise ValueError(f"unknown workcell template: {template}")
    init_runtime(root)
    workcell_dir = root / "workcells" / name
    workcell_dir.mkdir(parents=True, exist_ok=True)
    workcell_path = workcell_dir / "workcell.json"
    created_tasks: list[str] = []
    existing_tasks: list[str] = []
    for role in WORKCELL_ROLES:
        task = make_task(
            kind=template.replace("-", "_"),
            title=f"{name} {role} work",
            objective=f"{role} contribution for {template} workcell {name}.",
            role=role,
            source=f"workcell:{name}:{role}",
            extensions={"x_workcell": name, "x_workcell_template": template},
        )
        with suppress(FileExistsError):
            submit_task(root, task)
            created_tasks.append(task["task_id"])
            continue
        existing_tasks.append(task["task_id"])
    if not workcell_path.exists():
        write_json_atomic(
            workcell_path,
            {
                "created_at": FIXED_CREATED_AT,
                "name": name,
                "roles": list(WORKCELL_ROLES),
                "schema_version": "ccr.workcell.v1",
                "template": template,
            },
            overwrite=False,
        )
    append_event(
        root,
        make_event(
            action="workcell.create",
            object_type="task",
            object_id=name,
            status_before=None,
            status_after="open",
            refs=[str(workcell_path)],
        ),
    )
    return {
        "created_tasks": sorted(created_tasks),
        "existing_tasks": sorted(existing_tasks),
        "name": name,
        "ok": True,
        "path": str(workcell_path),
        "schema_version": "ccr.workcell_create.v1",
        "template": template,
    }


def workcell_next(root: Path, *, role: str) -> dict[str, Any]:
    """Return the next role task without leasing it."""

    return {"ok": True, "role": role, "task": next_task(root, role=role)}


def workcell_submit(root: Path, *, workcell: str, file: Path) -> dict[str, Any]:
    """Store a workcell output and preserve residuals if present."""

    init_runtime(root)
    data = read_json(file)
    if not isinstance(data, dict):
        raise ValueError("workcell output must be a JSON object")
    submission_id = stable_id("workcell-submission", workcell, data)
    destination = root / "workcells" / workcell / "submissions" / json_file_name(submission_id)
    write_json_atomic(destination, data, overwrite=True)
    residual_ids: list[str] = []
    for residual_data in data.get("residuals", []):
        if isinstance(residual_data, dict):
            residual = build_residual(
                kind=str(residual_data.get("kind", "other")),
                description=str(residual_data.get("description", "workcell residual")),
                blocking=bool(residual_data.get("blocking", False)),
                object_type="task",
                object_id=workcell,
                refs=[str(destination)],
                source="ccr.workcell",
                extensions={"raw": residual_data},
            )
            save_residual(root, residual, overwrite=True)
            residual_ids.append(str(residual["residual_id"]))
    append_event(
        root,
        make_event(
            action="workcell.submit",
            object_type="task",
            object_id=workcell,
            status_before=None,
            status_after="submitted",
            refs=[str(destination)],
            residuals=residual_ids,
        ),
    )
    return {
        "ok": True,
        "path": str(destination),
        "residuals": residual_ids,
        "submission_id": submission_id,
        "workcell": workcell,
    }


def workcell_integrate(root: Path, *, workcell: str, strategy: str) -> dict[str, Any]:
    """Integrate workcell submissions without dropping residuals."""

    if strategy != "residual-preserving":
        raise ValueError("only residual-preserving strategy is supported")
    submission_dir = root / "workcells" / workcell / "submissions"
    submissions = sorted(submission_dir.glob("*.json")) if submission_dir.exists() else []
    open_residuals = [
        item for item in iter_residuals(root, status="open") if item.get("object_id") == workcell
    ]
    return {
        "integrated_submissions": [str(path) for path in submissions],
        "ok": True,
        "open_residuals_preserved": [item["residual_id"] for item in open_residuals],
        "schema_version": "ccr.workcell_integrate.v1",
        "settled": False,
        "strategy": strategy,
        "workcell": workcell,
    }


def distill_seed(input_path: Path, output_dir: Path) -> dict[str, Any]:
    """Distill a seed document into a candidate packet."""

    text = input_path.read_text(encoding="utf-8")
    claim = _first_nonempty_line(text) or "Candidate claim from seed."
    packet = make_packet(
        packet_id=f"packet:distill:{_hash_text(claim)}",
        summary=f"Distilled candidate from {input_path.name}.",
        claim_text=claim,
        packet_type="claim",
    )
    residuals = []
    if "evidence:" not in text.lower():
        residuals.append(_report_residual("missing_evidence", "Seed lacks explicit evidence."))
    if len(claim.split()) < 4 or claim.endswith("?"):
        residuals.append(_report_residual("unverified_claim", "Seed claim is ambiguous."))
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "packet.candidate.json"
    write_json_atomic(packet_path, packet, overwrite=True)
    report = _distillation_report(
        str(input_path),
        [str(packet_path)],
        [packet["claims"][0]],
        residuals,
    )
    write_json_atomic(output_dir / "distillation_report.json", report, overwrite=True)
    return report


def distill_trace(input_path: Path, output_dir: Path) -> dict[str, Any]:
    """Distill an agent trace into a candidate trace packet."""

    data = read_json(input_path)
    if not isinstance(data, dict):
        raise ValueError("trace input must be a JSON object")
    steps = data.get("steps") or data.get("events") or []
    claim = f"Trace contains {len(steps) if isinstance(steps, list) else 0} candidate steps."
    packet = make_packet(
        packet_id=f"packet:trace:{_hash_text(canonical_dumps(data))}",
        summary=f"Distilled trace candidate from {input_path.name}.",
        claim_text=claim,
        packet_type="trace",
    )
    residuals = []
    if not steps:
        residuals.append(_report_residual("missing_evidence", "Trace has no finite steps."))
    output_dir.mkdir(parents=True, exist_ok=True)
    packet_path = output_dir / "trace_packet.candidate.json"
    write_json_atomic(packet_path, packet, overwrite=True)
    report = _distillation_report(
        str(input_path),
        [str(packet_path)],
        [packet["claims"][0]],
        residuals,
    )
    write_json_atomic(output_dir / "distillation_report.json", report, overwrite=True)
    return report


def distill_packet(packet_path: Path, *, emit_verifier_plan: bool) -> dict[str, Any]:
    """Summarize verifier binding for an existing packet."""

    packet = read_json(packet_path)
    if not isinstance(packet, dict):
        raise ValueError("packet input must be a JSON object")
    residuals = []
    if not packet.get("evidence"):
        residuals.append(_report_residual("missing_evidence", "Packet has no evidence entries."))
    verifier_plan = []
    if emit_verifier_plan:
        verifier_plan.append(
            {
                "packet_id": packet.get("packet_id"),
                "provider": "pic",
                "purpose": "schema/evidence/residual check",
                "settled": False,
            }
        )
    return {
        **_distillation_report(str(packet_path), [], [], residuals),
        "packet_id": packet.get("packet_id"),
        "verifier_plan": verifier_plan,
    }


def foundry_dashboard(root: Path) -> dict[str, Any]:
    """Compute a foundry dashboard from current runtime state."""

    packets = iter_packets(root)
    residuals = list(iter_residuals(root))
    blocking_ids = {
        str(item.get("object_id"))
        for item in residuals
        if item.get("status") == "open" and item.get("blocking")
    }
    checked_positive = [
        packet
        for packet in packets
        if packet.get("status") in {"checked", "settled"}
        and str(packet.get("packet_id")) not in blocking_ids
    ]
    metrics = {
        "baseline_refresh_age": "unknown",
        "blocking_residuals": sum(1 for item in residuals if item.get("blocking")),
        "candidate_inflow": sum(1 for packet in packets if packet.get("status") == "candidate"),
        "checked_packet_growth": len(checked_positive),
        "diagnostic_reserve": "unknown",
        "negative_liquidity_count": sum(
            1 for item in residuals if item.get("kind") == "negative_liquidity"
        ),
        "open_residuals": sum(1 for item in residuals if item.get("status") == "open"),
        "packet_counts_by_status": packet_counts(root),
        "positive_progress_packets": len(checked_positive),
        "provider_run_count": _json_count(root / "reports" / "providers"),
        "queue_latency": "unknown",
        "settled_packet_growth": sum(
            1 for packet in checked_positive if packet.get("status") == "settled"
        ),
        "task_counts_by_status": task_counts(root),
        "verifier_report_count": _json_count(root / "reports" / "verifier"),
    }
    bottlenecks = foundry_bottlenecks(root, metrics=metrics)["bottlenecks"]
    return {
        "bottlenecks": bottlenecks,
        "metrics": metrics,
        "non_claims": list(NON_CLAIMS),
        "ok": True,
        "recommended_tasks": foundry_recommended_tasks(root),
        "residual_ready": [
            _report_residual("settlement_blocker", "Missing data is reported as unknown, not zero.")
        ],
        "schema_version": "ccr.foundry_dashboard.v1",
        "settled": False,
    }


def foundry_bottlenecks(root: Path, *, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return deterministic foundry bottleneck diagnostics."""

    metrics = metrics or foundry_dashboard(root)["metrics"]
    bottlenecks: list[dict[str, Any]] = []
    if metrics.get("blocking_residuals", 0):
        bottlenecks.append({"kind": "blocking_residuals", "priority": 90})
    if metrics.get("candidate_inflow", 0) and not metrics.get("checked_packet_growth", 0):
        bottlenecks.append({"kind": "candidate_only_volume", "priority": 60})
    if metrics.get("diagnostic_reserve") == "unknown":
        bottlenecks.append({"kind": "unknown_diagnostic_reserve", "priority": 50})
    return {"bottlenecks": bottlenecks, "ok": True, "schema_version": "ccr.foundry_bottlenecks.v1"}


def foundry_recommended_tasks(root: Path) -> list[dict[str, Any]]:
    """Build recommended tasks without storing them."""

    residuals = [item for item in iter_residuals(root, status="open") if item.get("blocking")]
    tasks = [
        make_task(
            kind="residual_repair",
            title="Repair blocking residual",
            objective=f"Repair blocking residual {item.get('residual_id')}.",
            role="integrator",
            source=str(item.get("residual_id")),
            priority=90,
            inputs=[
                {
                    "kind": "residual",
                    "ref": str(item.get("residual_id")),
                    "required": True,
                }
            ],
        )
        for item in residuals[:5]
    ]
    if not tasks:
        tasks.append(
            make_task(
                kind="baseline_refresh",
                title="Refresh foundry baseline",
                objective="Check whether resource-matched baseline data is current.",
                role="benchmark_runner",
                source="foundry:baseline-refresh",
                priority=40,
            )
        )
    return tasks


def residual_rank(root: Path) -> dict[str, Any]:
    """Rank residuals without removing them."""

    ranked = sorted(
        (_ranked_residual(item) for item in iter_residuals(root, status="open")),
        key=lambda item: (-item["score"], item["residual_id"]),
    )
    return {"ok": True, "ranked_residuals": ranked, "schema_version": "ccr.residual_rank.v1"}


def residual_emit_tasks(root: Path, *, top: int) -> dict[str, Any]:
    """Emit repair tasks for top residuals without resolving residuals."""

    ranked = residual_rank(root)["ranked_residuals"][:top]
    tasks = [
        make_task(
            kind=_task_kind_for_residual(item),
            title="Repair residual",
            objective=f"Repair residual {item['residual_id']}: {item['description']}",
            role="integrator",
            source=item["residual_id"],
            priority=min(100, int(item["score"])),
            inputs=[{"kind": "residual", "ref": item["residual_id"], "required": True}],
        )
        for item in ranked
    ]
    return {"ok": True, "schema_version": "ccr.residual_emit_tasks.v1", "tasks": tasks}


def residual_repair_plan(root: Path, *, residual_id: str) -> dict[str, Any]:
    """Build a residual repair plan."""

    for residual in iter_residuals(root):
        if residual.get("residual_id") == residual_id:
            return {
                "blocking": residual.get("blocking", False),
                "ok": True,
                "recommended_task": make_task(
                    kind=_task_kind_for_residual(residual),
                    title="Repair selected residual",
                    objective=f"Repair residual {residual_id}.",
                    role="integrator",
                    source=residual_id,
                    priority=90 if residual.get("blocking") else 50,
                ),
                "residual": residual,
                "schema_version": "ccr.residual_repair_plan.v1",
                "settled": False,
            }
    raise FileNotFoundError(residual_id)


def experiment_init(root: Path, *, suite: str) -> dict[str, Any]:
    """Initialize a dry-run experiment suite."""

    init_runtime(root)
    suite_dir = root / "experiments" / suite
    suite_dir.mkdir(parents=True, exist_ok=True)
    path = suite_dir / "suite.json"
    payload = {
        "created_at": FIXED_CREATED_AT,
        "resource_envelope": {"budget": 1.0, "time": 1.0},
        "schema_version": "ccr.experiment_suite.v1",
        "suite": suite,
    }
    write_json_atomic(path, payload, overwrite=True)
    return {"ok": True, "path": str(path), "suite": suite}


def experiment_run_baseline(root: Path, *, suite: str, solver: Path) -> dict[str, Any]:
    """Import or synthesize a baseline solver result; do not execute solvers."""

    result = _load_result_or_synthetic(solver, label="baseline")
    return _store_experiment_result(root, suite=suite, label="baseline", result=result)


def experiment_run_collective(root: Path, *, suite: str, workcell: Path) -> dict[str, Any]:
    """Import or synthesize a collective result; do not execute workcells."""

    result = _load_result_or_synthetic(workcell, label="collective")
    return _store_experiment_result(root, suite=suite, label="collective", result=result)


def experiment_compare(baseline_path: Path, candidate_path: Path) -> dict[str, Any]:
    """Compare baseline and collective results under resource matching."""

    baseline = read_json(baseline_path)
    candidate = read_json(candidate_path)
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("comparison inputs must be JSON objects")
    base_env = baseline.get("resource_envelope", {})
    candidate_env = candidate.get("resource_envelope", {})
    matched = base_env == candidate_env
    residual_ready = None
    if not matched:
        residual_ready = build_residual(
            kind="settlement_blocker",
            description="Baseline and candidate resource envelopes do not match.",
            blocking=True,
            object_type="report",
            object_id=stable_id("experiment-compare", str(baseline_path), str(candidate_path)),
            refs=[str(baseline_path), str(candidate_path)],
            source="ccr.experiment",
        )
    delta = None
    if matched:
        delta = float(candidate.get("success_score", 0.0)) - float(
            baseline.get("success_score", 0.0)
        )
    return {
        "accepted": matched,
        "baseline_solver": baseline.get("solver", "baseline"),
        "candidate_solver": candidate.get("solver", "collective"),
        "cost": {
            "baseline": baseline.get("cost"),
            "candidate": candidate.get("cost"),
        },
        "delta": delta,
        "limitations": ["comparison is resource-envelope-relative and not real ASI proof"],
        "ok": True,
        "residual_ready": residual_ready,
        "resource_matched": matched,
        "schema_version": "ccr.experiment_compare.v1",
        "settled": False,
        "verifier_calls": {
            "baseline": baseline.get("verifier_calls", 0),
            "candidate": candidate.get("verifier_calls", 0),
        },
    }


def experiment_export_pic(root: Path, *, suite: str, output: Path) -> dict[str, Any]:
    """Export a PIC-compatible runtime report."""

    payload = {
        "accepted": False,
        "candidate_only_reasons": ["CCR experiment export is candidate-only until PIC checks it"],
        "profile": "development",
        "report_id": f"ccr-experiment:{suite}",
        "residuals": list(iter_residuals(root, status="open")),
        "schema_version": "ccr.pic_runtime_export.v1",
        "settled": False,
        "settled_blockers": ["experiment export does not settle phase claims"],
        "suite": suite,
    }
    write_json_atomic(output, payload, overwrite=True)
    return {"ok": True, "output": str(output), "report": payload}


def schedule_diagnose(root: Path) -> dict[str, Any]:
    """Diagnose scheduler/SQOT coordinates."""

    tasks = iter_tasks(root)
    open_tasks = [task for task in tasks if task.get("status") == "open"]
    leased_tasks = [task for task in tasks if task.get("status") == "leased"]
    blocked_tasks = [task for task in tasks if task.get("status") == "blocked"]
    verifier_tasks = [task for task in tasks if task.get("role") == "verifier"]
    residual_repair = [
        task
        for task in tasks
        if "residual" in str(task.get("extensions", {}).get("x_ccr_task_kind", ""))
        or "residual" in str(task.get("objective", "")).lower()
    ]
    stale = [_task_id(task) for task in leased_tasks if _lease_stale(task)]
    residual_ready = []
    if not _diagnostic_reserve_known(root):
        residual_ready.append(
            _report_residual("queue_overload", "Diagnostic reserve data is unknown.")
        )
    return {
        "blocked_tasks": len(blocked_tasks),
        "diagnostic_reserve": "unknown",
        "leased_tasks": len(leased_tasks),
        "meta_occupation_proxy": len(verifier_tasks) / max(1, len(tasks)),
        "ok": True,
        "open_tasks": len(open_tasks),
        "quarantine_load": len([task for task in tasks if task.get("status") == "quarantined"]),
        "queue_latency": "unknown",
        "residual_ready": residual_ready,
        "residual_repair_tasks": len(residual_repair),
        "schema_version": "ccr.schedule_diagnose.v1",
        "settled": False,
        "stale_leases": stale,
        "verifier_tasks": len(verifier_tasks),
    }


def schedule_rebalance(root: Path, *, dry_run: bool = True) -> dict[str, Any]:
    """Build a non-destructive scheduler rebalance report."""

    diagnosis = schedule_diagnose(root)
    return {
        "dry_run": dry_run,
        "mutated": False,
        "ok": True,
        "recommended_moves": [
            {"reason": "stale lease", "task_id": task_id, "target_status": "open"}
            for task_id in diagnosis["stale_leases"]
        ],
        "schema_version": "ccr.schedule_rebalance.v1",
    }


def schedule_emit_sqot_report(root: Path) -> dict[str, Any]:
    """Emit a PIC SQOT-compatible queue report."""

    diagnosis = schedule_diagnose(root)
    open_tasks = diagnosis["open_tasks"]
    verifier_tasks = diagnosis["verifier_tasks"]
    return {
        "diagnostic_reserve": {
            "available": None,
            "required_max": None,
            "required_min": None,
            "status": "unknown",
        },
        "ok": True,
        "queue_status": "diagnostic" if diagnosis["residual_ready"] else "ok",
        "schema_version": "pic.sqot_queue_report.v1",
        "verifier_capacity": {
            "capacity_ratio": None,
            "inflow": float(open_tasks),
            "service": float(verifier_tasks) if verifier_tasks else None,
            "status": "unknown" if not verifier_tasks else "adequate",
        },
    }


_ACTIVE_AUTHORITY_STATUSES = {"active", "approved"}
_AUTHORITY_BLOCKER_KINDS = {
    "authority_issuer_untrusted",
    "authority_scope_mismatch",
    "authority_status_not_active",
    "authority_time_unknown",
    "expired_authority_envelope",
    "fixture_only_authority_non_executable",
    "missing_authority_envelope",
}


def _operation_scope_tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    if value in (None, ""):
        return tokens
    if isinstance(value, dict):
        for key, item in value.items():
            if item in (None, ""):
                continue
            tokens.add(str(item))
            tokens.add(f"{key}:{item}")
    elif isinstance(value, list | tuple | set):
        for item in value:
            tokens.update(_operation_scope_tokens(item))
    else:
        tokens.add(str(value))
    return {token.strip().lower() for token in tokens if token.strip()}


def _operation_authority_scope_tokens(authority: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for key in (
        "scope",
        "scopes",
        "validity_domain",
        "validity_domains",
        "provider_target",
        "provider_targets",
        "provider",
        "providers",
    ):
        tokens.update(_operation_scope_tokens(authority.get(key)))
    return tokens


def _operation_scope_matches(authority: dict[str, Any], required: set[str]) -> bool:
    if not required:
        return True
    authority_tokens = _operation_authority_scope_tokens(authority)
    return "*" in authority_tokens or required.issubset(authority_tokens)


def _parse_operation_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    with suppress(ValueError):
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _operation_reference_time(report: dict[str, Any], trace_nf: dict[str, Any]) -> datetime | None:
    for value in (
        report.get("operation_evaluation_clock"),
        report.get("evaluation_clock"),
        trace_nf.get("operation_evaluation_clock"),
        trace_nf.get("evaluation_clock"),
        trace_nf.get("reference_time"),
    ):
        parsed = _parse_operation_time(value)
        if parsed is not None:
            return parsed
    for step in [item for item in trace_nf.get("steps", []) if isinstance(item, dict)]:
        clock = step.get("clock_cell")
        if not isinstance(clock, dict):
            continue
        for key in ("operation_evaluation_clock", "evaluation_time", "reference_time", "wall_time"):
            parsed = _parse_operation_time(clock.get(key))
            if parsed is not None:
                return parsed
    return None


def _operation_fixture_dry_run(report: dict[str, Any], trace_nf: dict[str, Any]) -> bool:
    gate = report.get("real_world_operation_gate")
    side_effect_policy = "none_without_execute_flag"
    if isinstance(gate, dict):
        side_effect_policy = str(gate.get("side_effect_policy") or side_effect_policy)
    side_effect_policy = str(
        report.get("side_effect_policy") or trace_nf.get("side_effect_policy") or side_effect_policy
    )
    return bool(report.get("fixture_mode") or trace_nf.get("fixture_mode")) and (
        side_effect_policy == "dry_run_only"
    )


def _deep_get_dict(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _authority_freshness_residuals(
    trace_report: dict[str, Any],
    trace_nf: dict[str, Any],
    *,
    existing_residuals: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    seen = {
        (str(item.get("kind", "")), str(item.get("step_id", "")))
        for item in existing_residuals or []
        if isinstance(item, dict)
    }
    trace_id = str(trace_report.get("trace_id", "trace"))
    reference = _operation_reference_time(trace_report, trace_nf)
    fixture_dry_run = _operation_fixture_dry_run(trace_report, trace_nf)

    def append_once(kind: str, step_id: str, description: str) -> None:
        key = (kind, step_id)
        if key in seen:
            return
        residual = _operation_residual(kind, description)
        residual["step_id"] = step_id
        residuals.append(residual)
        seen.add(key)

    for step in [item for item in trace_nf.get("steps", []) if isinstance(item, dict)]:
        step_id = str(step.get("step_id", "step"))
        authority = step.get("authority_envelope")
        if not isinstance(authority, dict) or str(authority.get("status", "")).lower() == "missing":
            continue
        status = str(authority.get("status", "")).lower()
        if status not in _ACTIVE_AUTHORITY_STATUSES:
            append_once(
                "authority_status_not_active",
                step_id,
                f"Authority status is not active/approved for {trace_id}:{step_id}.",
            )
        expires_at = authority.get("expires_at")
        if expires_at in (None, ""):
            if not fixture_dry_run:
                append_once(
                    "authority_time_unknown",
                    step_id,
                    f"Authority expiry/reference time is unknown for {trace_id}:{step_id}.",
                )
        else:
            expiry = _parse_operation_time(expires_at)
            if expiry is None:
                append_once(
                    "authority_time_unknown",
                    step_id,
                    f"Authority expiry/reference time is unknown for {trace_id}:{step_id}.",
                )
            elif reference is None:
                if not fixture_dry_run:
                    append_once(
                        "authority_time_unknown",
                        step_id,
                        f"Authority expiry/reference time is unknown for {trace_id}:{step_id}.",
                    )
            elif expiry <= reference:
                append_once(
                    "expired_authority_envelope",
                    step_id,
                    f"Authority envelope is expired for {trace_id}:{step_id}.",
                )
            if str(expires_at) == FIXED_CREATED_AT and fixture_dry_run:
                append_once(
                    "fixture_only_authority_non_executable",
                    step_id,
                    f"Fixture-only authority is not executable for {trace_id}:{step_id}.",
                )
        required_scope = _operation_scope_tokens(step.get("validity_domain"))
        if not _operation_scope_matches(authority, required_scope):
            append_once(
                "authority_scope_mismatch",
                step_id,
                f"Authority scope does not cover validity domain for {trace_id}:{step_id}.",
            )
    return residuals


def operation_plan_from_pic_trace(trace_report: dict[str, Any]) -> dict[str, Any]:
    """Create a TRC-governed real-world operation plan from a PIC trace report.

    CCR consumes the PIC checker output here; it does not re-check TRC theory.
    The returned plan is dry-run and does not execute any provider action.
    """

    if not isinstance(trace_report, dict):
        raise ValueError("trace report must be a JSON object")
    schema = str(trace_report.get("schema_version", ""))
    pic_checked = schema in {"pic.trc_trace_report.v1", "pic.trc_operation_gate_report.v1"}
    trace_nf = trace_report.get("trc_trace_nf", {})
    if not isinstance(trace_nf, dict):
        trace_nf = {}
    raw_steps = trace_nf.get("steps", [])
    steps = [step for step in raw_steps if isinstance(step, dict)]
    execution_blockers = sorted(
        {str(item) for item in trace_report.get("execution_blockers", []) if str(item)}
    )
    residuals = [dict(item) for item in trace_report.get("residuals", []) if isinstance(item, dict)]
    if not pic_checked:
        execution_blockers.append("pic_trc_trace_report_required")
        residuals.append(
            _operation_residual(
                "pic_trc_trace_or_gate_report_required",
                "Real-world operation planning requires a PIC trace-check "
                "or operation-gate report.",
            )
        )
    if schema == "pic.trc_operation_gate_report.v1":
        pic_operation_ready = bool(trace_report.get("operation_ready", False))
    else:
        gate = trace_report.get("real_world_operation_gate")
        gate_ready = bool(gate.get("operation_ready", False)) if isinstance(gate, dict) else False
        pic_operation_ready = bool(trace_report.get("execution_available", False)) and gate_ready
    residuals.extend(
        _authority_freshness_residuals(
            trace_report,
            trace_nf,
            existing_residuals=residuals,
        )
    )
    authority_blockers = {
        str(item.get("kind"))
        for item in residuals
        if str(item.get("kind")) in _AUTHORITY_BLOCKER_KINDS
    }
    execution_blockers.extend(sorted(authority_blockers))
    if not pic_operation_ready:
        execution_blockers.append("trace_not_execution_available")
        residuals.append(
            _operation_residual(
                "trace_not_execution_available",
                "PIC did not mark this TRC trace as operation-ready.",
            )
        )
    operations = [_operation_step(step, index) for index, step in enumerate(steps)]
    ready = (
        pic_checked
        and pic_operation_ready
        and not {item for item in execution_blockers if item}
    )
    return {
        "constraints": {
            "allowed_commands": [],
            "default_mode": "dry_run",
            "forbidden_actions": ["automatic_execution", "shell_expansion"],
            "network_policy": "explicit_provider_config_only",
            "requires_execute_flag": True,
            "requires_provider_config": True,
            "side_effect_policy": "none_without_execute_flag",
        },
        "executed": False,
        "execution_blockers": sorted(set(execution_blockers)),
        "non_claims": [
            *list(NON_CLAIMS),
            "A TRC operation plan is not physical outcome proof.",
            "Execution-available is not executed.",
        ],
        "ok": True,
        "operations": operations,
        "pic_trace_report_schema_version": schema,
        "plan_id": stable_id("trc-operation-plan", trace_report),
        "real_world_operation_ready": ready,
        "residuals": residuals,
        "schema_version": "ccr.trc_operation_plan.v1",
        "settled": False,
        "source_trace_id": str(trace_report.get("trace_id", "trace")),
    }


def operation_preflight_from_pic_trace(
    trace_report: dict[str, Any],
    *,
    provider_name: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a non-executing CCR operation preflight report."""

    plan = operation_plan_from_pic_trace(trace_report)
    residuals = [dict(item) for item in plan["residuals"] if isinstance(item, dict)]
    execution_blockers = list(plan["execution_blockers"])
    if not isinstance(config, dict):
        execution_blockers.append("provider_config_required")
        residuals.append(
            _operation_residual(
                "provider_config_required",
                "Operation preflight requires explicit provider config.",
            )
        )
    side_effect_policy = "none_without_execute_flag"
    if isinstance(config, dict):
        side_effect_policy = str(config.get("side_effect_policy", side_effect_policy))
        if config.get("allow_execute") and not config.get("operator_approval_ref"):
            execution_blockers.append("operator_approval_required")
            residuals.append(
                _operation_residual(
                    "operator_approval_required",
                    "Provider dispatch requires a user/operator approval reference.",
                )
            )
    provider_dispatch_ready = (
        bool(plan["real_world_operation_ready"])
        and isinstance(config, dict)
        and bool(config.get("allow_execute"))
        and bool(config.get("operator_approval_ref"))
        and side_effect_policy not in {"dry_run_only", "none", "none_without_execute_flag"}
        and not execution_blockers
    )
    return {
        "accepted": True,
        "executed": False,
        "execution_blockers": sorted(set(execution_blockers)),
        "non_claims": [
            *list(NON_CLAIMS),
            "Preflight is not dispatch.",
            "Provider dispatch readiness is not execution.",
        ],
        "ok": bool(plan["real_world_operation_ready"]) and not execution_blockers,
        "operation_plan": plan,
        "operation_ready": bool(plan["real_world_operation_ready"]),
        "physical_dispatch_ready": False,
        "provider": provider_name,
        "provider_dispatch_ready": provider_dispatch_ready,
        "residuals": residuals,
        "schema_version": "ccr.trc_operation_preflight.v1",
        "settled": False,
        "side_effect_policy": side_effect_policy,
    }


def operation_dispatch(
    root: Path,
    *,
    plan: dict[str, Any],
    provider_name: str,
    config: dict[str, Any] | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or explicitly dispatch a TRC-governed operation through a provider."""

    from ccr.providers.registry import get_provider

    init_runtime(root)
    if not isinstance(plan, dict):
        raise ValueError("operation plan must be a JSON object")
    provider = get_provider(provider_name)
    payload = {
        "operation_plan": plan,
        "plan_id": plan.get("plan_id"),
        "schema_version": "ccr.trc_operation_provider_payload.v1",
    }
    provider_plan = provider.plan(action="trc_operation", payload=payload, root=root)
    if not plan.get("real_world_operation_ready", False):
        residual = _operation_residual(
            "operation_plan_not_ready",
            "TRC operation plan is not ready for real-world dispatch.",
        )
        return {
            "executed": False,
            "network_call_performed": False,
            "ok": False,
            "plan": provider_plan,
            "provider": provider_name,
            "residual_ready": residual,
            "schema_version": "ccr.trc_operation_dispatch.v1",
        }
    if not execute:
        return {
            "executed": False,
            "network_call_performed": False,
            "ok": True,
            "plan": provider_plan,
            "provider": provider_name,
            "schema_version": "ccr.trc_operation_dispatch.v1",
        }
    if not isinstance(config, dict) or not config.get("allow_execute"):
        residual = _operation_residual(
            "explicit_execution_config_required",
            "Operation execution requires config with allow_execute=true.",
        )
        return {
            "executed": False,
            "network_call_performed": False,
            "ok": False,
            "plan": provider_plan,
            "provider": provider_name,
            "residual_ready": residual,
            "schema_version": "ccr.trc_operation_dispatch.v1",
        }
    side_effect_policy = str(config.get("side_effect_policy", "none_without_execute_flag"))
    if not config.get("operator_approval_ref"):
        residual = _operation_residual(
            "operator_approval_required",
            "Operation execution requires a user/operator approval reference.",
        )
        return {
            "executed": False,
            "network_call_performed": False,
            "ok": False,
            "plan": provider_plan,
            "provider": provider_name,
            "residual_ready": residual,
            "schema_version": "ccr.trc_operation_dispatch.v1",
        }
    if side_effect_policy in {"dry_run_only", "none", "none_without_execute_flag"}:
        residual = _operation_residual(
            "side_effect_policy_execution_required",
            "Operation execution requires an explicit non-dry-run side-effect policy.",
        )
        return {
            "executed": False,
            "network_call_performed": False,
            "ok": False,
            "plan": provider_plan,
            "provider": provider_name,
            "residual_ready": residual,
            "schema_version": "ccr.trc_operation_dispatch.v1",
        }
    report = provider.execute(
        action="trc_operation",
        payload=payload,
        root=root,
        config=config,
    )
    append_event(
        root,
        make_event(
            action="operation.dispatch",
            object_type="report",
            object_id=stable_id("operation-dispatch", report),
            status_before=None,
            status_after="created",
            refs=[str(plan.get("plan_id", ""))],
        ),
    )
    return {
        "executed": bool(report.get("network_call_performed")),
        "ok": bool(report.get("ok", False)),
        "provider": provider_name,
        "report": report,
        "schema_version": "ccr.trc_operation_dispatch.v1",
    }


def operation_observe(
    *,
    dispatch_report: dict[str, Any],
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Attach observation evidence to a dispatch report without proving physical outcome."""

    executed = bool(
        dispatch_report.get("executed")
        or dispatch_report.get("network_call_performed")
        or _deep_get_dict(dispatch_report, "report.network_call_performed")
    )
    physical_actuation_observed = bool(observation.get("physical_actuation_observed", False))
    residuals: list[dict[str, Any]] = []
    if physical_actuation_observed and not observation.get("verifier_acceptance_ref"):
        residuals.append(
            _operation_residual(
                "physical_outcome_verifier_required",
                "Physical actuation observation requires a scoped verifier before outcome claims.",
            )
        )
    return {
        "dispatch_executed": executed,
        "executed": False,
        "non_claims": [
            *list(NON_CLAIMS),
            "Observation evidence is not physical outcome proof without verifier acceptance.",
        ],
        "observation": observation,
        "ok": not residuals,
        "physical_outcome_proven": False,
        "residuals": residuals,
        "schema_version": "ccr.trc_operation_observation.v1",
        "settled": False,
    }


def import_task_jsonl(root: Path, *, file: Path, provider: str) -> dict[str, Any]:
    """Import task JSONL with independent line validation."""

    init_runtime(root)
    imported: list[str] = []
    duplicates: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, parsed, error in _iter_jsonl(file):
        if error is not None:
            diagnostics.append(_line_diagnostic(file, line_number, error))
            continue
        if not isinstance(parsed, dict):
            diagnostics.append(_line_diagnostic(file, line_number, "line is not an object"))
            continue
        task = dict(parsed)
        task.setdefault("extensions", {})
        task["extensions"][f"x_imported_from_{provider}"] = True
        task_id = str(task.get("task_id", ""))
        if task_id in seen:
            duplicates.append(task_id)
            continue
        seen.add(task_id)
        validation = validate_task(task, root=root)
        if not validation.ok:
            diagnostics.append(
                _line_diagnostic(
                    file,
                    line_number,
                    "; ".join(err.message for err in validation.errors),
                )
            )
            continue
        with suppress(FileExistsError):
            submit_task(root, task)
            imported.append(task_id)
            continue
        duplicates.append(task_id)
    return {
        "diagnostics": diagnostics,
        "duplicates": sorted(duplicates),
        "imported": sorted(imported),
        "ok": True,
        "provider": provider,
        "schema_version": "ccr.task_import.v1",
    }


def import_residual_jsonl(root: Path, *, file: Path, provider: str) -> dict[str, Any]:
    """Import residual JSONL with independent line validation."""

    init_runtime(root)
    imported: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for line_number, parsed, error in _iter_jsonl(file):
        if error is not None:
            diagnostics.append(_line_diagnostic(file, line_number, error))
            continue
        if not isinstance(parsed, dict):
            diagnostics.append(_line_diagnostic(file, line_number, "line is not an object"))
            continue
        residual = dict(parsed)
        residual.setdefault("extensions", {})
        residual["extensions"][f"x_imported_from_{provider}"] = True
        residual_id = str(residual.get("residual_id", ""))
        if residual_id in seen:
            duplicates.append(residual_id)
            continue
        seen.add(residual_id)
        validation = validate_instance("residual", residual, root=root)
        if not validation.ok:
            diagnostics.append(
                _line_diagnostic(
                    file,
                    line_number,
                    "; ".join(err.message for err in validation.errors),
                )
            )
            continue
        with suppress(FileExistsError):
            save_residual(root, residual, overwrite=False)
            imported.append(residual_id)
            continue
        duplicates.append(residual_id)
    return {
        "diagnostics": diagnostics,
        "duplicates": sorted(duplicates),
        "imported": sorted(imported),
        "ok": True,
        "provider": provider,
        "schema_version": "ccr.residual_import.v1",
    }


def make_task(
    *,
    kind: str,
    title: str,
    objective: str,
    role: str,
    source: str,
    priority: int = 50,
    inputs: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a valid CCR task."""

    task_id = stable_id("task", kind, role, source, objective)
    return {
        "blackboard_refs": [],
        "completion": {},
        "constraints": {
            "allowed_commands": [],
            "authority_policy": "read_only",
            "forbidden_actions": ["automatic_execution", "shell_expansion"],
            "max_runtime_minutes": 30,
            "network_policy": "none",
            "side_effect_policy": "dry_run_only",
        },
        "created_at": FIXED_CREATED_AT,
        "dependencies": [],
        "expected_outputs": [
            {
                "acceptance_criteria": ["Residuals must be preserved."],
                "destination": "tasks/open",
                "kind": "json",
                "schema_ref": "schemas/task.schema.json",
            }
        ],
        "extensions": {"x_ccr_task_kind": kind, **(extensions or {})},
        "inputs": inputs or [],
        "lease": {
            "lease_required": True,
            "leased_at": None,
            "leased_by": None,
            "renewal_allowed": True,
            "ttl_minutes": 30,
        },
        "objective": objective,
        "pic_interop": {
            "candidate_only_until_checked": True,
            "enabled": True,
            "identity_context_required": False,
            "input_mapping": "none",
            "output_mapping": "none",
            "pic_profile": "development",
            "recommended_pic_commands": [],
        },
        "priority": max(0, min(100, priority)),
        "residual_policy": {
            "blocking_residuals_prevent_settlement": True,
            "minimum_residual_fields": ["residual_id", "kind", "description", "blocking"],
            "preserve_residuals": True,
            "residual_destination": "residuals/open",
        },
        "role": role,
        "schema_version": "ccr.task.v0.1",
        "status": "open",
        "task_id": task_id,
        "title": title,
        "verifier_plan": {
            "failure_route": "residual",
            "optional_verifiers": ["pic"],
            "promotion_gate": "none",
            "required_verifiers": [],
        },
    }


def make_packet(
    *,
    packet_id: str,
    summary: str,
    claim_text: str,
    packet_type: str,
) -> dict[str, Any]:
    """Build a valid candidate CCR packet."""

    return {
        "artifacts": [
            {
                "artifact_id": f"artifact:{_hash_text(packet_id)}",
                "content_sha256": "unknown",
                "kind": "text",
                "uri_or_path": "inline",
            }
        ],
        "claims": [
            {
                "claim_id": f"claim:{_hash_text(packet_id)}",
                "claim_text": claim_text,
                "claim_type": "implementation",
                "settlement_target": "diagnostic_only",
                "status": "candidate",
            }
        ],
        "created_at": FIXED_CREATED_AT,
        "issuer": {"actor_id": "agent:ccr", "actor_type": "agent"},
        "lineage": {"children": [], "parents": [], "revision": 0},
        "packet_id": packet_id,
        "packet_type": packet_type,
        "pic_interop": {
            "candidate_kind": "packet_json",
            "enabled": True,
            "profile": "development",
            "recommended_commands": ["pic agent check --compact"],
            "status_mapping": {
                "pic_accepted_maps_to": "checked",
                "pic_settled_false_maps_to": "provisional",
                "pic_settled_true_maps_to": "checked",
            },
        },
        "provenance": {
            "content_sha256": "unknown",
            "origin_kind": "derived",
            "source_refs": ["ccr.distill"],
        },
        "residuals": [
            {
                "blocking": False,
                "description": "Candidate packet requires verification.",
                "kind": "unverified_claim",
                "residual_id": f"residual:{_hash_text(packet_id)}",
                "severity": "medium",
            }
        ],
        "reuse": {
            "intended_downstream_uses": ["verification"],
            "reuse_mode": "local",
            "transport_limits": ["candidate-only"],
        },
        "risk": {
            "authority_level": "none",
            "hazard_level": "none",
            "misuse_risk": "low",
            "overclaim_risk": "medium",
        },
        "schema_version": "ccr.packet.v0.1",
        "scope": {
            "out_of_scope": ["real ASI proof", "execution authority"],
            "profiles": ["development"],
            "validity_domain": "protocol-relative-demo",
        },
        "status": "candidate",
        "summary": summary,
        "verifiers": [
            {
                "provider": "pic",
                "purpose": "schema",
                "required": True,
                "verifier_id": f"verifier:{_hash_text(packet_id)}",
            }
        ],
    }


def _init_file_runtime(root: Path) -> None:
    """Create only the file-backed runtime paths needed by disposable demos."""

    root.mkdir(parents=True, exist_ok=True)
    for relative in RUNTIME_DIRECTORIES:
        (root / relative).mkdir(parents=True, exist_ok=True)
    events_path = root / "blackboard" / "events.jsonl"
    if not events_path.exists():
        events_path.write_text("", encoding="utf-8")
    write_json_atomic(
        root / CONFIG_FILENAME,
        {
            "created_at": FIXED_CREATED_AT,
            "default_mode": "dry_run",
            "external_side_effects_default": "none",
            "non_claims": list(NON_CLAIMS),
            "runtime_directories": list(RUNTIME_DIRECTORIES),
            "schema_version": "ccr.config.v0.1",
        },
        overwrite=True,
    )


def _mock_pic_report(packet_id: str) -> dict[str, Any]:
    return {
        "accepted": True,
        "candidate_only_reasons": ["mock PIC report is candidate-only"],
        "packet_id": packet_id,
        "profile": "development",
        "safe_commands": ["pic phase plan --compact --profile development"],
        "settled": False,
        "settled_blockers": ["mock PIC report cannot settle CCR packet"],
        "workflow_usable": True,
    }


def _materialize_pic_like_residuals(root: Path, normalized: dict[str, Any]) -> list[str]:
    residual_ids: list[str] = []
    packet_id = str(normalized.get("packet_id") or normalized.get("import_id"))
    for reason in normalized.get("candidate_only_reasons", []):
        residual = build_residual(
            kind="candidate_only_reason",
            description=f"PIC candidate-only reason: {reason}",
            blocking=False,
            object_type="packet",
            object_id=packet_id,
            refs=[str(normalized.get("import_id"))],
            source="ccr.demo.pic",
        )
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
    for blocker in normalized.get("settled_blockers", []):
        residual = build_residual(
            kind="settlement_blocker",
            description=f"PIC settled blocker: {blocker}",
            blocking=True,
            object_type="packet",
            object_id=packet_id,
            refs=[str(normalized.get("import_id"))],
            source="ccr.demo.pic",
        )
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
    return sorted(residual_ids)


def _materialize_safe_hints(root: Path, normalized: dict[str, Any]) -> list[str]:
    task_ids: list[str] = []
    for command in normalized.get("safe_commands", []):
        task = make_task(
            kind="safe_command_hint",
            title="Review safe command hint",
            objective="Review provider safe command hint without executing it.",
            role="integrator",
            source=str(command),
            priority=30,
            inputs=[{"kind": "text", "ref": str(command), "required": True}],
            extensions={"x_safe_command_hint": command},
        )
        with suppress(FileExistsError):
            submit_task(root, task)
        task_ids.append(task["task_id"])
    return sorted(task_ids)


def _distillation_report(
    input_ref: str,
    packets_created: list[str],
    claims_created: list[dict[str, Any]],
    residuals_created: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "candidate_only_reasons": [
            "distillation creates candidates only; it does not prove ALT settlement"
        ],
        "claims_created": claims_created,
        "input": input_ref,
        "non_claims": list(NON_CLAIMS),
        "ok": True,
        "packets_created": packets_created,
        "pipeline_stages": [
            {"name": "segmentation", "status": "dry_run"},
            {"name": "candidate_mining", "status": "dry_run"},
            {"name": "canonicalization", "status": "dry_run"},
            {"name": "leakage_check_placeholder", "status": "residual_ready"},
            {"name": "dependency_graph_extraction", "status": "dry_run"},
            {"name": "minimal_interface_summary", "status": "dry_run"},
            {"name": "verifier_binding", "status": "dry_run"},
            {"name": "packet_proposal", "status": "candidate_only"},
        ],
        "residuals_created": residuals_created,
        "schema_version": "ccr.distillation_report.v1",
        "settled": False,
        "verifier_plan": [],
    }


def _report_residual(kind: str, description: str) -> dict[str, Any]:
    return {
        "blocking": kind in {"settlement_blocker", "queue_overload"},
        "description": description,
        "kind": kind,
        "residual_id": stable_id("residual-ready", kind, description),
    }


def _operation_residual(kind: str, description: str) -> dict[str, Any]:
    return {
        "blocking": True,
        "description": description,
        "kind": kind,
        "residual_id": stable_id("operation-residual", kind, description),
        "status": "open",
    }


def _operation_step(step: dict[str, Any], index: int) -> dict[str, Any]:
    authority = step.get("authority_envelope")
    postcondition = step.get("postcondition")
    precondition = step.get("precondition")
    resource_use = step.get("resource_use") or step.get("resource_ledger")
    rollback = step.get("rollback_escrow_obligation")
    return {
        "action_type": str(step.get("action_type", "tool-call")),
        "authority_envelope": authority if isinstance(authority, dict) else {},
        "input_ref": str(step.get("input_ref", "")),
        "operation_index": index,
        "output_ref": str(step.get("output_ref", "")),
        "postcondition": postcondition if isinstance(postcondition, dict) else {},
        "precondition": precondition if isinstance(precondition, dict) else {},
        "resource_use": resource_use if isinstance(resource_use, dict) else {},
        "rollback_escrow_obligation": rollback if isinstance(rollback, dict) else {},
        "step_id": str(step.get("step_id", f"step:{index}")),
        "tolerance_ledger": step.get("tolerance_ledger")
        if isinstance(step.get("tolerance_ledger"), dict)
        else {},
        "tool_call": str(step.get("tool_call") or step.get("tool", "")),
        "validity_domain": step.get("validity_domain")
        if isinstance(step.get("validity_domain"), dict)
        else {},
    }


def _ranked_residual(residual: dict[str, Any]) -> dict[str, Any]:
    severity_score = {"info": 1, "low": 10, "medium": 30, "high": 60, "critical": 90}
    score = severity_score.get(str(residual.get("severity", "medium")), 30)
    if residual.get("blocking"):
        score += 50
    if residual.get("kind") in {"settlement_blocker", "hazard", "negative_liquidity"}:
        score += 15
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
        "kind": str(residual.get("kind", "other")),
        "residual_id": str(residual.get("residual_id")),
        "score": float(score),
        "status": residual.get("status", "open"),
    }


def _task_kind_for_residual(residual: dict[str, Any]) -> str:
    kind = str(residual.get("kind", "other"))
    if kind == "hazard":
        return "hazard_envelope_repair"
    if kind == "negative_liquidity":
        return "baseline_refresh"
    if kind == "queue_overload":
        return "sqot_queue_repair"
    if kind == "authority_gap":
        return "transport_certificate_repair"
    if kind == "missing_evidence":
        return "verifier_route"
    return "residual_repair"


def _store_experiment_result(
    root: Path, *, suite: str, label: str, result: dict[str, Any]
) -> dict[str, Any]:
    init_runtime(root)
    path = root / "experiments" / suite / f"{label}.json"
    payload = {
        "limitations": ["result imported or synthetic; no arbitrary solver execution"],
        "schema_version": f"ccr.experiment_{label}.v1",
        **result,
    }
    write_json_atomic(path, payload, overwrite=True)
    return {"ok": True, "path": str(path), "result": payload, "suite": suite}


def _load_result_or_synthetic(path: Path, *, label: str) -> dict[str, Any]:
    if path.exists():
        data = read_json(path)
        if isinstance(data, dict):
            return data
    return {
        "cost": 1.0,
        "resource_envelope": {"budget": 1.0, "time": 1.0},
        "solver": label,
        "success_score": 0.0 if label == "baseline" else 0.1,
        "verifier_calls": 0,
    }


def _lease_stale(task: dict[str, Any]) -> bool:
    lease = task.get("lease", {})
    if not isinstance(lease, dict):
        return True
    leased_at = lease.get("leased_at")
    ttl = lease.get("ttl_minutes")
    if leased_at is None or ttl is None:
        return True
    try:
        parsed = datetime.fromisoformat(str(leased_at).replace("Z", "+00:00"))
        return parsed + timedelta(minutes=int(ttl)) < datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return True


def _diagnostic_reserve_known(root: Path) -> bool:
    for path in (root / "reports").rglob("*.json") if (root / "reports").exists() else []:
        with suppress(Exception):
            data = read_json(path)
            if isinstance(data, dict) and "diagnostic_reserve" in canonical_dumps(data):
                return True
    return False


def _iter_jsonl(path: Path) -> list[tuple[int, Any | None, str | None]]:
    rows: list[tuple[int, Any | None, str | None]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append((line_number, json.loads(stripped), None))
            except json.JSONDecodeError as exc:
                rows.append((line_number, None, str(exc)))
    return rows


def _line_diagnostic(file: Path, line_number: int, message: str) -> dict[str, Any]:
    return {
        "line_number": line_number,
        "message": message,
        "residual_ready": build_residual(
            kind="validation_error",
            description=f"Import line {line_number} failed: {message}",
            blocking=False,
            object_type="report",
            object_id=str(file),
            refs=[str(file)],
            source="ccr.import",
        ),
    }


def _json_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*.json") if item.is_file())


def _task_id(task: dict[str, Any]) -> str:
    return str(task.get("task_id", ""))


def _first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip("# \t")
        if stripped:
            return stripped
    return ""


def _hash_text(text: str) -> str:
    return stable_id("h", text).split(":")[-1][:16]
