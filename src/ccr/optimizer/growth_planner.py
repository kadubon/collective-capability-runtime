# SPDX-License-Identifier: Apache-2.0
"""Bounded catalogue search over explicit joint scenarios using rational arithmetic."""

from __future__ import annotations

import copy
from datetime import timedelta
from fractions import Fraction
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer.growth_ledger import prerequisites, replay
from ccr.optimizer.growth_model import PLAN
from ccr.optimizer.model import timestamp


def cost(run: dict[str, Any], action: dict[str, Any]) -> dict[str, int]:
    arm = next(
        a
        for a in run["config"]["interventions"]
        if a["intervention_id"] == action["intervention_id"]
    )
    return {
        k: arm["resource_upper_bound"][k] + action["cleanup_cost"][k]
        for k in action["cleanup_cost"]
    }


def evaluate(run: dict[str, Any], steps: list[str], current: str, group: str) -> dict[str, Any]:
    from ccr.optimizer.engine import accounting

    g = run["config"]["growth"]
    book = accounting(run, group)
    ledger = replay(run, current, group=group)
    models = (
        ledger["compatible_scenarios"]
        if not run["frozen_policy"]
        else run["frozen_policy"]["compatible_scenarios"]
    )
    reasons = []
    if not models:
        reasons.append("inconsistent_model_set")
    already = {t["growth_action"] for t in run["trials"] if t["group"] == group}
    remaining = [s for s in steps if s not in already]
    if not remaining:
        reasons.append("no_unstarted_steps")
    totals = dict.fromkeys(g["units"]["costs"], 0)
    elapsed = 0
    worst = None
    forecasts = []
    for name in remaining:
        a = g["actions"][name]
        elapsed += a["duration_seconds"] + a["cleanup_seconds"]
        for k, v in cost(run, a).items():
            totals[k] += v
        if any(a["capacity"][k] > g["quota"]["capacity"][k] for k in a["capacity"]):
            reasons.append("capacity_quota")
    if elapsed > g["horizon_seconds"] or timestamp(current) + timedelta(
        seconds=elapsed
    ) > timestamp(g["window_end"]):
        reasons.append("horizon_or_window")
    for k in totals:
        if totals[k] > book["remaining"][k]:
            reasons.append("budget:" + k)
        if (
            group == "training"
            and any(g["actions"][s]["kind"] not in {"diagnostic", "repair"} for s in remaining)
            and totals[k] + book["used"][k] + book["reserved"][k]
            > book["budget"][k] - g["diagnostic_budget"][k]
        ):
            reasons.append("diagnostic_reserve:" + k)
    # One common sequence. Failure stops productive descendants and funded cleanup remains.
    for model in models:
        hypothetical = copy.deepcopy(ledger)
        gains = dict(ledger["observed_service"])
        seen = set(ledger["service_events"])
        prefix_seconds = 0
        for name in remaining:
            a = g["actions"][name]
            prefix_seconds += a["duration_seconds"] + a["cleanup_seconds"]
            reasons.extend(prerequisites(g, a, hypothetical))
            if any(
                timestamp(g["assets"][asset]["expires_at"])
                <= timestamp(current) + timedelta(seconds=prefix_seconds)
                for asset in a["requires"]
            ):
                reasons.append("source_expires_in_bundle")
            r = g["receivers"][a["receiver"]]
            for stage, work in a["verification_work"].items():
                v = g["verifier_stages"][stage]
                rates = [v["service_units_per_second"]]
                rates.extend(
                    hypothetical["measured_verifier_service"][asset][stage]
                    for asset in a["requires"]
                    if asset in hypothetical["measured_verifier_service"]
                )
                known = [rate for rate in rates if rate is not None]
                if work and (
                    not known
                    or work > max(known) * a["duration_seconds"]
                    or r["domain"] not in v["domains"]
                    or r["quality"] != v["quality"]
                    or timestamp(v["fresh_until"])
                    < timestamp(current) + timedelta(seconds=prefix_seconds)
                ):
                    reasons.append("verifier_service_or_quality:" + stage)
            success = g["scenarios"][model][name]
            if success is None:
                if a["kind"] not in {"diagnostic", "repair"}:
                    reasons.append("unknown_effect:" + name)
                break
            if not success:
                break
            if a["kind"] == "verification_investment":
                hypothetical["measured_verifier_service"][a["produces"]] = a["service_measurement"]
            if a["produces"]:
                hypothetical["eligible_assets"].append(a["produces"])
                hypothetical["receiver_qualifications"].append(f"{a['produces']}:{a['receiver']}")
            if a["kind"] == "transfer_validation":
                hypothetical["receiver_qualifications"].extend(
                    f"{asset}:{a['receiver']}" for asset in a["requires"]
                )
            key = service_key(run, a, group)
            if key not in seen:
                for k in gains:
                    gains[k] += a["gains"][k]
                seen.add(key)
        value = min(Fraction(min(gains[k], g["targets"][k]), g["targets"][k]) for k in gains)
        worst = value if worst is None else min(worst, value)
        forecasts.append({"scenario": model, "service": gains})
    if remaining:
        reasons.extend(prerequisites(g, g["actions"][remaining[0]], ledger))
    return {
        "steps": remaining,
        "reservation": totals,
        "duration_seconds": elapsed,
        "objective": str(worst) if worst is not None else None,
        "scenario_forecasts": forecasts,
        "violations": sorted(set(reasons)),
        "immediate_step": remaining[0] if remaining else None,
    }


def service_key(run: dict[str, Any], action: dict[str, Any], group: str) -> str:
    return sha256_json(service_identity(run, action, group))


def service_identity(run: dict[str, Any], action: dict[str, Any], group: str) -> dict[str, Any]:
    target = next(
        t for t in run["config"]["task_manifest"] if t["target_id"] == action["target_id"]
    )
    receiver = run["config"]["growth"]["receivers"][action["receiver"]]
    return {
        "study": run["config"]["growth"]["study_id"],
        "arm": group,
        "target": action["target_id"],
        "input": target["input_sha256"],
        "receiver": action["receiver"],
        "protocol": receiver["protocol"],
    }


def plan(
    run: dict[str, Any], current: str, *, restricted: bool = False, baseline: bool = False
) -> dict[str, Any]:
    from ccr.optimizer.engine import response

    g = run["config"]["growth"]
    blockers = list(run["blockers"])
    if run["state"] == "stopped" or timestamp(current) >= timestamp(run["config"]["deadline"]):
        blockers.append("run_not_active")
    if any(t["state"] != "evaluated" for t in run["trials"]):
        blockers.append("waiting_for_verified_result")
    if any(t["state"] in {"dispatching", "outcome_unknown"} for t in run["trials"]):
        blockers.append("unresolved_execution")
    group = "training" if not run["frozen_policy"] else "candidate"
    if baseline:
        group = "baseline"
        restricted = True
    catalog = sorted(g["comparison"]["restricted_bundles"] if restricted else g["bundles"])
    candidates = []
    holdout = set(run["config"]["evaluation"]["holdout_tasks"])
    for name in catalog[: g["candidate_limit"]]:
        steps = g["bundles"][name]
        if any((g["actions"][s]["target_id"] in holdout) != (group != "training") for s in steps):
            continue
        row = evaluate(run, steps, current, group)
        candidates.append({"bundle_id": name, **row})
    valid = [c for c in candidates if not c["violations"]]
    valid.sort(
        key=lambda c: (
            -Fraction(c["objective"]),
            *(c["reservation"][k] for k in g["cost_order"]),
            c["duration_seconds"],
            c["bundle_id"],
        )
    )
    attained = min(
        Fraction(min(v, g["targets"][k]), g["targets"][k])
        for k, v in replay(run, current, group=group)["observed_service"].items()
    )
    justified = [
        c
        for c in valid
        if Fraction(c["objective"]) > attained
        or g["actions"][c["immediate_step"]]["kind"] in {"diagnostic", "repair"}
    ]
    chosen = justified[0] if justified and not blockers else None
    if chosen is None and not blockers and group == "candidate" and not restricted:
        return plan(run, current, baseline=True)
    if chosen is None and not blockers:
        blockers.append(
            "no_admissible_bundle"
            if len(catalog) <= g["candidate_limit"]
            else "search_incomplete_unknown"
        )
    selected = None
    if chosen:
        a = g["actions"][chosen["immediate_step"]]
        selected = {
            "intervention_id": a["intervention_id"],
            "target_id": a["target_id"],
            "group": group,
        }
    return response(
        schema_version=PLAN,
        run_id=run["run_id"],
        revision=run["revision"],
        config_digest=run["config"]["config_digest"],
        selected=selected,
        chosen=chosen,
        candidates=candidates,
        blockers=blockers,
        ok=not blockers,
        reason="bounded_joint_forecast",
        evaluated_at=current,
        search={
            "catalogue_size": len(catalog),
            "enumerated": min(len(catalog), g["candidate_limit"]),
            "complete": len(catalog) <= g["candidate_limit"],
            "max_steps": g["max_steps"],
            "horizon_seconds": g["horizon_seconds"],
            "scope": "registered_catalogue_only",
        },
        forecast_not_observed=True,
        global_optimality=False,
    )
