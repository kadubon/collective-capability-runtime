# SPDX-License-Identifier: Apache-2.0
"""Finite synthetic native loop; isolated state and ephemeral evaluation keys."""

from __future__ import annotations

import base64
import copy
import importlib
import json
import tempfile
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer import (
    engine,
    growth_checker,
    native_accounting,
    native_checks,
    native_projection,
    native_runtime,
)
from ccr.optimizer.growth_example import fixture, observation, sign
from ccr.optimizer.growth_runtime import lifecycle
from ccr.storage.control import ControlStore


def source_fixture(producer: str) -> bytes:
    if producer not in native_checks.PACKAGES:
        raise ValueError("unsupported native fixture")
    relative = "examples/native_interchange/" + producer + ".json"
    path = Path(__file__).resolve().parents[3] / relative
    return (
        path.read_bytes()
        if path.is_file()
        else resources.files("ccr.data").joinpath(relative).read_bytes()
    )


def alt_profile(raw: dict[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    native_raw = source_fixture("alt")
    inspected = native_checks.inspect(native_raw)
    c = inspected["documents"]["contract"]
    selected = inspected["documents"]["plan"]["selected"]
    g = raw["growth"]
    original_asset = next(iter(g["assets"]))
    candidate = c["qualifications"][0]["offer"]["candidate"]
    spec = g["assets"].pop(original_asset)
    spec.update(receivers=["A", "B"], source_mission=c["scope"])
    g["assets"][candidate] = spec
    for action in g["actions"].values():
        action["requires"] = [candidate if v == original_asset else v for v in action["requires"]]
        if action["produces"] == original_asset:
            action["produces"] = candidate
    for receiver in ("A", "B"):
        offer = next(q["offer"] for q in c["qualifications"] if q["offer"]["receiver"] == receiver)
        g["receivers"][receiver] = {
            "mission_id": offer["mission"],
            "context_sha256": sha256_json(offer["context"]),
            "domain": offer["task_family"],
            "protocol": offer["protocol"],
            "evaluator": offer["evaluator"],
            "quality": offer["quality"],
            "cross_mission_allowed": True,
        }
    g["verifier_stages"]["review"]["domains"].append("typed-identity")
    names = {
        "prepare": "form",
        "adapt-B": "transfer",
        "reuse-0": "reuse",
        "reuse-1": "reuse_again",
        "reuse-2": "third",
        "reuse-3": "fourth",
    }
    for source_id in selected:
        name = names[source_id]
        option = next(o for o in c["options"] if o["id"] == source_id)
        if name not in g["actions"]:
            g["actions"][name] = copy.deepcopy(g["actions"]["reuse"])
            g["actions"][name].update(intervention_id=name, target_id="target:" + name)
            arm = copy.deepcopy(
                next(a for a in raw["base"]["interventions"] if a["intervention_id"] == "reuse")
            )
            arm["intervention_id"] = name
            raw["base"]["interventions"].append(arm)
            target = copy.deepcopy(raw["base"]["task_manifest"][0])
            target["target_id"] = "target:" + name
            raw["base"]["task_manifest"].append(target)
            for scenario in g["scenarios"].values():
                scenario[name] = True
        action = g["actions"][name]
        action["receiver"] = "B" if name in {"transfer", "reuse_again", "fourth"} else "A"
        if option["offer"]:
            offer = next(q["offer"] for q in c["qualifications"] if q["id"] == option["offer"])
            target = next(
                t for t in raw["base"]["task_manifest"] if t["target_id"] == action["target_id"]
            )
            target["input_sha256"] = offer["inputs"][0]
            action["gains"] = {"task": 1, "research": 1}
        arm = next(a for a in raw["base"]["interventions"] if a["intervention_id"] == name)
        arm["resource_upper_bound"]["cost"] = max(
            1, sum(int(x["amount"]) for x in c["costs"] if x["id"] in option["costs"])
        )
    raw["base"]["resource_limits"]["cost"] = 140
    g["quota"]["pool_budget"]["cost"] = g["quota"]["budget"]["cost"] = 140
    g["bundles"]["delayed"] = ["form", "transfer", "reuse", "reuse_again", "third", "fourth"]
    return raw, native_raw, names


def vek_single_work() -> bytes:
    """Explicitly construct and check a changed one-work serial native problem."""
    original = json.loads(source_fixture("vek"))
    docs = {k: json.loads(v) for k, v in original["documents"].items()}
    contract = docs["contract"]
    contract["slot_seconds"] = "2"
    first = next(iter(docs["plan"]["schedule"]))
    model = importlib.import_module("verification_ecology_kit.capacity.model")
    reducer = importlib.import_module("verification_ecology_kit.capacity.reducer")
    checker = importlib.import_module("verification_ecology_kit.capacity.checker")
    reports = importlib.import_module("verification_ecology_kit.capacity.report")
    parsed = model.Contract.from_dict(contract)
    snapshot = reducer.replay(parsed, docs["history"]["events"])
    docs["plan"]["contract_digest"] = parsed.contract_digest
    docs["plan"]["schedule"] = {first: 0}
    docs["plan"]["checked"] = checker.check_schedule(parsed, snapshot, {first: 0}).to_dict()
    docs["report"] = reports.capacity_report(parsed, snapshot, docs["plan"])
    original["documents"] = {k: json.dumps(v, sort_keys=True) for k, v in docs.items()}
    raw = json.dumps(original, sort_keys=True).encode()
    native_checks.check(raw)
    return raw


def run_example() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ccr-native-synthetic-") as temporary:
        return _run(Path(temporary))


def _run(root: Path) -> dict[str, Any]:
    ed = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = importlib.import_module("cryptography.hazmat.primitives.serialization")
    key = ed.Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    raw, alt, alt_names = alt_profile(fixture(public))
    g = raw["growth"]
    asset = next(iter(g["assets"]))
    g["assets"][asset]["expires_at"] = (
        (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0).isoformat()
    )
    sources = {"alt": alt, "vek": vek_single_work(), "cpcf": source_fixture("cpcf")}
    inspected = {p: native_checks.check(value) for p, value in sources.items()}
    vek_documents = inspected["vek"]["documents"]
    vek_action = next(iter(vek_documents["plan"]["schedule"]))
    work_id = next(
        a["work_id"] for a in vek_documents["contract"]["actions"] if a["action_id"] == vek_action
    )
    work = next(w for w in vek_documents["contract"]["work"] if w["work_id"] == work_id)
    for name, kind in (
        ("probe", "diagnostic"),
        ("verification", "diagnostic"),
        ("review", "repair"),
    ):
        action = copy.deepcopy(g["actions"]["greedy"])
        action.update(
            kind=kind,
            intervention_id=name,
            target_id="target:" + name,
            gains={"task": 0, "research": 0},
        )
        g["actions"][name] = action
        arm = copy.deepcopy(raw["base"]["interventions"][0])
        arm.update(
            intervention_id=name,
            kind="measurement" if kind == "diagnostic" else "residual_repair",
            resource_upper_bound={"cost": 3},
        )
        raw["base"]["interventions"].append(arm)
        target = copy.deepcopy(raw["base"]["task_manifest"][0])
        target.update(
            target_id="target:" + name,
            input_sha256=work["input_digest"] if name == "verification" else sha256_json(name),
        )
        raw["base"]["task_manifest"].append(target)
        for scenario in g["scenarios"].values():
            scenario[name] = None
    for action in g["actions"].values():
        action["capacity"] = {"reviewer": 1}
    g["quota"]["capacity"] = g["quota"]["pool_capacity"] = {"reviewer": 1}
    g["bundles"]["delayed"] = ["probe", "verification", *g["bundles"]["delayed"]]
    g["bundles"]["review"] = ["review"]
    g["actions"]["greedy"]["verification_work"]["review"] = 100
    g["horizon_seconds"] = 60
    raw["base"]["resource_limits"]["cost"] = 200
    g["quota"]["budget"]["cost"] = g["quota"]["pool_budget"]["cost"] = 200
    store = ControlStore(root, "")
    run_id = engine.initialize(store, mission="mission:synthetic-native-loop", config=raw)["run_id"]
    run = engine.load(store, run_id)
    bindings = {}
    specifications = [("alt", source, name) for source, name in alt_names.items()]
    specifications += [
        ("vek", vek_action, "verification"),
        ("cpcf", "prepare", "probe"),
        ("cait", "accounting-review", "review"),
    ]
    for producer, source_action, name in specifications:
        bindings[name] = {
            "producer": producer,
            "contract_sha256": run["config"]["config_digest"]
            if producer == "cait"
            else inspected[producer]["document_sha256"]["contract"],
            "source_action": source_action,
            "action_sha256": sha256_json(g["actions"][name]),
            "valid_from": "2020-01-01T00:00:00Z",
            "valid_until": g["window_end"],
        }
    bindings["probe"]["observations"] = {"success": "red", "failed": "blue"}
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": g["study_id"],
        "arm": "training",
        "pool_id": g["quota"]["pool_id"],
        "bindings": bindings,
        "pools": {"verifier": "reviewer"},
        "units": {
            unit: {"target": "cost", "rate": "1", "rounding": "exact"}
            for unit in ("resource", "check-work", "credits")
        },
    }
    native_runtime.register(store, run_id, registration, expected_revision=0)
    before = engine.plan(store, run_id)
    assert before["chosen"] is None
    receipts = []
    for producer, source in sources.items():
        projected = native_projection.project(source, registration)
        revision = engine.load(store, run_id)["revision"]
        staged = native_runtime.stage(
            store, run_id, source, projected, expected_revision=revision, idempotency_key=producer
        )
        receipts.append(
            native_runtime.admit(
                store, run_id, staged["proposal_id"], expected_revision=revision + 1
            )
        )
    trace = []
    for expected in g["bundles"]["delayed"]:
        plan = engine.plan(store, run_id)
        assert plan["chosen"]["immediate_step"] == expected
        assert growth_checker.check(engine.load(store, run_id), plan, store.now())["ok"]
        trial = engine.step(store, run_id, apply=True, expected_revision=plan["revision"])["trial"]
        assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
        result = engine.ingest(
            store,
            run_id,
            observation(store, run_id, trial["trial_id"], key, success=expected != "verification"),
        )
        trace.append(
            {"action": expected, "trial_id": trial["trial_id"], "reward": result["reward"]}
        )
    first = engine.report(store, run_id)["ledgers"]["training"]
    run = engine.load(store, run_id)
    lifecycle(
        store,
        run_id,
        sign(
            key,
            {
                "event_id": "native-example-withdrawal",
                "run_id": run_id,
                "config_digest": run["config"]["config_digest"],
                "asset": asset,
                "state": "withdrawn",
                "reason": "synthetic source loss",
                "observed_at": store.now(),
                "verifier_id": "reviewer",
                "worker_id": "producer",
            },
        ),
    )
    assert engine.plan(store, run_id)["chosen"] is None
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    feedback = native_accounting.reconcile(
        store, run_id, exported, report, expected_revision=run["revision"]
    )
    assert native_accounting.reconcile(
        store, run_id, exported, report, expected_revision=run["revision"]
    )["idempotent"]
    second = engine.plan(store, run_id)
    assert second["chosen"]["immediate_step"] == "review"
    after = engine.report(store, run_id)["ledgers"]["training"]
    assert first["observed_service"] == after["observed_service"] == {"task": 4, "research": 4}
    assert first["actual_costs"] == after["actual_costs"]
    assert first["asset_count"] == after["asset_count"] == 1
    return {
        "ok": True,
        "evidence_mode": "synthetic",
        "operationally_observed": False,
        "before_admission": before["blockers"],
        "admissions": receipts,
        "trace": trace,
        "first_cycle": first,
        "feedback": feedback,
        "second_cycle_next_action": "review",
        "after_reconciliation": after,
        "continuation_guarantee_transferred": False,
        "causal_attribution": None,
        "public_acceleration_claim": None,
    }
