# SPDX-License-Identifier: Apache-2.0
"""Independent bundle replay; deliberately does not call the search evaluator."""

from __future__ import annotations

from datetime import timedelta
from fractions import Fraction
from typing import Any

from ccr.optimizer.growth_ledger import replay
from ccr.optimizer.model import timestamp


def check(run: dict[str, Any], proposal: dict[str, Any], current: str) -> dict[str, Any]:
    from ccr.optimizer.engine import accounting
    from ccr.optimizer.growth_planner import service_key

    errors = []
    if (
        proposal.get("revision") != run["revision"]
        or proposal.get("config_digest") != run["config"]["config_digest"]
    ):
        errors.append("stale_plan")
    g = run["config"]["growth"]
    chosen = proposal.get("chosen")
    if not isinstance(chosen, dict):
        return {"ok": False, "blockers": [*errors, "no_submitted_bundle"]}
    group = "training" if not run["frozen_policy"] else "candidate"
    if proposal.get("selected", {}).get("group") == "baseline":
        group = "baseline"
        if chosen.get("bundle_id") not in g["comparison"]["restricted_bundles"]:
            errors.append("unregistered_baseline")
    original = g["bundles"].get(chosen.get("bundle_id"))
    completed = {t["growth_action"] for t in run["trials"] if t["group"] == group}
    expected = [s for s in original or [] if s not in completed]
    if (
        chosen.get("steps") != expected
        or not expected
        or chosen.get("immediate_step") != expected[0]
    ):
        return {"ok": False, "blockers": [*errors, "modified_dependencies"]}
    immediate = g["actions"][expected[0]]
    if proposal.get("selected") != {
        "group": group,
        "intervention_id": immediate["intervention_id"],
        "target_id": immediate["target_id"],
    }:
        errors.append("modified_immediate_dispatch")
    if group == "baseline" and not run["frozen_policy"]:
        errors.append("baseline_before_freeze")
    ledger = replay(run, current, group=group)
    scenarios = (
        ledger["compatible_scenarios"]
        if not run["frozen_policy"]
        else run["frozen_policy"]["compatible_scenarios"]
    )
    if not scenarios:
        errors.append("inconsistent_models")
    budget = accounting(run, group)
    reserved = dict.fromkeys(g["units"]["costs"], 0)
    elapsed = 0
    objectives = []
    for step in expected:
        a = g["actions"][step]
        arm = next(
            i
            for i in run["config"]["interventions"]
            if i["intervention_id"] == a["intervention_id"]
        )
        elapsed += a["duration_seconds"] + a["cleanup_seconds"]
        for k in reserved:
            reserved[k] += arm["resource_upper_bound"][k] + a["cleanup_cost"][k]
            if reserved[k] > budget["remaining"][k]:
                errors.append("prefix_budget:" + k)
        for k, amount in a["capacity"].items():
            if amount > g["quota"]["capacity"][k]:
                errors.append("shared_capacity:" + k)
    if chosen.get("reservation") != reserved or chosen.get("duration_seconds") != elapsed:
        errors.append("modified_reservation_or_duration")
    if group == "training" and any(
        g["actions"][s]["kind"] not in {"diagnostic", "repair"} for s in expected
    ):
        for k in reserved:
            if (
                reserved[k] + budget["used"][k] + budget["reserved"][k]
                > budget["budget"][k] - g["diagnostic_budget"][k]
            ):
                errors.append("diagnostic_budget:" + k)
    if elapsed > g["horizon_seconds"] or timestamp(current) + timedelta(
        seconds=elapsed
    ) > timestamp(g["window_end"]):
        errors.append("terminal_window")
    for scenario in scenarios:
        available = set(ledger["eligible_assets"])
        qualified = set(ledger["receiver_qualifications"])
        gains = dict(ledger["observed_service"])
        credited = set(ledger["service_events"])
        offered = dict(ledger["measured_verifier_service"])
        offset = 0
        for step in expected:
            a = g["actions"][step]
            offset += a["duration_seconds"] + a["cleanup_seconds"]
            receiver = g["receivers"][a["receiver"]]
            for asset in a["requires"]:
                spec = g["assets"][asset]
                if asset not in available or a["receiver"] not in spec["receivers"]:
                    errors.append("dependency_or_scope")
                if (
                    spec["source_mission"] != receiver["mission_id"]
                    and not receiver["cross_mission_allowed"]
                ):
                    errors.append("cross_mission_grant")
                if timestamp(spec["expires_at"]) <= timestamp(current) + timedelta(seconds=offset):
                    errors.append("dependency_expiry")
                if (
                    a["kind"] != "transfer_validation"
                    and f"{asset}:{a['receiver']}" not in qualified
                ):
                    errors.append("receiver_qualification")
            for stage, demand in a["verification_work"].items():
                stage_spec = g["verifier_stages"][stage]
                offerings = [stage_spec["service_units_per_second"]]
                offerings += [
                    offered[parent][stage] for parent in a["requires"] if parent in offered
                ]
                offers = [value for value in offerings if value is not None]
                if demand and (
                    not offers
                    or demand > max(offers) * a["duration_seconds"]
                    or receiver["domain"] not in stage_spec["domains"]
                    or receiver["quality"] != stage_spec["quality"]
                    or timestamp(stage_spec["fresh_until"])
                    < timestamp(current) + timedelta(seconds=offset)
                ):
                    errors.append("verification_obligation:" + stage)
            effect = g["scenarios"][scenario][step]
            if effect is None and a["kind"] not in {"diagnostic", "repair"}:
                errors.append("unknown_effect")
            if effect is not True:
                break
            if a["kind"] == "verification_investment":
                offered[a["produces"]] = a["service_measurement"]
            if a["produces"]:
                available.add(a["produces"])
                qualified.add(f"{a['produces']}:{a['receiver']}")
            if a["kind"] == "transfer_validation":
                qualified.update(f"{asset}:{a['receiver']}" for asset in a["requires"])
            identity = service_key(run, a, group)
            if identity not in credited:
                for k in gains:
                    gains[k] += a["gains"][k]
                credited.add(identity)
        objectives.append(
            min(Fraction(min(gains[k], g["targets"][k]), g["targets"][k]) for k in gains)
        )
    if objectives and chosen.get("objective") != str(min(objectives)):
        errors.append("modified_objective")
    if (
        run["blockers"]
        or run["state"] == "stopped"
        or any(t["state"] != "evaluated" for t in run["trials"])
    ):
        errors.append("runtime_not_dispatchable")
    return {
        "ok": not errors,
        "blockers": sorted(set(errors)),
        "recomputed_reservation": reserved,
        "recomputed_objective": str(min(objectives)) if objectives else None,
        "external_dispatch_authorized": False,
    }
