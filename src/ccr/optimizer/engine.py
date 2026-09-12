# SPDX-License-Identifier: Apache-2.0
"""Finite optimizer transitions. No shell execution or implicit provider calls."""

from __future__ import annotations

import base64
import copy
import importlib
import random
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from ccr.constants import NON_CLAIMS
from ccr.experiments.protocol import compare_experiment_results
from ccr.ids import canonical_bytes, sha256_json, stable_id, validate_identifier
from ccr.optimizer.model import (
    KINDS,
    PLAN_VERSION,
    REPORT_VERSION,
    TRIAL_VERSION,
    WORKFLOWS,
    normalize_config,
    timestamp,
    vector,
)
from ccr.phase.eligibility import packet_eligibility
from ccr.schemas.validation import validate_instance
from ccr.storage.control import ControlStore
from ccr.tasks.factory import build_task


def response(**fields: Any) -> dict[str, Any]:
    return {
        "schema_version": REPORT_VERSION,
        "ok": True,
        "settled": False,
        "external_execution": False,
        "network_call_performed": False,
        "mutated_runtime": False,
        "blockers": [],
        "residuals": [],
        "non_claims": list(NON_CLAIMS),
        **fields,
    }


def initialize(store: ControlStore, *, mission: str, config: dict[str, Any]) -> dict[str, Any]:
    from ccr.mission.model import mission_path, mission_scope

    validate_identifier(mission, field="mission")
    if config.get("schema_version") == "ccr.growth_profile.v1":
        from ccr.optimizer.growth_runtime import initialize as growth_initialize

        return growth_initialize(store, mission, config)
    normalized = normalize_config(config)
    initial: dict[str, Any] = {"packets": [], "residuals": []}
    if mission_path(store.root, mission).exists():
        scope = mission_scope(store.root, mission)
        if not scope["ok"]:
            raise ValueError("mission scope must be valid before optimizer registration")
        initial = {"packets": scope["packets"], "residuals": scope["residuals"]}
    credited = {}
    for packet in initial["packets"]:
        if packet_eligibility(store.root, packet)["positive_contribution"]:
            for artifact in packet.get("artifacts", []):
                digest = str(artifact.get("content_sha256", ""))
                if len(digest) == 64:
                    credited[f"collective:{digest}"] = "initial_capability"
                    credited[f"baseline:{digest}"] = "initial_capability"
    run_id = stable_id("optimizer", mission, normalized)
    with store.edit(run_id, create=True) as (run, current):
        if timestamp(normalized["deadline"]) <= timestamp(current):
            raise ValueError("deadline must be in the future")
        run.update(
            run_id=run_id,
            mission_id=mission,
            config=normalized,
            revision=0,
            created_at=current,
            state="training",
            trials=[],
            credited=credited,
            blockers=[],
            residuals=copy.deepcopy(initial["residuals"]),
            initial_snapshot=initial,
            initial_snapshot_digest=sha256_json(initial),
            frozen_policy=None,
        )
    return response(run_id=run_id, config_digest=normalized["config_digest"], mutated_runtime=True)


def load(store: ControlStore, run_id: str) -> dict[str, Any]:
    validate_identifier(run_id, field="run_id")
    run = store.read(run_id)
    if run is None or "trials" not in run:
        raise FileNotFoundError(run_id)
    return run


@contextmanager
def edit_run(store: ControlStore, run_id: str) -> Iterator[tuple[dict[str, Any], str]]:
    validate_identifier(run_id, field="run_id")
    if not run_id.startswith("optimizer:"):
        raise ValueError("optimizer run id required")
    with store.edit(run_id) as (run, current):
        if run.get("run_id") != run_id:
            raise ValueError("optimizer run identity mismatch")
        yield run, current


def accounting(run: dict[str, Any], group: str) -> dict[str, Any]:
    config = run["config"]
    limits = config["resource_limits"]
    evaluation = config["evaluation"]["resource_envelope"]
    budget = (
        {k: limits[k] - 2 * evaluation[k] for k in limits}
        if group == "training"
        else dict(evaluation)
    )
    zero = 0 if "growth" in config else 0.0
    used = dict.fromkeys(limits, zero)
    reserved = dict.fromkeys(limits, zero)
    diagnostic = dict.fromkeys(limits, zero)
    for trial in run["trials"]:
        if trial["group"] != group and not (group == "candidate" and trial["group"] == "training"):
            continue
        actual = trial.get("actual_resources")
        cost = actual if actual is not None else trial["reserved_resources"]
        destination = used if actual is not None else reserved
        for key in limits:
            destination[key] += cost[key]
            if trial["kind"] == "measurement":
                diagnostic[key] += cost[key]
    if run.get("growth_reservation"):
        future = run["growth_reservation"]
        if future["group"] == group or (group == "candidate" and future["group"] == "training"):
            for key in reserved:
                reserved[key] += future["future"][key]
    return {
        "budget": budget,
        "used": used,
        "reserved": reserved,
        "diagnostic": diagnostic,
        "remaining": {k: budget[k] - used[k] - reserved[k] for k in limits},
    }


def scores(run: dict[str, Any]) -> dict[str, float | None]:
    config = run["config"]
    result: dict[str, float | None] = {}
    for arm in config["interventions"]:
        trials = [
            t
            for t in run["trials"]
            if t["group"] == "training"
            and t["intervention_id"] == arm["intervention_id"]
            and t["state"] == "evaluated"
        ]
        cost = sum(t["actual_resources"][config["effort_resource"]] for t in trials)
        result[arm["intervention_id"]] = (
            sum(t["reward"] for t in trials) / cost if cost > 0 else None
        )
    return result


def _plan(run: dict[str, Any], current: str) -> dict[str, Any]:
    if "growth" in run["config"]:
        from ccr.optimizer.growth_planner import plan as growth_plan

        return growth_plan(run, current)
    config = run["config"]
    blockers = list(run["blockers"])
    if run["state"] == "stopped":
        blockers.append("stopped")
    if timestamp(current) >= timestamp(config["deadline"]):
        blockers.append("deadline_reached")
    if any(t["state"] in {"dispatching", "outcome_unknown"} for t in run["trials"]):
        blockers.append("unresolved_execution")
    active = sum(t["state"] != "evaluated" for t in run["trials"])
    if active >= config["max_inflight"]:
        blockers.append("waiting_for_results")
    group = "training" if run["state"] == "training" else "candidate"
    holdout = config["evaluation"]["holdout_tasks"]
    ranking = scores(run)
    candidates = []
    for candidate_group in ["training"] if group == "training" else ["candidate", "baseline"]:
        book = accounting(run, candidate_group)
        for target in config["task_manifest"]:
            is_holdout = target["target_id"] in holdout
            if is_holdout != (candidate_group != "training"):
                continue
            if any(
                t["target_id"] == target["target_id"] and t["group"] == candidate_group
                for t in run["trials"]
            ):
                continue
            for arm in config["interventions"]:
                if (
                    candidate_group == "baseline"
                    and arm["intervention_id"] != config["evaluation"]["baseline_intervention"]
                ):
                    continue
                cost = arm["resource_upper_bound"]
                if any(cost[k] > book["remaining"][k] + 1e-12 for k in cost):
                    continue
                reserve = config["diagnostic_reserve"] if candidate_group == "training" else 0
                if arm["kind"] != "measurement" and any(
                    book["used"][k] + book["reserved"][k] - book["diagnostic"][k] + cost[k]
                    > book["budget"][k] * (1 - reserve) + 1e-12
                    for k in cost
                ):
                    continue
                candidates.append(
                    {
                        "intervention_id": arm["intervention_id"],
                        "target_id": target["target_id"],
                        "group": candidate_group,
                    }
                )
    candidates.sort(key=lambda item: (item["group"], item["target_id"], item["intervention_id"]))
    selected = None
    reason = "no_feasible_candidate"
    if candidates and not blockers:
        rng = random.Random(f"{config['seed']}:{run['revision']}")
        if group == "training" and rng.random() < config["epsilon"]:
            selected = rng.choice(candidates)
            reason = "exploration"
        else:
            weights = ranking if group == "training" else run["frozen_policy"]["scores"]
            selected = max(candidates, key=lambda c: weights.get(c["intervention_id"]) or 0.0)
            reason = "observed_efficiency" if group == "training" else "frozen_policy"
    if not candidates:
        blockers.append(reason)
    return response(
        schema_version=PLAN_VERSION,
        run_id=run["run_id"],
        revision=run["revision"],
        config_digest=config["config_digest"],
        selected=selected,
        candidates=candidates,
        scores=ranking,
        reason=reason,
        blockers=sorted(set(blockers)),
        ok=not blockers,
        accounts={g: accounting(run, g) for g in ("training", "candidate", "baseline")},
    )


def plan(store: ControlStore, run_id: str) -> dict[str, Any]:
    return _plan(load(store, run_id), store.now())


def step(
    store: ControlStore, run_id: str, *, apply: bool = False, expected_revision: int | None = None
) -> dict[str, Any]:
    if not apply:
        return plan(store, run_id)
    with edit_run(store, run_id) as (run, current):
        if expected_revision is not None and expected_revision != run["revision"]:
            return response(ok=False, blockers=["stale_revision"])
        proposal = _plan(run, current)
        choice = proposal["selected"]
        if not choice:
            return proposal
        config = run["config"]
        arm = next(
            a for a in config["interventions"] if a["intervention_id"] == choice["intervention_id"]
        )
        target = next(t for t in config["task_manifest"] if t["target_id"] == choice["target_id"])
        trial_id = stable_id("trial", run_id, run["revision"], choice)
        task = build_task(
            kind=f"optimizer_{arm['kind']}",
            title=f"{arm['kind']}: {target['target_id']}",
            objective=f"{WORKFLOWS[arm['kind']]} {target['acceptance_criteria']}",
            role=KINDS[arm["kind"]],
            source=trial_id,
            inputs=[
                {
                    "kind": "artifact",
                    "ref": target["input_ref"],
                    "required": True,
                    "notes": f"Expected source SHA256: {target['input_sha256']}",
                }
            ],
            extensions={
                "x_optimizer_run": run_id,
                "x_optimizer_trial": trial_id,
                "x_mission_id": run["mission_id"],
            },
        )
        task["expected_outputs"][0]["acceptance_criteria"] = [
            target["acceptance_criteria"],
            "Independent artifact-bound verification is required.",
        ]
        task["created_at"] = current
        checked = validate_instance("task", task)
        if not checked.ok:
            raise ValueError("invalid generated optimizer task: " + str(checked.errors))
        trial = {
            "schema_version": TRIAL_VERSION,
            "trial_id": trial_id,
            "run_id": run_id,
            **choice,
            "kind": arm["kind"],
            "policy_version": config["policy_version"],
            "config_digest": config["config_digest"],
            "input_digest": sha256_json(target),
            "reserved_resources": dict(arm["resource_upper_bound"]),
            "actual_resources": None,
            "state": "awaiting_approval" if "operation_plan" in arm else "queued",
            "task": task,
            "created_at": current,
            "fencing_token": 0,
            "worker_id": None,
            "lease_expires_at": None,
            "reward": None,
            "result_digest": None,
            "dispatch_report": None,
            "residuals": [],
            "blockers": [],
            "selection_reason": proposal["reason"],
        }
        if "operation_plan" in arm:
            operation = copy.deepcopy(arm["operation_plan"])
            operation["plan_id"] = stable_id("plan:optimizer", trial_id)
            operation["optimizer_binding"] = {
                "run_id": run_id,
                "trial_id": trial_id,
                "input_digest": trial["input_digest"],
                "config_digest": config["config_digest"],
                "input_sha256": target["input_sha256"],
                "intervention_id": arm["intervention_id"],
                "kind": arm["kind"],
                "group": choice["group"],
            }
            operation["operations"][0]["input_ref"] = target["input_ref"]
            operation["operations"][0]["resource_use"] = dict(arm["resource_upper_bound"])
            operation["operations"][0]["postcondition"] = target["acceptance_criteria"]
            trial["operation_plan"] = operation
        if "growth" in config:
            from ccr.optimizer.growth_runtime import prepare

            prepare(run, proposal, trial, current)
        run["trials"].append(trial)
        run["revision"] += 1
        return response(run_id=run_id, trial=copy.deepcopy(trial), mutated_runtime=True)


def _trial(run: dict[str, Any], trial_id: str) -> dict[str, Any]:
    for trial in run["trials"]:
        if trial["trial_id"] == trial_id:
            return dict_ref(trial)
    raise FileNotFoundError(trial_id)


def dict_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("object required")
    return value


def claim(
    store: ControlStore, run_id: str, trial_id: str, *, worker: str, ttl_seconds: int = 1800
) -> dict[str, Any]:
    validate_identifier(worker, field="worker")
    if isinstance(ttl_seconds, bool) or not 1 <= ttl_seconds <= 3600:
        raise ValueError("lease TTL must be 1..3600 seconds")
    with edit_run(store, run_id) as (run, current):
        trial = _trial(run, trial_id)
        if run["state"] == "stopped" or timestamp(current) >= timestamp(run["config"]["deadline"]):
            return response(ok=False, blockers=["run_not_active"])
        if "growth" in run["config"]:
            from ccr.optimizer.growth_ledger import prerequisites, replay

            action = run["config"]["growth"]["actions"][trial["growth_action"]]
            missing = prerequisites(
                run["config"]["growth"], action, replay(run, current, group=trial["group"])
            )
            if missing:
                return response(ok=False, blockers=missing)
        if trial["state"] not in {"queued", "awaiting_approval", "leased"}:
            return response(ok=False, blockers=["trial_not_claimable"])
        if trial["lease_expires_at"] and timestamp(trial["lease_expires_at"]) > timestamp(current):
            return response(ok=False, blockers=["lease_active"])
        trial.update(
            worker_id=worker,
            fencing_token=trial["fencing_token"] + 1,
            state="leased",
            lease_expires_at=(timestamp(current) + timedelta(seconds=ttl_seconds)).isoformat(),
        )
        return response(
            task=trial["task"],
            task_id=trial["task"]["task_id"],
            trial_id=trial_id,
            fencing_token=trial["fencing_token"],
            mutated_runtime=True,
        )


def check_lease(trial: dict[str, Any], current: str, worker: str, token: int) -> None:
    if (
        isinstance(token, bool)
        or trial["worker_id"] != worker
        or trial["fencing_token"] != token
        or not trial["lease_expires_at"]
        or timestamp(trial["lease_expires_at"]) <= timestamp(current)
    ):
        raise ValueError("stale or expired optimizer lease")


def task_transition(
    store: ControlStore,
    run_id: str,
    trial_id: str,
    *,
    worker: str,
    token: int,
    result: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    with edit_run(store, run_id) as (run, current):
        trial = _trial(run, trial_id)
        if result is not None and trial.get("completion_key") == idempotency_key:
            if trial.get("completion_digest") != sha256_json(result):
                raise ValueError("conflicting idempotent completion")
            return response(task_id=trial["task"]["task_id"], idempotent=True)
        check_lease(trial, current, worker, token)
        if trial["state"] not in {"leased", "awaiting_result"}:
            raise ValueError("trial cannot be completed or heartbeated in this state")
        if result is None:
            trial["lease_expires_at"] = (timestamp(current) + timedelta(minutes=30)).isoformat()
        else:
            if not idempotency_key:
                raise ValueError("completion idempotency key required")
            trial.update(
                state="awaiting_verification",
                completion_key=idempotency_key,
                completion_digest=sha256_json(result),
                candidate_result=result,
            )
        return response(task_id=trial["task"]["task_id"], mutated_runtime=True)


def dispatch(
    store: ControlStore,
    run_id: str,
    *,
    trial_id: str,
    worker: str,
    token: int,
    config: dict[str, Any],
    execute: bool = False,
) -> dict[str, Any]:
    if not execute:
        return response(
            operation_plan=_trial(load(store, run_id), trial_id).get("operation_plan"),
            next_action="operation approve then optimizer run --execute",
        )
    with edit_run(store, run_id) as (run, current):
        trial = _trial(run, trial_id)
        if run["state"] == "stopped" or timestamp(current) >= timestamp(run["config"]["deadline"]):
            return response(ok=False, blockers=["run_not_active"])
        if "growth" in run["config"]:
            from ccr.optimizer.growth_ledger import prerequisites, replay

            action = run["config"]["growth"]["actions"][trial["growth_action"]]
            missing = prerequisites(
                run["config"]["growth"], action, replay(run, current, group=trial["group"])
            )
            if missing:
                return response(ok=False, blockers=missing)
        check_lease(trial, current, worker, token)
        if trial["state"] != "leased" or "operation_plan" not in trial:
            return response(ok=False, blockers=["trial_not_dispatchable"])
        if not config.get("operator_approval_ref"):
            return response(ok=False, blockers=["operator_approval_required"])
        trial["state"] = "dispatching"
        from ccr.operations.approval import dispatch_config_digest

        trial["dispatch_config_digest"] = dispatch_config_digest(config)
        operation = copy.deepcopy(trial["operation_plan"])
    # A crash from here onward is deliberately non-retryable without observation.
    from ccr.extensions import operation_dispatch

    try:
        report = operation_dispatch(
            store.root,
            plan=operation,
            provider_name="http",
            config=config,
            execute=True,
            control_store=store,
        )
    except Exception as exc:
        report = {"ok": False, "error_type": type(exc).__name__, "outcome_unknown": True}
    with edit_run(store, run_id) as (run, current):
        trial = _trial(run, trial_id)
        if trial["fencing_token"] != token or trial["state"] != "dispatching":
            raise ValueError("dispatch state changed; reconcile external observation")
        trial["dispatch_report"] = report
        rejected_before_send = bool(report.get("residual_ready")) and not report.get("approval_id")
        trial["state"] = (
            "leased"
            if rejected_before_send
            else ("awaiting_result" if report.get("ok") else "outcome_unknown")
        )
        if not report.get("ok"):
            residual = report.get("residual_ready") or {
                "kind": "outcome_unknown",
                "blocking": True,
                "trial_id": trial_id,
            }
            trial["residuals"].append(residual)
        return response(
            ok=bool(report.get("ok")),
            trial_id=trial_id,
            state=trial["state"],
            dispatch_report=report,
            mutated_runtime=True,
            external_execution=True
            if report.get("network_call_performed")
            else (None if trial["state"] == "outcome_unknown" else False),
            network_call_performed=report.get(
                "network_call_performed", None if trial["state"] == "outcome_unknown" else False
            ),
        )


def _verify(config: dict[str, Any], result: dict[str, Any]) -> None:
    verifier = result.get("verifier_id")
    producers = {p for arm in config["interventions"] for p in arm["producer_ids"]}
    if (
        verifier not in config["trusted_verifiers"]
        or verifier in producers
        or verifier == result.get("worker_id")
    ):
        raise ValueError("verifier is untrusted or not independent")
    payload = {k: v for k, v in result.items() if k != "signature_base64"}
    try:
        ed = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        public = base64.b64decode(config["trusted_verifiers"][verifier], validate=True)
        signature = base64.b64decode(result["signature_base64"], validate=True)
        ed.Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical_bytes(payload))
    except Exception as exc:
        raise ValueError("independent verifier signature invalid or crypto unavailable") from exc


def _result_ledger(
    run: dict[str, Any], trial: dict[str, Any], result: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ledger = copy.deepcopy(run["residuals"])
    target = next(t for t in run["config"]["task_manifest"] if t["target_id"] == trial["target_id"])
    resolved = set(result.get("resolved_residual_ids", []))
    if resolved and trial["kind"] != "residual_repair":
        raise ValueError("residual resolution requires a registered repair intervention")
    found = set()
    for residual in ledger:
        if residual.get("residual_id") not in resolved:
            continue
        if not (
            residual.get("residual_id") == target["input_ref"]
            or residual.get("object_id") in {target["input_ref"], trial["target_id"]}
        ):
            raise ValueError("residual resolution outside registered repair scope")
        found.add(residual["residual_id"])
        residual.update(
            status="resolved",
            resolution={
                "result_digest": sha256_json(result),
                "artifact_sha256": result["artifact_sha256"],
                "verifier_id": result["verifier_id"],
            },
        )
    if found != resolved:
        raise ValueError("unknown residual resolution id")
    subjects = {
        trial["target_id"],
        target["input_ref"],
        run["mission_id"],
        result["packet"]["packet_id"],
    }
    blockers = []
    for residual in ledger:
        owner = residual.get("object_id") or residual.get("optimizer_target_id")
        refs = residual.get("refs", [])
        if (
            residual.get("blocking") is True
            and residual.get("status") != "resolved"
            and (
                owner in subjects
                or (isinstance(refs, list) and any(ref in subjects for ref in refs))
                or (not owner and not refs)
            )
        ):
            blockers.append(residual)
    return ledger, blockers


def ingest(store: ControlStore, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
    if result.get("schema_version") == "ccr.growth_result.v1":
        from ccr.optimizer.growth_runtime import ingest as growth_ingest

        return growth_ingest(store, run_id, result)
    with edit_run(store, run_id) as (run, current):
        if "growth" in run["config"]:
            raise ValueError("growth run requires the separate signed growth envelope")
        return _ingest_result(store, run, current, result)


def _ingest_result(
    store: ControlStore, run: dict[str, Any], current: str, result: dict[str, Any]
) -> dict[str, Any]:
    validation = validate_instance("optimizer-result", result)
    if not validation.ok:
        raise ValueError("invalid optimizer result: " + str(validation.errors))
    config = run["config"]
    _verify(config, result)
    trial = _trial(run, result["trial_id"])
    digest = sha256_json(result)
    if trial["result_digest"]:
        if trial["result_digest"] != digest:
            raise ValueError("conflicting result for evaluated trial")
        return response(trial_id=trial["trial_id"], reward=trial["reward"], idempotent=True)
    for field in (
        "run_id",
        "target_id",
        "config_digest",
        "input_digest",
        "worker_id",
        "fencing_token",
    ):
        if result[field] != trial[field]:
            raise ValueError(f"result {field} does not match trial")
    if trial["worker_id"] is None or trial["state"] not in {
        "leased",
        "awaiting_result",
        "awaiting_verification",
        "outcome_unknown",
        "dispatching",
    }:
        raise ValueError("trial has no attributable execution")
    if "operation_plan" in trial and not trial.get("dispatch_config_digest"):
        raise ValueError("external trial was not dispatched")
    # Signed observation can reconcile an expired/crashed dispatch, but never a new fence.
    observed = timestamp(result["observed_at"])
    if observed < timestamp(trial["created_at"]) or observed > timestamp(current):
        raise ValueError("result observation time outside trial window")
    actual = vector(result["actual_resources"], config["resource_limits"])
    if actual[config["effort_resource"]] <= 0:
        raise ValueError("actual effort must include positive total evaluation and control cost")
    overrun = any(actual[k] > trial["reserved_resources"][k] for k in actual)
    reward = 0.0
    reasons = []
    if overrun:
        run["blockers"].append("resource_overrun")
        reasons.append("resource_overrun")
    residuals = result["residuals"]
    if result["accepted"] and not overrun:
        packet = result.get("packet")
        if not isinstance(packet, dict):
            reasons.append("verified_packet_required")
        else:
            packet_check = validate_instance("packet", packet)
            if not packet_check.ok:
                reasons.append("packet_not_eligible")
            else:
                artifact_hashes = {a.get("content_sha256") for a in packet.get("artifacts", [])}
                if (
                    not result.get("artifact_sha256")
                    or result["artifact_sha256"] not in artifact_hashes
                ):
                    reasons.append("reusable_artifact_digest_mismatch")
                if packet["issuer"]["actor_id"] == result["verifier_id"]:
                    reasons.append("packet_verifier_not_independent")
                if any(r.get("blocking") is True for r in residuals):
                    reasons.append("blocking_residual")
                if not reasons:
                    ledger, known_blockers = _result_ledger(run, trial, result)
                    eligible = packet_eligibility(
                        store.root, packet, ledger_blockers=known_blockers
                    )
                    if not eligible["positive_contribution"]:
                        reasons.append("packet_not_eligible")
                    else:
                        run["residuals"] = ledger
            credit_group = "baseline" if trial["group"] == "baseline" else "collective"
            artifact_key = f"{credit_group}:{result.get('artifact_sha256')}"
            target_key = f"{trial['group']}:target:{trial['target_id']}"
            if artifact_key in run["credited"] or target_key in run["credited"]:
                reasons.append("duplicate_outcome")
            if not reasons:
                reward = 1.0
                run["credited"].update(
                    {artifact_key: trial["trial_id"], target_key: trial["trial_id"]}
                )
    trial.update(
        state="evaluated",
        actual_resources=actual,
        reward=reward,
        result_digest=digest,
        result=result,
        blockers=reasons,
    )
    trial["residuals"].extend(residuals)
    run["residuals"].extend({**r, "optimizer_target_id": trial["target_id"]} for r in residuals)
    run["revision"] += 1
    return response(
        trial_id=trial["trial_id"],
        reward=reward,
        blockers=reasons,
        residuals=trial["residuals"],
        mutated_runtime=True,
    )


def freeze(store: ControlStore, run_id: str) -> dict[str, Any]:
    with edit_run(store, run_id) as (run, current):
        if run["state"] != "training" or run["blockers"]:
            raise ValueError("only an unblocked training run can be frozen")
        if not run["trials"] or any(t["state"] != "evaluated" for t in run["trials"]):
            raise ValueError("complete training observations before freezing")
        policy = {"scores": scores(run), "frozen_at": current, "training_revision": run["revision"]}
        if "growth" in run["config"]:
            from ccr.optimizer.growth_runtime import freeze as growth_freeze

            policy = growth_freeze(run, current)
        policy["policy_digest"] = sha256_json(policy)
        run.update(frozen_policy=policy, state="evaluation", revision=run["revision"] + 1)
        return response(frozen_policy=policy, mutated_runtime=True)


def stop(store: ControlStore, run_id: str) -> dict[str, Any]:
    with edit_run(store, run_id) as (run, current):
        run.update(state="stopped", stopped_at=current)
    return response(run_id=run_id, state="stopped", mutated_runtime=True)


def report(store: ControlStore, run_id: str) -> dict[str, Any]:
    run = load(store, run_id)
    config = run["config"]
    if "growth" in config:
        from ccr.optimizer.growth_runtime import report as growth_report

        return growth_report(store, run)
    evaluation = config["evaluation"]
    arms: dict[str, Any] = {}
    complete = bool(run["frozen_policy"])
    for group in ("baseline", "candidate"):
        rows = {
            t["target_id"]: t
            for t in run["trials"]
            if t["group"] == group and t["state"] == "evaluated"
        }
        complete = complete and set(rows) == set(evaluation["holdout_tasks"])
        arms[group] = {
            "outcomes": [rows[k]["reward"] for k in evaluation["holdout_tasks"] if k in rows],
            "resource_envelope": evaluation["resource_envelope"],
            "evaluation_design": {
                "mode": "fixed_horizon",
                "pre_registered": True,
                "horizon": evaluation["horizon"],
                "alpha": evaluation["alpha"],
            },
        }
    comparison = compare_experiment_results(arms["baseline"], arms["candidate"])
    admissible = complete and not run["blockers"] and comparison["acceleration_claim_admissible"]
    return response(
        run_id=run_id,
        state=run["state"],
        revision=run["revision"],
        config_digest=config["config_digest"],
        frozen_policy=run["frozen_policy"],
        accounts={g: accounting(run, g) for g in ("training", "candidate", "baseline")},
        trials=run["trials"],
        scores=scores(run),
        blockers=run["blockers"],
        residuals=run["residuals"],
        evaluation_complete=complete,
        comparison=comparison,
        improvement_claim_admissible=bool(admissible),
        next_action=_plan(run, store.now()),
        server_time=store.now(),
        limitations=[
            "Finite registered task protocol only; not real ASI or settlement.",
            "Resource totals include producer, communication, verifier and control costs.",
        ],
    )


def summaries(root: Path, mission: str | None = None) -> list[dict[str, Any]]:
    store = ControlStore(root)
    return [
        {
            "run_id": r["run_id"],
            "state": r["state"],
            "scores": scores(r),
            "pending_trials": sum(t["state"] != "evaluated" for t in r["trials"]),
            "approval_waiting": sum(
                "operation_plan" in t and t["state"] in {"awaiting_approval", "leased"}
                for t in r["trials"]
            ),
            "accounts": {g: accounting(r, g) for g in ("training", "candidate", "baseline")},
            "next_action": _plan(r, store.now()),
        }
        for r in store.list_objects("optimizer:")
        if mission is None or r["mission_id"] == mission
    ]
