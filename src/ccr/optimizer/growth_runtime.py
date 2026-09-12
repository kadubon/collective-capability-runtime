# SPDX-License-Identifier: Apache-2.0
"""Growth hooks in the existing optimizer transaction, task and signature lifecycle."""

from __future__ import annotations

import copy
from typing import Any

from ccr.ids import sha256_json, stable_id, validate_identifier
from ccr.optimizer import growth_checker, growth_ledger, growth_model, growth_planner
from ccr.optimizer.model import timestamp
from ccr.storage.control import ControlStore


def initialize(store: ControlStore, mission: str, raw: dict[str, Any]) -> dict[str, Any]:
    from ccr.mission.model import mission_path, mission_scope
    from ccr.optimizer.engine import response

    validate_identifier(mission, field="mission")
    config = growth_model.normalize(raw)
    g = config["growth"]
    for mission_id in {mission, *(r["mission_id"] for r in g["receivers"].values())}:
        if mission_path(store.root, mission_id).exists():
            scope = mission_scope(store.root, mission_id)
            if not scope["ok"] or scope["packets"] or scope["residuals"]:
                raise ValueError("growth empty checkpoint cannot ignore existing mission evidence")
    # This finite profile starts from an explicitly empty shared checkpoint.
    # Preexisting assets require a new formation/validation trial and its real cost.
    initial: dict[str, Any] = {"packets": [], "residuals": []}
    if g["checkpoint_digest"] != sha256_json(initial):
        raise ValueError("growth v1 requires the declared empty evidence checkpoint")
    run_id = stable_id("optimizer", mission, config)
    pool_key = "growth-pool:" + g["quota"]["pool_id"]
    study_key = "growth-study:" + g["study_id"]
    mode_key = "growth-evidence-mode"
    with store.edit_many(
        [run_id, pool_key, study_key, mode_key],
        create_keys={run_id, study_key},
        optional_keys={pool_key, mode_key},
    ) as (objects, current):
        if timestamp(g["window_end"]) <= timestamp(current):
            raise ValueError("registered observation window must be in the future")
        mode = objects[mode_key]
        if mode and mode["mode"] != g["evidence_mode"]:
            raise ValueError("synthetic and observational growth require isolated stores")
        mode["mode"] = g["evidence_mode"]
        pool = objects[pool_key]
        q = g["quota"]
        spec = {
            "budget": q["pool_budget"],
            "capacity": q["pool_capacity"],
            "units": g["units"]["costs"],
        }
        if pool and pool["spec"] != spec:
            raise ValueError("immutable shared pool specification mismatch")
        if not pool:
            pool.update(spec=spec, allocations={})
        for kind in ("budget", "capacity"):
            for k, total in spec[kind].items():
                used = sum(a[kind][k] for a in pool["allocations"].values())
                if used + q[kind][k] > total:
                    raise ValueError("shared quota overreservation: " + kind + ":" + k)
        pool["allocations"][run_id] = {
            "budget": q["budget"],
            "capacity": q["capacity"],
            "allocation_ref": q["allocation_ref"],
        }
        objects[study_key].update(run_id=run_id, config_digest=config["config_digest"])
        objects[run_id].update(
            run_id=run_id,
            mission_id=mission,
            config=config,
            revision=0,
            created_at=current,
            state="training",
            trials=[],
            credited={},
            blockers=[],
            residuals=[],
            initial_snapshot=initial,
            initial_snapshot_digest=g["checkpoint_digest"],
            frozen_policy=None,
            growth_events=[],
            growth_reservation=None,
        )
    return response(run_id=run_id, config_digest=config["config_digest"], mutated_runtime=True)


def prepare(
    run: dict[str, Any], proposal: dict[str, Any], trial: dict[str, Any], current: str
) -> None:
    checked = growth_checker.check(run, proposal, current)
    if not checked["ok"]:
        raise ValueError("independent plan check failed: " + str(checked["blockers"]))
    chosen = proposal["chosen"]
    g = run["config"]["growth"]
    name = chosen["immediate_step"]
    action = g["actions"][name]
    trial["growth_action"] = name
    trial["reserved_resources"] = growth_planner.cost(run, action)
    trial["task"]["extensions"]["x_growth"] = {
        "action_id": name,
        "kind": action["kind"],
        "receiver": g["receivers"][action["receiver"]],
        "required_assets": action["requires"],
        "output_asset": action["produces"],
        "verification_work": action["verification_work"],
        "cleanup_cost": action["cleanup_cost"],
        "independent_signed_result_required": True,
        "evidence_mode": g["evidence_mode"],
    }
    run["growth_reservation"] = {
        "group": trial["group"],
        "trial_id": trial["trial_id"],
        "future": {
            k: chosen["reservation"][k] - trial["reserved_resources"][k]
            for k in chosen["reservation"]
        },
        "plan": copy.deepcopy(proposal),
        "checker": checked,
    }
    growth_ledger.append(run, "reservation", copy.deepcopy(run["growth_reservation"]), current)


def ingest(store: ControlStore, run_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    from ccr.optimizer import engine
    from ccr.schemas.validation import validate_instance

    if not validate_instance("growth-result", envelope).ok:
        raise ValueError("invalid growth result schema")

    growth_model.closed(
        envelope, "schema_version result observation verifier_id worker_id signature_base64"
    )
    if envelope["schema_version"] != growth_model.RESULT:
        raise ValueError("growth result version required")
    with engine.edit_run(store, run_id) as (run, current):
        g = run["config"].get("growth")
        if not g:
            raise ValueError("growth evidence cannot enter legacy result accounting")
        engine._verify(run["config"], envelope)
        result = envelope["result"]
        if (
            envelope["verifier_id"] != result["verifier_id"]
            or envelope["worker_id"] != result["worker_id"]
        ):
            raise ValueError("nested signer and worker bindings differ")
        o = envelope["observation"]
        growth_model.closed(
            o,
            "study_id evidence_mode action_id receiver context_sha256 protocol evaluator "
            "artifact_version parents external_inputs status measured_service",
        )
        trial = engine._trial(run, result["trial_id"])
        if trial.get("growth_envelope_digest"):
            if trial["growth_envelope_digest"] != sha256_json(envelope):
                raise ValueError("conflicting growth result delivery")
            return engine.response(
                idempotent=True, trial_id=trial["trial_id"], reward=trial["reward"]
            )
        a = g["actions"][trial["growth_action"]]
        receiver = g["receivers"][a["receiver"]]
        expected = {
            "study_id": g["study_id"],
            "evidence_mode": g["evidence_mode"],
            "action_id": trial["growth_action"],
            "receiver": a["receiver"],
            "context_sha256": receiver["context_sha256"],
            "protocol": receiver["protocol"],
            "evaluator": receiver["evaluator"],
        }
        if any(o[k] != v for k, v in expected.items()):
            raise ValueError("growth observation scope mismatch")
        if (
            o["status"] not in {"success", "failed", "timeout", "inconclusive"}
            or (o["status"] == "success") != result["accepted"]
        ):
            raise ValueError("outcome status must match signed acceptance")
        growth_model.integers(result["actual_resources"], g["units"]["costs"])
        growth_model.integers(o["measured_service"], g["verifier_stages"])
        if any(
            o["measured_service"][k] > a["service_measurement"][k] for k in o["measured_service"]
        ):
            raise ValueError("service measurement outside registered bound")
        asset = a["produces"]
        parents = g["assets"][asset]["parents"] if asset else a["requires"]
        if o["parents"] != parents:
            raise ValueError("lineage coalition mismatch")
        if asset:
            spec = g["assets"][asset]
            if (
                result.get("artifact_sha256") != asset
                or o["artifact_version"] != spec["version"]
                or o["external_inputs"] != spec["external_inputs"]
            ):
                raise ValueError("immutable asset/source binding mismatch")
        else:
            growth_model.text(o["artifact_version"])
            growth_model.unique(o["external_inputs"])
        ledger = growth_ledger.replay(run, current, group=trial["group"])
        reasons = growth_ledger.prerequisites(g, a, ledger)
        # Existing signature, fencing, packet eligibility and residual logic is authoritative.
        admitted = engine._ingest_result(store, run, current, result)
        # Keep the new exact wire values after legacy eligibility validation.
        trial["actual_resources"] = dict(result["actual_resources"])
        trial["legacy_artifact_credit_blockers"] = list(admitted.get("blockers", []))
        reasons.extend(r for r in admitted.get("blockers", []) if r != "duplicate_outcome")
        if timestamp(result["observed_at"]) > timestamp(g["window_end"]) or timestamp(
            current
        ) > timestamp(g["window_end"]):
            reasons.append("late_observation")
        if asset and timestamp(g["assets"][asset]["expires_at"]) <= timestamp(current):
            reasons.append("expired_asset")
        qualified = not reasons
        growth_ledger.append(
            run,
            "outcome",
            {
                "group": trial["group"],
                "trial_id": trial["trial_id"],
                "action_id": trial["growth_action"],
                "artifact_sha256": result.get("artifact_sha256"),
                "artifact_version": o["artifact_version"],
                "measured_service": o["measured_service"],
                "parents": parents,
                "external_inputs": o["external_inputs"],
                "observed_at": result["observed_at"],
                "costs": result["actual_resources"],
                "status": o["status"],
                "qualified": qualified,
                "success": result["accepted"] and qualified,
                "reasons": sorted(set(reasons)),
                "service_identity": growth_planner.service_identity(run, a, trial["group"]),
                "acceptance_evidence": sha256_json(envelope),
                "envelope": envelope,
            },
            current,
        )
        # The future steps provably have no task, lease or dispatch. Release only those.
        growth_ledger.append(
            run, "release_unstarted", {"reservation": run["growth_reservation"]}, current
        )
        run["growth_reservation"] = None
        trial["growth_envelope_digest"] = sha256_json(envelope)
        trial["reward"] = int(
            qualified
            and result["accepted"]
            and a["kind"] in {"service", "reuse"}
            and growth_planner.service_key(run, a, trial["group"]) not in ledger["service_events"]
        )
        trial["growth_blockers"] = sorted(set(reasons))
        trial["blockers"] = sorted(set(reasons))
        return engine.response(
            trial_id=trial["trial_id"],
            reward=trial["reward"],
            blockers=reasons,
            mutated_runtime=True,
        )


def freeze(run: dict[str, Any], current: str) -> dict[str, Any]:
    ledger = growth_ledger.replay(run, current)
    if not ledger["compatible_scenarios"]:
        raise ValueError("cannot freeze inconsistent forecast models")
    policy = {
        "compatible_scenarios": ledger["compatible_scenarios"],
        "training_revision": run["revision"],
        "journal_digest": ledger["journal_digest"],
        "frozen_at": current,
    }
    return policy


def lifecycle(store: ControlStore, run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Signed invalidation preserves history and cannot silently re-admit evidence."""
    from ccr.optimizer import engine

    growth_model.closed(
        event,
        "event_id run_id config_digest asset state reason observed_at verifier_id "
        "worker_id signature_base64",
    )
    if event["state"] not in {"withdrawn", "quarantined", "expired", "corrected"}:
        raise ValueError("revalidation requires a new independently checked trial")
    with engine.edit_run(store, run_id) as (run, current):
        engine._verify(run["config"], event)
        if event["run_id"] != run_id or event["config_digest"] != run["config"]["config_digest"]:
            raise ValueError("lifecycle scope mismatch")
        if event["asset"] not in run["config"]["growth"]["assets"]:
            raise ValueError("unknown lifecycle asset")
        if (
            not timestamp(run["created_at"])
            <= timestamp(event["observed_at"])
            <= timestamp(current)
        ):
            raise ValueError("lifecycle observation time invalid")
        growth_model.text(event["event_id"])
        growth_model.text(event["reason"])
        for row in run["growth_events"]:
            if row["kind"] == "lifecycle" and row["payload"]["event_id"] == event["event_id"]:
                if row["payload"] != event:
                    raise ValueError("conflicting lifecycle event")
                return engine.response(idempotent=True)
        growth_ledger.append(run, "lifecycle", event, current)
        run["revision"] += 1
        return engine.response(
            mutated_runtime=True,
            repair_hints=[
                {
                    "asset": event["asset"],
                    "reason": event["reason"],
                    "requires": "new registered validation evidence",
                }
            ],
        )


def verifier_pressure(run: dict[str, Any], current: str) -> dict[str, Any]:
    """Separate registered queue demand from authenticated completion and rates."""
    g = run["config"]["growth"]
    arrivals = []
    for trial in run["trials"]:
        action = g["actions"][trial["growth_action"]]
        arrivals.append(
            {
                "trial_id": trial["trial_id"],
                "group": trial["group"],
                "arrived_at": trial["created_at"],
                "deadline": run["config"]["deadline"],
                "age_seconds": max(
                    0, int((timestamp(current) - timestamp(trial["created_at"])).total_seconds())
                ),
                "registered_work": action["verification_work"],
                "state": trial["state"],
                "completion_authenticated": bool(trial["result_digest"]),
                "measured_completed_work": None,
            }
        )
    return {
        "stages": g["verifier_stages"],
        "arrivals": arrivals,
        "unfinished_trials": [a["trial_id"] for a in arrivals if not a["completion_authenticated"]],
        "repair_obligations": run["residuals"],
        "funded_continuation": run["growth_reservation"],
        "observed_joint_capacity": None,
        "work_semantics": "Registered demand is not measured completion; rates are stage-scoped.",
    }


def report(store: ControlStore, run: dict[str, Any]) -> dict[str, Any]:
    from ccr.optimizer.engine import accounting, response

    current = store.now()
    ledgers = {
        g: growth_ledger.replay(run, current, group=g)
        for g in ("training", "candidate", "baseline")
    }
    return response(
        schema_version=growth_model.REPORT,
        run_id=run["run_id"],
        state=run["state"],
        revision=run["revision"],
        config_digest=run["config"]["config_digest"],
        frozen_policy=run["frozen_policy"],
        ledgers=ledgers,
        trials=run["trials"],
        accounts={g: accounting(run, g) for g in ledgers},
        next_action=growth_planner.plan(run, current),
        restricted_alternative=growth_planner.plan(run, current, restricted=True),
        server_time=current,
        improvement_claim_admissible=False,
        evaluation_complete=bool(run["frozen_policy"])
        and all(
            ledgers[arm]["observed_service"][k] >= run["config"]["growth"]["targets"][k]
            for arm in ("candidate", "baseline")
            for k in ("task", "research")
        ),
        observed_comparison={
            k: ledgers["candidate"]["observed_service"][k]
            - ledgers["baseline"]["observed_service"][k]
            for k in ("task", "research")
        },
        comparison_kind="descriptive_or_model_conditional_only",
        blockers=run["blockers"],
        residuals=run["residuals"],
        evidence_mode=run["config"]["growth"]["evidence_mode"],
        verifier_pressure=verifier_pressure(run, current),
        assumptions=[
            "Registered finite joint scenarios; no iid reuse inference.",
            "Externally assigned disjoint quotas remain reserved across restarts.",
            "Signatures authenticate evaluator records, not external truth or independent errors.",
        ],
    )
