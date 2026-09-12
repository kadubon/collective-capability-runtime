# SPDX-License-Identifier: Apache-2.0
"""Offline synthetic integration with ephemeral keys; never contacts providers."""

from __future__ import annotations

import base64
import copy
import importlib
import json
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from ccr.ids import canonical_bytes, sha256_json
from ccr.optimizer import engine, growth_checker, growth_model
from ccr.storage.control import ControlStore
from ccr.storage.local_store import SQLiteRuntimeStore

WORKFLOW: dict[str, Any] = {"operation": "double", "domain": [0, 1, 2, 3]}


def fixture(public_key: str, *, study: str = "synthetic:delayed") -> dict[str, Any]:
    asset = sha256_json(WORKFLOW)
    actions: dict[str, Any] = {}
    specs = [
        ("form", "formation", "source", [], asset, 0),
        ("transfer", "transfer_validation", "receiver", [asset], None, 0),
        ("reuse", "reuse", "receiver", [asset], None, 2),
        ("reuse_again", "reuse", "receiver", [asset], None, 2),
        ("greedy", "service", "source", [], None, 1),
    ]
    for name, kind, receiver, requires, produces, gain in specs:
        actions[name] = {
            "kind": kind,
            "intervention_id": name,
            "target_id": "target:" + name,
            "receiver": receiver,
            "requires": requires,
            "produces": produces,
            "gains": {"task": gain, "research": gain},
            "duration_seconds": 2,
            "cleanup_seconds": 1,
            "cleanup_cost": {"cost": 1},
            "capacity": {"worker": 1},
            "service_measurement": {"review": 0},
            "verification_work": {"review": 1},
            "authority": "local_only",
            "evidence_refs": ["synthetic:finite-model"],
        }
    holdout = []
    for name in ("form", "transfer", "reuse", "reuse_again", "greedy"):
        action = copy.deepcopy(actions[name])
        action["target_id"] = "target:holdout_" + name
        action["intervention_id"] = "holdout_" + name
        actions["holdout_" + name] = action
        holdout.append(action["target_id"])
    base = {
        "schema_version": "ccr.optimizer_config.v1",
        "policy_version": 1,
        "seed": 17,
        "deadline": "2099-01-01T00:00:00Z",
        "epsilon": 0.2,
        "diagnostic_reserve": 0.2,
        "resource_limits": {"cost": 100},
        "effort_resource": "cost",
        "max_inflight": 1,
        "trusted_verifiers": {"reviewer": public_key},
        "task_manifest": [
            {
                "target_id": a["target_id"],
                "input_ref": "synthetic:" + n,
                "input_sha256": sha256_json(n),
                "acceptance_criteria": (
                    "Check finite synthetic input and receiver contract; no empirical claim."
                ),
            }
            for n, a in actions.items()
        ],
        "interventions": [
            {
                "intervention_id": n,
                "kind": growth_model.MAPPING[a["kind"]],
                "resource_upper_bound": {"cost": 1},
                "producer_ids": ["producer"],
            }
            for n, a in actions.items()
        ],
        "evaluation": {
            "holdout_tasks": holdout,
            "horizon": len(holdout),
            "alpha": 0.05,
            "resource_envelope": {"cost": 40},
            "baseline_intervention": "greedy",
        },
    }
    receivers = {
        name: {
            "mission_id": "mission:" + name,
            "context_sha256": sha256_json(name),
            "domain": "finite_software",
            "protocol": "synthetic-service-1",
            "evaluator": "arithmetic-oracle-1",
            "quality": "exact",
            "cross_mission_allowed": True,
        }
        for name in ("source", "receiver")
    }
    bundles = {
        "delayed": ["form", "transfer", "reuse", "reuse_again"],
        "simple": ["greedy"],
        "holdout_delayed": [
            "holdout_form",
            "holdout_transfer",
            "holdout_reuse",
            "holdout_reuse_again",
        ],
        "holdout_simple": ["holdout_greedy"],
    }
    return {
        "schema_version": growth_model.PROFILE,
        "policy": "verified_growth_v1",
        "base": base,
        "growth": {
            "study_id": study,
            "checkpoint_digest": sha256_json({"packets": [], "residuals": []}),
            "evidence_mode": "synthetic",
            "targets": {"task": 4, "research": 4},
            "units": {
                "task": "registered_service",
                "research": "registered_service",
                "costs": {"cost": "effort_unit"},
            },
            "horizon_seconds": 30,
            "max_steps": 8,
            "candidate_limit": 128,
            "attribution_seconds": 3600,
            "window_end": "2099-01-01T00:00:00Z",
            "receivers": receivers,
            "assets": {
                asset: {
                    "version": "1",
                    "source_mission": "mission:source",
                    "receivers": list(receivers),
                    "parents": [],
                    "external_inputs": ["synthetic:hand-authored-model"],
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            },
            "actions": actions,
            "bundles": bundles,
            "scenarios": {"finite": dict.fromkeys(actions, True)},
            "verifier_stages": {
                "review": {
                    "domains": ["finite_software"],
                    "quality": "exact",
                    "service_units_per_second": 1,
                    "fresh_until": "2099-01-01T00:00:00Z",
                    "independence_groups": ["synthetic-reviewer"],
                    "exposure_groups": ["shared-fixture"],
                    "dependence": "shared",
                }
            },
            "quota": {
                "pool_id": "pool:" + study,
                "pool_budget": {"cost": 100},
                "pool_capacity": {"worker": 1},
                "budget": {"cost": 100},
                "capacity": {"worker": 1},
                "allocation_ref": "synthetic:dedicated-budget",
            },
            "cost_order": ["cost"],
            "diagnostic_budget": {"cost": 2},
            "comparison": {
                "restricted_bundles": list(bundles),
                "independent_unit": "whole_synthetic_study",
                "uncertainty_method": "unresolved",
            },
        },
    }


def sign(key: Any, value: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in value.items() if k != "signature_base64"}
    return {
        **payload,
        "signature_base64": base64.b64encode(key.sign(canonical_bytes(payload))).decode(),
    }


def observation(
    store: ControlStore, run_id: str, trial_id: str, key: Any, *, success: bool = True
) -> dict[str, Any]:
    run = engine.load(store, run_id)
    g = run["config"]["growth"]
    trial = engine._trial(run, trial_id)
    action = g["actions"][trial["growth_action"]]
    receiver = g["receivers"][action["receiver"]]
    asset = action["produces"]
    fixture_path = Path(__file__).resolve().parents[3] / "examples/verified_growth/packet.json"
    packet = json.loads(
        fixture_path.read_text(encoding="utf-8")
        if fixture_path.is_file()
        else resources.files("ccr.data")
        .joinpath("examples/verified_growth/packet.json")
        .read_text(encoding="utf-8")
    )
    artifact = asset or (
        action["requires"][0] if action["requires"] else sha256_json(trial["target_id"])
    )
    packet["artifacts"][0]["content_sha256"] = artifact
    packet["issuer"]["actor_id"] = "producer"
    packet["packet_id"] = "packet:" + artifact[:16]
    result = sign(
        key,
        {
            "schema_version": "ccr.optimizer_result.v1",
            **{
                k: trial[k]
                for k in (
                    "run_id",
                    "trial_id",
                    "target_id",
                    "config_digest",
                    "input_digest",
                    "worker_id",
                    "fencing_token",
                )
            },
            "observed_at": store.now(),
            "verifier_id": "reviewer",
            "actual_resources": {"cost": 2},
            "accepted": success,
            "residuals": [],
            "packet": packet,
            "artifact_sha256": artifact,
        },
    )
    o = {
        "study_id": g["study_id"],
        "evidence_mode": "synthetic",
        "action_id": trial["growth_action"],
        "receiver": action["receiver"],
        "context_sha256": receiver["context_sha256"],
        "protocol": receiver["protocol"],
        "evaluator": receiver["evaluator"],
        "artifact_version": g["assets"][asset]["version"] if asset else "1",
        "parents": g["assets"][asset]["parents"] if asset else action["requires"],
        "external_inputs": g["assets"][asset]["external_inputs"]
        if asset
        else ["synthetic:fixture"],
        "status": "success" if success else "failed",
        "measured_service": dict(action["service_measurement"]),
    }
    return sign(
        key,
        {
            "schema_version": growth_model.RESULT,
            "result": result,
            "observation": o,
            "verifier_id": "reviewer",
            "worker_id": trial["worker_id"],
        },
    )


def run_example(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        with tempfile.TemporaryDirectory(prefix="ccr-growth-synthetic-") as directory:
            return run_example(Path(directory))
    ed = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = importlib.import_module("cryptography.hazmat.primitives.serialization")
    key = ed.Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    store = ControlStore(root, "")
    run_id = engine.initialize(store, mission="mission:source", config=fixture(public))["run_id"]
    worker = SQLiteRuntimeStore(root)
    worker.initialize()
    trace = []
    for _ in range(4):
        proposal = engine.plan(store, run_id)
        assert growth_checker.check(engine.load(store, run_id), proposal, store.now())["ok"]
        trial = engine.step(store, run_id, apply=True, expected_revision=proposal["revision"])[
            "trial"
        ]
        claim = worker.claim_task(role=trial["task"]["role"], worker_id="producer", ttl_minutes=30)
        assert claim is not None
        candidate = perform_synthetic(root, trial["growth_action"])
        worker.complete(
            task_id=claim["task_id"],
            worker_id="producer",
            fencing_token=claim["fencing_token"],
            idempotency_key=trial["trial_id"],
            result=candidate,
        )
        result = engine.ingest(store, run_id, observation(store, run_id, trial["trial_id"], key))
        trace.append({"action": trial["growth_action"], "reward": result["reward"]})
    engine.freeze(store, run_id)
    for _ in range(8):
        trial = engine.step(store, run_id, apply=True)["trial"]
        engine.claim(store, run_id, trial["trial_id"], worker="producer")
        candidate = perform_synthetic(root, trial["growth_action"])
        engine.task_transition(
            store,
            run_id,
            trial["trial_id"],
            worker="producer",
            token=1,
            result=candidate,
            idempotency_key=trial["trial_id"],
        )
        engine.ingest(store, run_id, observation(store, run_id, trial["trial_id"], key))
    report = engine.report(store, run_id)
    assert report["ledgers"]["training"]["observed_service"] == {"task": 4, "research": 4}
    assert report["ledgers"]["training"]["asset_count"] == 1
    assert report["evaluation_complete"]
    return {
        "ok": True,
        "evidence_mode": "synthetic",
        "trace": trace,
        "ledger": report["ledgers"]["training"],
        "frozen_policy": report["frozen_policy"],
        "comparison": report["observed_comparison"],
        "evaluation_complete": report["evaluation_complete"],
        "reference_policies": reference_policies(root / "references", public, key),
        "verification_and_cost_scenarios": boundary_scenarios(root / "boundaries", public, key),
        "improvement_claim_admissible": False,
        "external_execution": False,
        "network_call_performed": False,
    }


def boundary_scenarios(root: Path, public: str, key: Any) -> dict[str, Any]:
    """Execute supported verifier investment and an adverse formation-cost control."""
    investment = fixture(public, study="synthetic:verification")
    g = investment["growth"]
    g["actions"]["form"]["kind"] = "verification_investment"
    g["actions"]["form"]["service_measurement"]["review"] = 2
    investment["base"]["interventions"][0]["kind"] = "measurement"
    for name in ("reuse", "reuse_again"):
        g["actions"][name]["verification_work"]["review"] = 4
    negative = fixture(public, study="synthetic:cost-dominates")
    negative["base"]["interventions"][0]["resource_upper_bound"]["cost"] = 19
    results = {}
    for name, raw, steps in (
        ("verifier_investment", investment, 4),
        ("cost_dominates", negative, 1),
    ):
        store = ControlStore(root / name, "")
        run_id = engine.initialize(store, mission="mission:source", config=raw)["run_id"]
        trace = []
        for _ in range(steps):
            plan = engine.plan(store, run_id)
            assert growth_checker.check(engine.load(store, run_id), plan, store.now())["ok"]
            trial = engine.step(store, run_id, apply=True)["trial"]
            trace.append(trial["growth_action"])
            engine.claim(store, run_id, trial["trial_id"], worker="producer")
            engine.ingest(store, run_id, observation(store, run_id, trial["trial_id"], key))
        report = engine.report(store, run_id)
        results[name] = {
            "actions": trace,
            "ledger": report["ledgers"]["training"],
            "verifier_pressure": report["verifier_pressure"],
        }
    assert results["verifier_investment"]["ledger"]["observed_service"]["task"] == 4
    assert results["cost_dominates"]["actions"] == ["greedy"]
    return results


def reference_policies(root: Path, public: str, key: Any) -> dict[str, Any]:
    """Run finite references through real signed trials, without an empirical verdict."""
    raw = fixture(public, study="synthetic:references")
    g = raw["growth"]
    # The immediate-output restriction is an ablation, never the strong comparator.
    greedy = copy.deepcopy(raw)
    greedy["growth"]["bundles"] = {"simple": ["greedy"]}
    greedy["growth"]["comparison"]["restricted_bundles"] = ["simple"]
    immediate_store = ControlStore(root / "immediate", "")
    immediate_id = engine.initialize(immediate_store, mission="mission:source", config=greedy)[
        "run_id"
    ]
    trial = engine.step(immediate_store, immediate_id, apply=True)["trial"]
    engine.claim(immediate_store, immediate_id, trial["trial_id"], worker="producer")
    engine.ingest(
        immediate_store,
        immediate_id,
        observation(immediate_store, immediate_id, trial["trial_id"], key),
    )
    immediate = engine.report(immediate_store, immediate_id)["ledgers"]["training"]

    # Unmodified v1 policy: same tasks, evaluator, horizon and all-in effort bounds.
    legacy_config = copy.deepcopy(raw["base"])
    for arm in legacy_config["interventions"]:
        arm["resource_upper_bound"]["cost"] = 2
    legacy_store = ControlStore(root / "legacy", "")
    legacy_id = engine.initialize(legacy_store, mission="mission:source", config=legacy_config)[
        "run_id"
    ]
    assets: set[str] = set()
    qualified: set[str] = set()
    gains = {"task": 0, "research": 0}
    trace = []
    for _ in range(g["max_steps"]):
        plan = engine.plan(legacy_store, legacy_id)
        if not plan["selected"]:
            break
        trial = engine.step(legacy_store, legacy_id, apply=True)["trial"]
        engine.claim(legacy_store, legacy_id, trial["trial_id"], worker="producer")
        actual = engine._trial(engine.load(legacy_store, legacy_id), trial["trial_id"])
        action = next(a for a in g["actions"].values() if a["target_id"] == trial["target_id"])
        success = trial["kind"] == growth_model.MAPPING[action["kind"]]
        success = success and set(action["requires"]) <= assets
        if action["kind"] != "transfer_validation":
            success = success and all(
                f"{a}:{action['receiver']}" in qualified for a in action["requires"]
            )
        packet_path = Path(__file__).resolve().parents[3] / "examples/verified_growth/packet.json"
        packet = json.loads(
            packet_path.read_text()
            if packet_path.exists()
            else resources.files("ccr.data")
            .joinpath("examples/verified_growth/packet.json")
            .read_text()
        )
        artifact = action["produces"] or (
            action["requires"][0] if action["requires"] else sha256_json(trial["target_id"])
        )
        packet["artifacts"][0]["content_sha256"] = artifact
        packet["issuer"]["actor_id"] = "producer"
        result = sign(
            key,
            {
                "schema_version": "ccr.optimizer_result.v1",
                **{
                    k: actual[k]
                    for k in (
                        "run_id",
                        "trial_id",
                        "target_id",
                        "config_digest",
                        "input_digest",
                        "worker_id",
                        "fencing_token",
                    )
                },
                "observed_at": legacy_store.now(),
                "verifier_id": "reviewer",
                "actual_resources": {"cost": 2},
                "accepted": success,
                "residuals": [],
                "packet": packet,
                "artifact_sha256": artifact,
            },
        )
        admitted = engine.ingest(legacy_store, legacy_id, result)
        if success:
            if action["produces"]:
                assets.add(artifact)
                qualified.add(f"{artifact}:{action['receiver']}")
            if action["kind"] == "transfer_validation":
                qualified.update(f"{a}:{action['receiver']}" for a in action["requires"])
            for k in gains:
                gains[k] += action["gains"][k]
        trace.append(
            {
                "kind": trial["kind"],
                "target": trial["target_id"],
                "accepted": success,
                "legacy_reward": admitted["reward"],
            }
        )
    legacy = engine.report(legacy_store, legacy_id)
    return {
        "comparison_kind": "finite_synthetic_descriptive",
        "registered_training_budget": {"cost": 20},
        "legacy": {
            "observed_service": gains,
            "cost": legacy["accounts"]["training"]["used"],
            "trace": trace,
        },
        "immediate_output_greedy": {
            "observed_service": immediate["observed_service"],
            "cost": immediate["actual_costs"],
        },
        "new_policy_and_reoptimized_restricted_alternative": (
            "See the executed frozen candidate/baseline comparison; "
            "the permitted reuse route removes the apparent advantage."
        ),
        "legacy_reward_is_a_different_metric": True,
        "improvement_claim_admissible": False,
    }


def perform_synthetic(root: Path, action: str) -> dict[str, Any]:
    """Execute only this fixed software fixture, never imported expressions or code."""
    from ccr.io import write_json_atomic
    from ccr.workcells.protocol import (
        WORKCELL_STAGES,
        advance_workcell,
        create_workcell,
        integrate_workcell,
        submit_workcell,
    )

    if action.endswith("form"):
        name = "synthetic-" + action
        create_workcell(root, template="packet-distillation", name=name)
        metadata = root / "workcells" / name / "workcell.json"
        # Baseline and candidate use isolated workcells even with identical content.
        if json.loads(metadata.read_text())["current_stage"] == "integration":
            name += "-baseline"
            create_workcell(root, template="packet-distillation", name=name)
        path = root / "synthetic-proposal.json"
        write_json_atomic(
            path,
            {
                "claims": [
                    {"claim_text": "Doubling equals repeated addition on the finite domain."}
                ],
                "workflow": WORKFLOW,
                "provenance": {"model": "none", "tool": "finite-python", "source": "synthetic"},
            },
        )
        submit_workcell(root, workcell=name, file=path)
        for stage in WORKCELL_STAGES[1:-1]:
            advance_workcell(root, workcell=name, target_stage=stage)
        result = integrate_workcell(root, workcell=name, strategy="residual-preserving")
        if not result["protocol_complete"] or result["open_residuals_preserved"]:
            raise ValueError("synthetic workcell failed")
        return {
            "workflow": WORKFLOW,
            "artifact_sha256": sha256_json(WORKFLOW),
            "protocol_complete": True,
        }
    outputs = [2 * n for n in WORKFLOW["domain"]]
    # Separate arithmetic evaluator: repeated addition, no generated implementation.
    if outputs != [n + n for n in WORKFLOW["domain"]]:
        raise ValueError("finite receiver oracle failed")
    return {
        "action": "transfer_check" if action.endswith("transfer") else "receiver_service",
        "receiver_outputs": outputs,
        "verified_domain": WORKFLOW["domain"],
    }
