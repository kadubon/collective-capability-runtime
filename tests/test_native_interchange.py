# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from ccr.ids import sha256_json
from ccr.optimizer import engine, native_checks, native_projection, native_runtime
from ccr.optimizer.native_projection_check import check
from ccr.optimizer.native_wire import convert, loads, rational

FIXTURES = Path(__file__).resolve().parents[1] / "examples/native_interchange"
native = pytest.mark.skipif(
    os.getenv("CCR_NATIVE_CONFORMANCE") != "1",
    reason="requires explicitly configured pinned native companion environment",
)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"x":1,"x":2}',
        b'{"x":1.0}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":9007199254740993}',
        b'{"x":"\xff"}',
        b"[]",
        b'{"x":' + b"[" * 25 + b"0" + b"]" * 25 + b"}",
        b'{"x":[' + b"0," * 512 + b"0]}",
        b'{"x":"' + b"a" * 131073 + b'"}',
        b" " * 2_000_001,
    ],
    ids=[
        "duplicate",
        "float",
        "nan",
        "infinity",
        "overflow",
        "encoding",
        "array-root",
        "depth",
        "array-size",
        "string-size",
        "byte-size",
    ],
)
def test_native_lexical_bounds(raw: bytes) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        loads(raw)


@pytest.mark.parametrize("value", [True, 1, 0.5, "1.0", "2/4", "01", "-0", "1/0", "9" * 82])
def test_native_rational_rejections(value: Any) -> None:
    with pytest.raises(ValueError):
        rational(value)


def test_exact_conservative_conversion() -> None:
    assert convert("1/3", "3") == 1
    assert convert("1/3", "2", rounding="upper") == 1
    assert convert("1/3", "2", rounding="lower") == 0
    for args in [("1/3", "2"), ("-1", "1"), ("1", "0"), (str(2**53), "2")]:
        with pytest.raises(ValueError):
            convert(*args)
    assert loads(b'{"escaped":"[\\"{", "x":true}') == {"escaped": '["{', "x": True}


def test_inspection_is_local_read_only(tmp_path: Path, monkeypatch: Any) -> None:
    import socket

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("inspection attempted network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.chdir(tmp_path)
    for producer in native_checks.PACKAGES:
        report = native_checks.inspect((FIXTURES / (producer + ".json")).read_bytes())
        assert report["producer"] == producer
    assert list(tmp_path.iterdir()) == []


@native
@pytest.mark.parametrize("producer", native_checks.PACKAGES)
def test_actual_released_companion_checks(producer: str, monkeypatch: Any) -> None:
    import socket

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("native check attempted network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    raw = (FIXTURES / (producer + ".json")).read_bytes()
    result = native_checks.check(raw)
    assert result["native_checker"]["version"] == native_checks.PACKAGES[producer][1]
    assert result["source_authentication"] == "unestablished"
    assert not result["ccr_admission"] and not result["receiver_eligibility"]
    assert result["service_observation"] is None
    source = json.loads(raw)
    doc_name = "report" if producer in {"cait", "vek"} else "plan"
    doc = json.loads(source["documents"][doc_name])
    if producer == "alt":
        doc["contract_digest"] = "0" * 64
    elif producer == "cpcf":
        doc["spec"]["policy"]["action_id"] = "reuse-beta"
    elif producer == "vek":
        doc["observed_service"] = 100
    else:
        doc["balances"][0]["closing"] = "999"
    source["documents"][doc_name] = json.dumps(doc)
    with pytest.raises(ValueError):
        native_checks.check(json.dumps(source).encode())


@native
def test_native_sidecar_and_semantic_acceptance_are_required(monkeypatch: Any) -> None:
    import importlib

    from ccr.optimizer import native_replan
    from ccr.optimizer.native_example import source_fixture

    original = json.loads(source_fixture("alt"))
    tasks = json.loads(original["documents"]["tasks"])
    for changed in ({"tasks": []}, {**tasks, "invented_authority": True}):
        source = copy.deepcopy(original)
        source["documents"]["tasks"] = json.dumps(changed)
        with pytest.raises(ValueError, match="sidecar"):
            native_checks.check(json.dumps(source).encode())
    with pytest.raises(ValueError, match="CPCF source"):
        native_replan.cpcf({}, source_fixture("alt"))
    with pytest.raises(ValueError, match="unsupported"):
        source_fixture("unregistered")
    facade = importlib.import_module("collective_phase_control_fabric.growth_control")
    # Selected false-acceptance boundary fault: a successful Python call with a
    # negative semantic result must never become a positive native proposal.
    monkeypatch.setattr(facade, "check_epistemic_plan", lambda *_: {"policy_feasible": False})
    with pytest.raises(ValueError, match="not feasible"):
        native_checks.check(source_fixture("cpcf"))


def setup_run(
    tmp_path: Path,
    *,
    continuation: bool = False,
    database_url: str = "",
    valid_until: str | None = None,
    clock: dict[str, Any] | None = None,
    duration: int | None = None,
    extra_verifier: bool = False,
) -> tuple[Any, Any, str, bytes, dict[str, Any]]:
    from tests.test_growth import config, start

    key, raw = config()
    if extra_verifier:
        raw["base"]["trusted_verifiers"]["other-reviewer"] = raw["base"]["trusted_verifiers"][
            "reviewer"
        ]
    if duration is not None:
        raw["growth"]["actions"]["form"]["duration_seconds"] = duration
    raw["base"]["interventions"][0]["resource_upper_bound"]["cost"] = 5
    if continuation:
        next(a for a in raw["base"]["interventions"] if a["intervention_id"] == "reuse")[
            "resource_upper_bound"
        ]["cost"] = 5
    if database_url:
        from ccr.storage.control import ControlStore

        store = ControlStore(tmp_path, database_url)
        run_id = engine.initialize(store, mission=raw["growth"]["study_id"], config=raw)["run_id"]
    else:
        store, run_id = start(tmp_path, raw)
    run = engine.load(store, run_id)
    source = (FIXTURES / "cpcf.json").read_bytes()
    inspected = native_checks.inspect(source)
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": raw["growth"]["study_id"],
        "arm": "training",
        "pool_id": raw["growth"]["quota"]["pool_id"],
        "bindings": {
            "form": {
                "producer": "cpcf",
                "contract_sha256": inspected["document_sha256"]["contract"],
                "source_action": "prepare",
                "action_sha256": sha256_json(raw["growth"]["actions"]["form"]),
                "valid_from": "2020-01-01T00:00:00Z",
                "valid_until": valid_until or raw["growth"]["window_end"],
            }
        },
        "units": {"credits": {"target": "cost", "rate": "1", "rounding": "exact"}},
    }
    if continuation:
        registration["bindings"]["form"]["observations"] = {"success": "red", "failed": "blue"}
        registration["bindings"]["reuse"] = {
            **registration["bindings"]["form"],
            "source_action": "reuse",
            "action_sha256": sha256_json(raw["growth"]["actions"]["reuse"]),
            "observations": {"success": "recorded"},
        }
    registration["clocks"] = {
        inspected["document_sha256"]["contract"]: clock
        or {"utc_origin": store.now(), "tick_origin": "0", "seconds_per_tick": "1"}
    }
    from ccr.optimizer.native_example import cpcf_scope

    for name, binding in registration["bindings"].items():
        binding["scope"] = cpcf_scope(
            run, inspected["documents"], binding["source_action"], name, "reviewer"
        )
    native_runtime.register(store, run_id, registration, expected_revision=0)
    return key, store, run_id, source, registration


@native
def test_cpcf_admission_changes_real_plan_and_signed_result(tmp_path: Path) -> None:
    from ccr.optimizer.growth_example import observation

    key, store, run_id, raw, registration = setup_run(tmp_path)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "greedy"
    projection = native_projection.project(raw, registration)
    forged = copy.deepcopy(projection)
    forged["bindings"][0]["ccr_action"] = "greedy"
    with pytest.raises(ValueError, match="substitution"):
        check(engine.load(store, run_id), raw, forged)
    staged = native_runtime.stage(
        store, run_id, raw, projection, expected_revision=1, idempotency_key="first"
    )
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "greedy"
    assert native_runtime.stage(
        store, run_id, raw, projection, expected_revision=1, idempotency_key="duplicate"
    )["idempotent"]
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "form"
    assert engine.report(store, run_id)["ledgers"]["training"]["asset_count"] == 0
    trial = engine.step(store, run_id, apply=True, expected_revision=3)["trial"]
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    assert engine.ingest(store, run_id, observation(store, run_id, trial["trial_id"], key))["ok"]
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "transfer"
    assert engine.report(store, run_id)["ledgers"]["training"]["asset_count"] == 1
    from ccr.optimizer.native_history import cpcf_history

    with pytest.raises(ValueError, match="no qualified registered observation"):
        cpcf_history(
            engine.load(store, run_id), registration["bindings"]["form"]["contract_sha256"]
        )
    cait = native_projection.project((FIXTURES / "cait.json").read_bytes(), registration)
    assert cait["bindings"] == [] and cait["service_credit"] == 0


@native
def test_native_same_revision_sqlite_staging(tmp_path: Path) -> None:
    _, store, run_id, raw, registration = setup_run(tmp_path)
    projection = native_projection.project(raw, registration)

    def stage(index: int) -> str:
        try:
            return native_runtime.stage(
                store, run_id, raw, projection, expected_revision=1, idempotency_key=str(index)
            )["proposal_id"]
        except ValueError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(stage, range(2)))
    assert len(set(results)) == 1
    run = engine.load(store, run_id)
    assert len(run["native_staged"]) == 1 and run["revision"] == 2


@native
def test_cpcf_replans_only_from_registered_signed_observations(
    tmp_path: Path, native_test_clock: Any
) -> None:
    from datetime import timedelta

    from ccr.optimizer import native_replan
    from ccr.optimizer.model import timestamp
    from tests.test_growth import finish

    key, store, run_id, raw, registration = setup_run(tmp_path, continuation=True)

    def admit(source: bytes, delivery: str) -> None:
        revision = engine.load(store, run_id)["revision"]
        staged = native_runtime.stage(
            store,
            run_id,
            source,
            native_projection.project(source, registration),
            expected_revision=revision,
            idempotency_key=delivery,
        )
        native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=revision + 1)

    admit(raw, "root")
    finish(store, run_id, key)
    run = engine.load(store, run_id)
    with pytest.raises(ValueError, match="visible history"):
        check(run, raw, native_projection.project(raw, registration))
    replanned = native_replan.cpcf(run, raw)
    plan = native_checks.inspect(replanned)["documents"]["plan"]["spec"]
    assert plan["history"] == [
        {
            "action_id": "prepare",
            "observation": "red",
            "entry": False,
            "comparison_history_length": 0,
        }
    ]
    assert plan["policy"]["action_id"] == "reuse"
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "transfer"
    finish(store, run_id, key)
    native_test_clock["now"] = (timestamp(store.now()) + timedelta(seconds=1)).isoformat()
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] != "reuse"
    admit(replanned, "observed")
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "reuse"
    finish(store, run_id, key)
    assert engine.report(store, run_id)["ledgers"]["training"]["observed_service"] == {
        "task": 2,
        "research": 2,
    }


@native
def test_cait_signed_roundtrip_reconciles_and_opens_funded_review(tmp_path: Path) -> None:
    import importlib
    from datetime import datetime, timedelta, timezone

    from ccr.optimizer import native_accounting
    from ccr.optimizer.growth_example import sign
    from ccr.optimizer.growth_runtime import lifecycle
    from tests.test_growth import config, finish, start

    key, raw = config()
    g = raw["growth"]
    asset = next(iter(g["assets"]))
    g["assets"][asset]["expires_at"] = (
        (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0).isoformat()
    )
    action = copy.deepcopy(g["actions"]["greedy"])
    action.update(
        kind="repair",
        intervention_id="review",
        target_id="target:review",
        gains={"task": 0, "research": 0},
    )
    g["actions"]["review"] = action
    g["bundles"]["review"] = ["review"]
    for scenario in g["scenarios"].values():
        scenario["review"] = True
    arm = copy.deepcopy(raw["base"]["interventions"][0])
    arm.update(intervention_id="review", kind="residual_repair")
    raw["base"]["interventions"].append(arm)
    target = copy.deepcopy(raw["base"]["task_manifest"][0])
    target.update(target_id="target:review")
    raw["base"]["task_manifest"].append(target)
    store, run_id = start(tmp_path, raw)
    run = engine.load(store, run_id)
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": g["study_id"],
        "arm": "training",
        "pool_id": g["quota"]["pool_id"],
        "units": {},
        "bindings": {
            "review": {
                "producer": "cait",
                "contract_sha256": run["config"]["config_digest"],
                "source_action": "accounting-review",
                "action_sha256": sha256_json(action),
                "valid_from": "2020-01-01T00:00:00Z",
                "valid_until": g["window_end"],
            }
        },
    }
    native_runtime.register(store, run_id, registration, expected_revision=0)
    for _ in range(4):
        finish(store, run_id, key)
    run = engine.load(store, run_id)
    event = sign(
        key,
        {
            "event_id": "withdraw-native",
            "run_id": run_id,
            "config_digest": run["config"]["config_digest"],
            "asset": asset,
            "state": "withdrawn",
            "reason": "source withdrawal",
            "observed_at": store.now(),
            "verifier_id": "reviewer",
            "worker_id": "producer",
        },
    )
    lifecycle(store, run_id, event)
    run = engine.load(store, run_id)
    assert engine.plan(store, run_id)["chosen"] is None
    exported = native_accounting.export(run, store.now())
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    checked = native_accounting.check_feedback(run, exported, report, store.now())
    assert checked["complete"] and checked["invalidated_assets"] == [asset]
    assert checked["costs"] == {"cost": 8}
    forged = copy.deepcopy(exported)
    forged["remaining_obligations"] = ["invented-review-demand"]
    with pytest.raises(ValueError, match="not bound"):
        native_accounting.check_feedback(run, forged, report, store.now())
    native_accounting.reconcile(store, run_id, exported, report, expected_revision=run["revision"])
    assert native_accounting.reconcile(
        store, run_id, exported, report, expected_revision=run["revision"]
    )["idempotent"]
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "review"
    after = engine.report(store, run_id)["ledgers"]["training"]
    assert after["observed_service"] == {"task": 4, "research": 4}
    assert after["actual_costs"] == {"cost": 8} and after["asset_count"] == 1


@native
def test_alt_native_receiver_admission_runs_existing_lifecycle(
    tmp_path: Path, native_test_clock: Any
) -> None:
    from datetime import timedelta

    from ccr.optimizer.growth_example import observation
    from ccr.optimizer.model import timestamp
    from ccr.optimizer.native_example import serial_alt_source
    from tests.test_growth import config, start

    key, raw = config()
    native_raw = serial_alt_source((FIXTURES / "alt.json").read_bytes())
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
        action["duration_seconds"] = 1
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
    store, run_id = start(tmp_path, raw)
    run = engine.load(store, run_id)
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": g["study_id"],
        "arm": "training",
        "pool_id": g["quota"]["pool_id"],
        "units": {"resource": {"target": "cost", "rate": "1", "rounding": "exact"}},
        "pools": {"verifier": "worker"},
        "clocks": {
            inspected["document_sha256"]["contract"]: {
                "utc_origin": store.now(),
                "tick_origin": "3",
                "seconds_per_tick": "1",
            }
        },
        "bindings": {
            names[s]: {
                "producer": "alt",
                "contract_sha256": inspected["document_sha256"]["contract"],
                "source_action": s,
                "action_sha256": sha256_json(g["actions"][names[s]]),
                "valid_from": "2020-01-01T00:00:00Z",
                "valid_until": g["window_end"],
            }
            for s in selected
        },
    }
    native_runtime.register(store, run_id, registration, expected_revision=0)
    projection = native_projection.project(native_raw, registration)
    staged = native_runtime.stage(
        store, run_id, native_raw, projection, expected_revision=1, idempotency_key="alt"
    )
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    assert not engine.report(store, run_id)["ledgers"]["training"]["receiver_qualifications"]
    for expected in g["bundles"]["delayed"]:
        assert engine.plan(store, run_id)["chosen"]["immediate_step"] == expected
        trial = engine.step(store, run_id, apply=True)["trial"]
        engine.claim(store, run_id, trial["trial_id"], worker="producer")
        engine.ingest(store, run_id, observation(store, run_id, trial["trial_id"], key))
        native_test_clock["now"] = (timestamp(store.now()) + timedelta(seconds=2)).isoformat()
        if expected == "form":
            assert (
                candidate + ":B"
                not in engine.report(store, run_id)["ledgers"]["training"][
                    "receiver_qualifications"
                ]
            )
    ledger = engine.report(store, run_id)["ledgers"]["training"]
    assert ledger["observed_service"] == {"task": 4, "research": 4}
    assert ledger["asset_count"] == 1 and candidate + ":B" in ledger["receiver_qualifications"]


@native
@pytest.mark.parametrize("status", ["positive", "negative", "timeout", "inconclusive", "invalid"])
@pytest.mark.parametrize("condition", ["completed", "positive", "negative"])
def test_vek_signed_negative_completes_work_without_service_credit(
    tmp_path: Path, status: str, condition: str, native_test_clock: Any
) -> None:
    import importlib
    from datetime import timedelta

    from ccr.optimizer.growth_example import observation, sign
    from ccr.optimizer.model import timestamp
    from tests.test_growth import config, start

    original = json.loads((FIXTURES / "vek.json").read_bytes())
    docs = {k: json.loads(v) for k, v in original["documents"].items()}
    c = docs["contract"]
    c["horizon"] = 16
    c["slot_seconds"] = "2"
    c["resources"][0]["capacity"] = [1] * 16
    c["services"][0]["valid_until"] = 16
    for work in c["work"]:
        work["deadline"] = 16
    source_names = list(docs["plan"]["schedule"])
    first_action = next(a for a in c["actions"] if a["action_id"] == source_names[0])
    second_action = next(a for a in c["actions"] if a["action_id"] == source_names[1])
    second_work = next(w for w in c["work"] if w["work_id"] == second_action["work_id"])
    second_work["predecessors"] = [first_action["work_id"]]
    if condition != "completed":
        second_action["requires_success" if condition == "positive" else "requires_negative"] = [
            source_names[0]
        ]
    model = importlib.import_module("verification_ecology_kit.capacity.model")
    checker = importlib.import_module("verification_ecology_kit.capacity.checker")
    reports = importlib.import_module("verification_ecology_kit.capacity.report")
    contract = model.Contract.from_dict(c)
    snapshot = checker.Snapshot(spent=[0, 0])
    plan = docs["plan"]
    plan.update(
        contract_digest=contract.contract_digest,
        schedule={name: i * 2 for i, name in enumerate(plan["schedule"])},
    )
    plan["checked"] = checker.check_schedule(contract, snapshot, plan["schedule"]).to_dict()
    docs["report"] = reports.capacity_report(contract, snapshot, plan)
    original["documents"] = {k: json.dumps(v) for k, v in docs.items()}
    native_raw = json.dumps(original).encode()
    inspected = native_checks.check(native_raw)
    key, raw = config()
    g = raw["growth"]
    template = copy.deepcopy(g["actions"]["greedy"])
    source_names = list(plan["schedule"])
    action_names = {name: "check" + str(i) for i, name in enumerate(source_names)}
    for source_name, name in action_names.items():
        a = copy.deepcopy(template)
        a.update(
            kind="diagnostic",
            intervention_id=name,
            target_id="target:" + name,
            gains={"task": 0, "research": 0},
        )
        g["actions"][name] = a
        arm = copy.deepcopy(raw["base"]["interventions"][0])
        arm.update(intervention_id=name, kind="measurement")
        raw["base"]["interventions"].append(arm)
        target = copy.deepcopy(raw["base"]["task_manifest"][0])
        source_action = next(x for x in c["actions"] if x["action_id"] == source_name)
        work = next(x for x in c["work"] if x["work_id"] == source_action["work_id"])
        target.update(target_id="target:" + name, input_sha256=work["input_digest"])
        raw["base"]["task_manifest"].append(target)
        for scenario in g["scenarios"].values():
            scenario[name] = None
    g["quota"]["capacity"] = g["quota"]["pool_capacity"] = {"reviewer": 1}
    for a in g["actions"].values():
        a["capacity"] = {"reviewer": 1}
    g["horizon_seconds"] = 60
    g["actions"]["greedy"]["verification_work"]["review"] = 100
    g["bundles"]["delayed"] = list(action_names.values())
    store, run_id = start(tmp_path, raw)
    run = engine.load(store, run_id)
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": g["study_id"],
        "arm": "training",
        "pool_id": g["quota"]["pool_id"],
        "units": {"check-work": {"target": "cost", "rate": "1", "rounding": "exact"}},
        "clocks": {
            inspected["document_sha256"]["contract"]: {
                "utc_origin": store.now(),
                "tick_origin": "0",
                "seconds_per_tick": "2",
            }
        },
        "bindings": {
            name: {
                "producer": "vek",
                "contract_sha256": inspected["document_sha256"]["contract"],
                "source_action": source_id,
                "action_sha256": sha256_json(g["actions"][name]),
                "valid_from": "2020-01-01T00:00:00Z",
                "valid_until": g["window_end"],
            }
            for source_id, name in action_names.items()
        },
    }
    native_runtime.register(store, run_id, registration, expected_revision=0)
    assert engine.plan(store, run_id)["chosen"] is None
    projected = native_projection.project(native_raw, registration)
    staged = native_runtime.stage(
        store, run_id, native_raw, projected, expected_revision=1, idempotency_key="vek"
    )
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    before = engine.load(store, run_id)
    assert native_runtime.blockers(
        before,
        list(action_names.values())[1],
        (timestamp(store.now()) + timedelta(seconds=4)).isoformat(),
        "training",
    ) == ["native_VEK_prerequisite_not_observed"]
    assert all(
        row["status"] == "pending"
        for row in native_runtime.verification_work(before, store.now()).values()
    )
    assert all(
        row["status"] == "censored"
        for row in native_runtime.verification_work(before, "2100-01-01T00:00:00Z").values()
    )
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(
        store, run_id, trial["trial_id"], key, success=status in {"positive", "invalid"}
    )
    if status in {"timeout", "inconclusive"}:
        envelope["observation"]["status"] = status
    if status == "invalid":
        result = {k: v for k, v in envelope["result"].items() if k != "signature_base64"}
        result["actual_resources"]["cost"] = 999
        envelope["result"] = sign(key, result)
    envelope = sign(key, {k: v for k, v in envelope.items() if k != "signature_base64"})
    result = engine.ingest(store, run_id, envelope)
    assert result["reward"] == 0
    native_test_clock["now"] = (timestamp(store.now()) + timedelta(seconds=4)).isoformat()
    report = engine.report(store, run_id)
    assert report["trials"][0]["state"] == "evaluated"
    assert report["ledgers"]["training"]["observed_service"] == {"task": 0, "research": 0}
    work = native_runtime.verification_work(engine.load(store, run_id), store.now())
    first = work[next(iter(action_names.values()))]
    assert first["status"] == status
    assert first["verification_completed"] == (status in {"positive", "negative"})
    if status in {"positive", "negative"} and condition in {"completed", status}:
        assert report["next_action"]["chosen"]["immediate_step"] == list(action_names.values())[1]
    else:
        assert report["next_action"]["chosen"] is None


def test_native_clock_exact_rounding_and_bounds() -> None:
    from fractions import Fraction

    from ccr.optimizer import native_clock

    clock = {"utc_origin": "2090-01-01T00:00:00Z", "tick_origin": "0", "seconds_per_tick": "1"}
    assert native_clock.utc(clock, Fraction(1, 3), lower=True) == "2090-01-01T00:00:00.333334+00:00"
    assert (
        native_clock.utc(clock, Fraction(1, 3), lower=False) == "2090-01-01T00:00:00.333333+00:00"
    )
    assert (
        native_clock.utc(clock, Fraction(-1, 3), lower=True) == "2089-12-31T23:59:59.666667+00:00"
    )
    for fault in (
        {**clock, "tick_origin": "-1"},
        {**clock, "seconds_per_tick": "0"},
        {**clock, "unexpected": "field"},
    ):
        with pytest.raises(ValueError):
            native_clock.validate(fault)
    with pytest.raises(ValueError, match="UTC range"):
        native_clock.utc(clock, Fraction(10**30), lower=True)
    window = {
        "available_at": clock["utc_origin"],
        "start": "2090-01-01T00:00:01Z",
        "end": "2090-01-01T00:00:05Z",
        "execution_end": "2090-01-01T00:00:05Z",
    }
    assert not native_clock.applicable(window, clock["utc_origin"])
    assert native_clock.applicable(window, window["start"], 3)
    assert native_clock.applicable(window, window["start"], 4)
    assert not native_clock.applicable(window, window["start"], 5)
    assert not native_clock.applicable(window, window["end"])


def test_cpcf_history_clock_preserves_elapsed_time_and_evidence_expiry() -> None:
    from ccr.optimizer import native_clock

    docs = native_checks.inspect((FIXTURES / "cpcf.json").read_bytes())["documents"]
    clock = {"utc_origin": "2090-01-01T00:00:00Z", "tick_origin": "0", "seconds_per_tick": "1"}
    docs["plan"]["spec"]["history"] = [{"action_id": "prepare"}]
    catalogue = docs["contract"]["spec"]["action_catalogue"]
    prepare = next(
        row
        for row in catalogue
        if docs["objects"][row["action_digest"]]["spec"]["action_id"] == "prepare"
    )
    # A separate clock oracle uses all branches, never one guessed hidden model.
    prepare["successors"][0]["evidence_added"]["calibrated"] = "3"
    interval = native_clock.window("cpcf", docs, "reuse", clock)
    assert interval["start"] == "2090-01-01T00:00:01+00:00"
    assert interval["end"] == "2090-01-01T00:00:03+00:00"
    for successor in prepare["successors"]:
        successor["evidence_added"] = {}
    with pytest.raises(ValueError, match="no mapped source clock"):
        native_clock.window("cpcf", docs, "reuse", clock)


@pytest.mark.parametrize("producer", ["alt", "vek", "cpcf"])
def test_native_clock_source_windows(producer: str) -> None:
    from ccr.optimizer import native_clock

    docs = native_checks.inspect((FIXTURES / (producer + ".json")).read_bytes())["documents"]
    name = {"alt": "reuse-0", "vek": "adapt-B", "cpcf": "prepare"}[producer]
    clock = {"utc_origin": "2090-01-01T00:00:00Z", "tick_origin": "0", "seconds_per_tick": "1"}
    interval = native_clock.window(producer, docs, name, clock)
    assert set(interval) == {"available_at", "start", "execution_end", "end"}
    if producer == "alt":
        assert interval == {
            "available_at": "2090-01-01T00:00:03+00:00",
            "start": "2090-01-01T00:00:05+00:00",
            "end": "2090-01-01T00:00:06+00:00",
            "execution_end": "2090-01-01T00:00:06+00:00",
        }
        assert (
            native_clock.window(producer, docs, "prepare", clock)["start"]
            == "2090-01-01T00:00:03+00:00"
        )
        altered = copy.deepcopy(docs)
        altered["contract"]["evidence_cutoff"] = 999
    elif producer == "vek":
        altered = copy.deepcopy(docs)
        altered["history"]["events"] = [{"unknown": "clock"}]
    else:
        assert interval["end"] == "2090-01-01T00:00:05+00:00"
        altered = copy.deepcopy(docs)
        altered["contract"]["spec"]["deadline"] = "0"
    with pytest.raises(ValueError):
        native_clock.window(producer, altered, name, clock)
    with pytest.raises(ValueError, match=r"clock rate|dimension"):
        native_clock.window(producer, docs, name, {**clock, "seconds_per_tick": "2"})
    with pytest.raises(ValueError, match="dimension"):
        native_clock.window("unknown", docs, name, clock)
