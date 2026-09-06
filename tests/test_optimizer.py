from __future__ import annotations

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ccr.cli import main
from ccr.ids import canonical_bytes, sha256_json
from ccr.operations.approval import create_operation_approval, validate_and_consume_approval
from ccr.optimizer import engine
from ccr.schemas.registry import validate_registered_report
from ccr.storage.control import ControlStore
from ccr.storage.local_store import SQLiteRuntimeStore

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def configuration(
    key: Ed25519PrivateKey, *, training: int = 10, holdout: int = 2
) -> dict[str, Any]:
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    return {
        "seed": 17,
        "deadline": "2099-01-01T00:00:00Z",
        "epsilon": 1.0,
        "resource_limits": {"cost": 100, "calls": 100},
        "effort_resource": "cost",
        "max_inflight": 8,
        "trusted_verifiers": {"reviewer": public},
        "task_manifest": [
            {
                "target_id": f"target.{i:03}",
                "input_ref": f"artifact:{i}",
                "input_sha256": sha256_json(i),
                "acceptance_criteria": "Produce an independently checked reusable repair.",
            }
            for i in range(training + holdout)
        ],
        "interventions": [
            {
                "intervention_id": arm,
                "kind": "verification",
                "resource_upper_bound": {"cost": 1, "calls": 1},
                "producer_ids": ["producer"],
            }
            for arm in ("a", "b")
        ],
        "evaluation": {
            "horizon": holdout,
            "alpha": 0.05,
            "holdout_tasks": [f"target.{i:03}" for i in range(training, training + holdout)],
            "resource_envelope": {"cost": 40, "calls": 40},
            "baseline_intervention": "a",
        },
    }


def start(tmp_path: Path, key: Ed25519PrivateKey, **kw: Any) -> tuple[ControlStore, str]:
    store = ControlStore(tmp_path, "")
    run = engine.initialize(store, mission="mission:test", config=configuration(key, **kw))
    return store, run["run_id"]


def sign(key: Ed25519PrivateKey, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {k: v for k, v in payload.items() if k != "signature_base64"}
    return {
        **payload,
        "signature_base64": base64.b64encode(key.sign(canonical_bytes(payload))).decode(),
    }


def observation(
    store: ControlStore,
    run_id: str,
    trial: dict[str, Any],
    key: Ed25519PrivateKey,
    *,
    accepted: bool = True,
    artifact: str | None = None,
) -> dict[str, Any]:
    current = next(
        t for t in engine.load(store, run_id)["trials"] if t["trial_id"] == trial["trial_id"]
    )
    packet = json.loads(
        (REPO / "examples/phase_formation/packets/checked/packet.phase.seed.json").read_text()
    )
    digest = artifact or sha256_json(trial["target_id"])
    packet["packet_id"] = "packet." + digest[:16]
    packet["issuer"]["actor_id"] = "producer"
    packet["artifacts"][0]["content_sha256"] = digest
    return sign(
        key,
        {
            "schema_version": "ccr.optimizer_result.v1",
            "run_id": run_id,
            "trial_id": trial["trial_id"],
            "target_id": trial["target_id"],
            "config_digest": trial["config_digest"],
            "input_digest": trial["input_digest"],
            "worker_id": current["worker_id"],
            "fencing_token": current["fencing_token"],
            "observed_at": store.now(),
            "verifier_id": "reviewer",
            "actual_resources": {"cost": 1, "calls": 1},
            "accepted": accepted,
            "residuals": [],
            "packet": packet,
            "artifact_sha256": digest,
        },
    )


def claimed_step(store: ControlStore, run_id: str) -> dict[str, Any]:
    step = engine.step(store, run_id, apply=True)
    assert step["ok"], step
    trial = step["trial"]
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    return trial


def test_closed_loop_updates_efficiency_and_freezes_holdout(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key)
    for _ in range(8):
        trial = claimed_step(store, run_id)
        result = observation(store, run_id, trial, key, accepted=trial["intervention_id"] == "b")
        engine.ingest(store, run_id, result)
    before = engine.report(store, run_id)
    assert before["scores"] == {"a": 0.0, "b": 1.0}
    assert not before["improvement_claim_admissible"]
    frozen = engine.freeze(store, run_id)["frozen_policy"]
    for _ in range(4):
        trial = claimed_step(store, run_id)
        assert trial["intervention_id"] == ("a" if trial["group"] == "baseline" else "b")
        engine.ingest(
            store,
            run_id,
            observation(store, run_id, trial, key, accepted=trial["group"] == "candidate"),
        )
    report = engine.report(store, run_id)
    assert report["evaluation_complete"]
    assert report["comparison"]["delta"] == 1
    assert not report[
        "improvement_claim_admissible"
    ]  # two observations cannot establish improvement
    assert report["frozen_policy"] == frozen
    assert report["scores"] == before["scores"]
    assert report["accounts"]["candidate"]["used"]["cost"] == 10  # includes training
    assert not validate_registered_report(report, root=REPO)


def test_plan_and_status_are_read_only(tmp_path: Path, key: Any) -> None:
    empty = tmp_path / "empty"
    assert engine.summaries(empty) == []
    assert not empty.exists()
    store, run_id = start(tmp_path, key)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    first = engine.plan(store, run_id)
    assert engine.step(store, run_id) == first
    engine.report(store, run_id)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert not validate_registered_report(first, root=REPO)


@pytest.mark.parametrize(
    "mutation",
    ["unsigned", "self", "candidate", "residual", "digest", "missing_cost", "nan", "scope"],
)
def test_no_unearned_reward(tmp_path: Path, key: Any, mutation: str) -> None:
    store, run_id = start(tmp_path, key)
    trial = claimed_step(store, run_id)
    result = observation(store, run_id, trial, key)
    if mutation == "unsigned":
        result["signature_base64"] = "invalid"
    elif mutation == "self":
        result["verifier_id"] = "producer"
    elif mutation == "candidate":
        result["packet"]["status"] = "candidate"
    elif mutation == "residual":
        result["residuals"] = [{"kind": "unresolved", "blocking": True}]
    elif mutation == "digest":
        result["packet"]["artifacts"][0]["content_sha256"] = "0" * 64
    elif mutation == "missing_cost":
        del result["actual_resources"]["calls"]
    elif mutation == "nan":
        result["actual_resources"]["cost"] = float("nan")
    elif mutation == "scope":
        result["input_digest"] = "other"
    if mutation not in {"unsigned", "nan"}:
        result = sign(key, result)
    try:
        accepted = engine.ingest(store, run_id, result)
        assert accepted["reward"] == 0
    except ValueError:
        pass
    assert not any(t["reward"] for t in engine.report(store, run_id)["trials"])


def test_duplicate_result_and_artifact_do_not_double_credit(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key)
    first = claimed_step(store, run_id)
    result = observation(store, run_id, first, key, artifact="a" * 64)
    assert engine.ingest(store, run_id, result)["reward"] == 1
    assert engine.ingest(store, run_id, result)["idempotent"]
    second = claimed_step(store, run_id)
    assert (
        engine.ingest(store, run_id, observation(store, run_id, second, key, artifact="a" * 64))[
            "reward"
        ]
        == 0
    )
    result["accepted"] = False
    with pytest.raises(ValueError, match="conflicting"):
        engine.ingest(store, run_id, sign(key, result))


def test_lease_fencing_restart_stop_and_overrun(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key)
    trial = claimed_step(store, run_id)
    stale = observation(store, run_id, trial, key)
    with store.edit(run_id) as (run, _):
        run["trials"][0]["lease_expires_at"] = "2000-01-01T00:00:00Z"
    resumed = ControlStore(tmp_path, "")
    assert engine.claim(resumed, run_id, trial["trial_id"], worker="producer")["fencing_token"] == 2
    with pytest.raises(ValueError, match="fencing_token"):
        engine.ingest(resumed, run_id, stale)
    with pytest.raises(ValueError, match="lease"):
        engine.task_transition(resumed, run_id, trial["trial_id"], worker="producer", token=1)
    result = observation(resumed, run_id, trial, key)
    result["actual_resources"]["cost"] = 3
    assert engine.ingest(resumed, run_id, sign(key, result))["reward"] == 0
    assert "resource_overrun" in engine.plan(resumed, run_id)["blockers"]
    engine.stop(resumed, run_id)
    assert "stopped" in engine.step(resumed, run_id, apply=True)["blockers"]


def contention(store: ControlStore, run_id: str) -> None:
    revision = engine.load(store, run_id)["revision"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: engine.step(store, run_id, apply=True, expected_revision=revision),
                range(8),
            )
        )
    assert sum(r.get("mutated_runtime", False) for r in results) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: engine.step(store, run_id, apply=True), range(25)))
    run = engine.report(store, run_id)
    assert len({t["target_id"] for t in run["trials"]}) == len(run["trials"])
    for account in run["accounts"].values():
        assert all(v >= 0 for v in account["remaining"].values())
    assert len(run["trials"]) <= 8


def test_sqlite_concurrent_reservation(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key)
    contention(store, run_id)


def operation() -> dict[str, Any]:
    return {
        "schema_version": "ccr.trc_operation_plan.v1",
        "plan_id": "plan.test",
        "constraints": {
            "allowed_commands": [],
            "requires_execute_flag": True,
            "requires_provider_config": True,
        },
        "executed": False,
        "settled": False,
        "execution_blockers": [],
        "residuals": [],
        "real_world_operation_ready": True,
        "operations": [
            {
                "action_type": "tool-call",
                "authority_envelope": {"expires_at": "2099-01-01T00:00:00Z", "status": "approved"},
                "resource_use": {"cost": 1, "calls": 1},
                "step_id": "step.test",
                "validity_domain": {"environment": "test"},
            }
        ],
    }


def provider_config() -> dict[str, Any]:
    return {
        "allow_execute": True,
        "allowed_provider_classes": ["http"],
        "provider_class": "http",
        "side_effect_policy": "controlled_provider_allowed",
        "endpoint": "https://example.test",
        "allowed_hosts": ["example.test"],
        "timeout_seconds": 10,
        "byte_limit": 4096,
    }


def approved(store: ControlStore, plan: dict[str, Any], nonce: str) -> dict[str, Any]:
    config = provider_config()
    result = create_operation_approval(
        store.root,
        plan=plan,
        provider="http",
        config=config,
        approvers=["operator"],
        expires_at="2099-01-01T00:00:00Z",
        nonce=nonce,
        control_store=store,
    )
    return {
        **config,
        "operator_approval_ref": result["approval"]["approval_id"],
        "approval_nonce": nonce,
    }


def test_mock_http_dispatch_and_unknown_not_retried(
    tmp_path: Path, key: Any, monkeypatch: Any
) -> None:
    from ccr.providers.http import HttpProvider

    calls = []

    def execute(self: Any, **kw: Any) -> dict[str, Any]:
        calls.append(kw)
        raise TimeoutError("after send")

    monkeypatch.setattr(HttpProvider, "execute", execute)
    config = configuration(key)
    for arm in config["interventions"]:
        arm["operation_plan"] = operation()
    store = ControlStore(tmp_path, "")
    run_id = engine.initialize(store, mission="mission:test", config=config)["run_id"]
    trial = claimed_step(store, run_id)
    assert not engine.dispatch(
        store,
        run_id,
        trial_id=trial["trial_id"],
        worker="producer",
        token=1,
        config=provider_config(),
        execute=True,
    )["ok"]
    settings = approved(store, trial["operation_plan"], "nonce.test")
    result = engine.dispatch(
        store,
        run_id,
        trial_id=trial["trial_id"],
        worker="producer",
        token=1,
        config=settings,
        execute=True,
    )
    assert result["state"] == "outcome_unknown"
    assert "unresolved_execution" in engine.plan(store, run_id)["blockers"]
    assert not engine.dispatch(
        store,
        run_id,
        trial_id=trial["trial_id"],
        worker="producer",
        token=1,
        config=settings,
        execute=True,
    )["ok"]
    assert len(calls) == 1
    assert engine.ingest(store, run_id, observation(store, run_id, trial, key))["reward"] == 1


def test_approval_tampering_and_concurrent_consumption(tmp_path: Path) -> None:
    store = ControlStore(tmp_path, "")
    plan = operation()
    config = approved(store, plan, "nonce.concurrent")
    altered = {**config, "byte_limit": 5}
    assert not validate_and_consume_approval(
        store.root, plan=plan, provider="http", config=altered, control_store=store
    )[0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(
            pool.map(
                lambda _: validate_and_consume_approval(
                    store.root, plan=plan, provider="http", config=config, control_store=store
                )[0],
                range(8),
            )
        )
    assert sum(values) == 1
    with pytest.raises(ValueError, match="nonce"):
        approved(store, plan, "nonce.concurrent")


def test_existing_worker_handles_optimizer_task(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key)
    engine.step(store, run_id, apply=True)
    worker = SQLiteRuntimeStore(tmp_path)
    claim = worker.claim_task(role="verifier", worker_id="producer", ttl_minutes=30)
    assert claim
    assert worker.heartbeat(task_id=claim["task_id"], worker_id="producer", fencing_token=1)["ok"]
    assert worker.complete(
        task_id=claim["task_id"],
        worker_id="producer",
        fencing_token=1,
        idempotency_key="result.1",
        result={"summary": "candidate only"},
    )["ok"]
    report = engine.report(store, run_id)
    assert report["trials"][0]["reward"] is None
    assert report["trials"][0]["state"] == "awaiting_verification"


def test_successful_http_feedback_changes_allocation(
    tmp_path: Path, key: Any, monkeypatch: Any
) -> None:
    from ccr.providers.http import HttpProvider

    receipts = []

    def execute(self: Any, **kw: Any) -> dict[str, Any]:
        receipts.append(kw["payload"]["operation_plan"]["optimizer_binding"])
        return {
            "ok": True,
            "network_call_performed": True,
            "effect_executed": True,
            "candidate": {"accepted": True},
        }

    monkeypatch.setattr(HttpProvider, "execute", execute)
    config = configuration(key)
    for arm in config["interventions"]:
        arm["operation_plan"] = operation()
    store = ControlStore(tmp_path, "")
    run_id = engine.initialize(store, mission="mission:http", config=config)["run_id"]
    for index in range(8):
        trial = claimed_step(store, run_id)
        preview = engine.dispatch(
            store,
            run_id,
            trial_id=trial["trial_id"],
            worker="producer",
            token=1,
            config={},
            execute=False,
        )
        assert not preview["mutated_runtime"]
        settings = approved(store, trial["operation_plan"], f"nonce.http.{index}")
        sent = engine.dispatch(
            store,
            run_id,
            trial_id=trial["trial_id"],
            worker="producer",
            token=1,
            config=settings,
            execute=True,
        )
        assert sent["ok"] and sent["network_call_performed"]
        assert engine.report(store, run_id)["trials"][-1]["reward"] is None
        engine.ingest(
            store,
            run_id,
            observation(store, run_id, trial, key, accepted=trial["intervention_id"] == "b"),
        )
    assert len(receipts) == 8
    assert engine.report(store, run_id)["scores"] == {"a": 0, "b": 1}


def test_holdout_claim_requires_complete_fixed_horizon(tmp_path: Path, key: Any) -> None:
    store, run_id = start(tmp_path, key, training=10, holdout=12)
    for _ in range(8):
        trial = claimed_step(store, run_id)
        engine.ingest(
            store,
            run_id,
            observation(store, run_id, trial, key, accepted=trial["intervention_id"] == "b"),
        )
    engine.freeze(store, run_id)
    for _ in range(23):
        trial = claimed_step(store, run_id)
        engine.ingest(
            store,
            run_id,
            observation(store, run_id, trial, key, accepted=trial["group"] == "candidate"),
        )
    assert not engine.report(store, run_id)["improvement_claim_admissible"]
    trial = claimed_step(store, run_id)
    engine.ingest(
        store,
        run_id,
        observation(store, run_id, trial, key, accepted=trial["group"] == "candidate"),
    )
    assert engine.report(store, run_id)["improvement_claim_admissible"]


def test_atomic_rollback_and_export(tmp_path: Path, key: Any, monkeypatch: Any) -> None:
    store, run_id = start(tmp_path, key)
    before = engine.load(store, run_id)
    original = store.sql

    def fail_outbox(connection: Any, query: str, values: Any = ()) -> Any:
        if query.startswith("INSERT INTO ccr_control_outbox"):
            raise RuntimeError("injected storage failure")
        return original(connection, query, values)

    monkeypatch.setattr(store, "sql", fail_outbox)
    with pytest.raises(RuntimeError, match="storage"):
        engine.step(store, run_id, apply=True)
    assert engine.load(store, run_id) == before
    monkeypatch.setattr(store, "sql", original)
    engine.step(store, run_id, apply=True)
    snapshots = store.export(run_id)
    assert len(snapshots) == 2
    assert store.export(run_id) == snapshots
    assert all(Path(item["path"]).is_file() for item in snapshots)
    with pytest.raises(ValueError, match="run id"):
        engine.stop(store, "operation:approvals")


@pytest.mark.parametrize("resolve", [False, True])
def test_residual_repair_requires_explicit_scoped_verified_resolution(
    tmp_path: Path, key: Any, resolve: bool
) -> None:
    config = configuration(key, training=1)
    config["task_manifest"][0]["input_ref"] = "residual:repair"
    for arm in config["interventions"]:
        arm["kind"] = "residual_repair"
    store = ControlStore(tmp_path, "")
    run_id = engine.initialize(store, mission="mission:test", config=config)["run_id"]
    with store.edit(run_id) as (run, _):
        run["residuals"] = [
            {
                "residual_id": "residual:repair",
                "object_id": "target.000",
                "kind": "repair_needed",
                "blocking": True,
                "status": "open",
            }
        ]
    trial = claimed_step(store, run_id)
    result = observation(store, run_id, trial, key)
    if resolve:
        result["resolved_residual_ids"] = ["residual:repair"]
    admitted = engine.ingest(store, run_id, sign(key, result))
    assert admitted["reward"] == (1 if resolve else 0)
    residual = engine.report(store, run_id)["residuals"][0]
    assert residual["residual_id"] == "residual:repair" and residual["blocking"]
    assert residual["status"] == ("resolved" if resolve else "open")
    if resolve:
        assert residual["resolution"]["artifact_sha256"] == result["artifact_sha256"]


def test_initial_capability_is_not_new_reward(tmp_path: Path, key: Any, monkeypatch: Any) -> None:
    import ccr.mission.model as mission_model

    packet = json.loads(
        (REPO / "examples/phase_formation/packets/checked/packet.phase.seed.json").read_text()
    )
    packet["artifacts"][0]["content_sha256"] = "f" * 64
    mission_file = tmp_path / "mission.json"
    mission_file.write_text("{}")
    monkeypatch.setattr(mission_model, "mission_path", lambda *args: mission_file)
    monkeypatch.setattr(
        mission_model,
        "mission_scope",
        lambda *args: {"ok": True, "packets": [packet], "residuals": []},
    )
    store, run_id = start(tmp_path, key)
    trial = claimed_step(store, run_id)
    result = engine.ingest(store, run_id, observation(store, run_id, trial, key, artifact="f" * 64))
    assert result["reward"] == 0
    assert "duplicate_outcome" in result["blockers"]


@pytest.mark.parametrize(
    "change",
    [
        "epsilon",
        "seed",
        "duplicate",
        "holdout",
        "horizon",
        "budget",
        "effort",
        "key",
        "cost",
        "timezone",
    ],
)
def test_registration_rejects_invalid_study(tmp_path: Path, key: Any, change: str) -> None:
    config = configuration(key)
    if change == "epsilon":
        config["epsilon"] = float("nan")
    elif change == "seed":
        config["seed"] = True
    elif change == "duplicate":
        config["task_manifest"].append(config["task_manifest"][0])
    elif change == "holdout":
        config["evaluation"]["holdout_tasks"] = ["not.registered"]
    elif change == "horizon":
        config["evaluation"]["horizon"] = 1
    elif change == "budget":
        config["evaluation"]["resource_envelope"]["cost"] = 60
    elif change == "effort":
        config["effort_resource"] = "unmeasured"
    elif change == "key":
        config["trusted_verifiers"]["reviewer"] = "broken"
    elif change == "cost":
        config["interventions"][0]["resource_upper_bound"]["cost"] = 0
    else:
        config["deadline"] = "2099-01-01"
    with pytest.raises(ValueError):
        engine.initialize(ControlStore(tmp_path, ""), mission="mission:test", config=config)
    assert not (tmp_path / "ccr.sqlite").exists()


def test_optimizer_api_identity_boundaries(tmp_path: Path, key: Any, monkeypatch: Any) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import ccr.distributed.server as server

    identity = {"sub": "human:operator"}
    monkeypatch.setattr(server, "verify_oidc_dpop", lambda **kw: dict(identity))
    client = TestClient(
        server.create_app(root=tmp_path, store=SQLiteRuntimeStore(tmp_path), auth_config={})
    )
    created = client.post(
        "/v1/optimizer", json={"mission": "mission:api", "config": configuration(key)}
    )
    assert created.status_code == 200
    run_id = created.json()["run_id"]
    trial = client.post(f"/v1/optimizer/{run_id}/step", json={"apply": True}).json()["trial"]
    identity["sub"] = "worker:actual"
    denied = client.post(f"/v1/optimizer/{run_id}/stop", json={})
    assert denied.status_code == 401
    claimed = client.post(
        f"/v1/optimizer/{run_id}/claim", json={"trial_id": trial["trial_id"], "worker": "spoofed"}
    )
    assert claimed.status_code == 200
    saved = client.get(f"/v1/optimizer/{run_id}").json()["trials"][0]
    assert saved["worker_id"] == "worker:actual"
    identity["sub"] = "human:operator"
    assert client.post(f"/v1/optimizer/{run_id}/stop", json={}).json()["state"] == "stopped"


def test_legacy_sqlite_approval_remains_usable(tmp_path: Path) -> None:
    from ccr.storage.sqlite import immediate_transaction

    store = ControlStore(tmp_path, "")
    plan = operation()
    config = approved(store, plan, "nonce.legacy")
    artifact = store.read("operation:approvals")["approvals"][config["operator_approval_ref"]][
        "artifact"
    ]
    with store.connection(write=True) as connection:
        connection.execute("DELETE FROM ccr_control WHERE object_key='operation:approvals'")
    with immediate_transaction(tmp_path) as connection:
        connection.execute(
            "INSERT INTO operation_approvals(approval_id,approval_digest,plan_digest,provider,"
            "use_count,max_uses,expires_at,updated_at) VALUES (?,?,?,?,0,1,?,?)",
            (
                artifact["approval_id"],
                sha256_json(artifact),
                sha256_json(plan),
                "http",
                artifact["expires_at"],
                artifact["created_at"],
            ),
        )
    assert validate_and_consume_approval(
        tmp_path, plan=plan, provider="http", config=config, control_store=store
    )[0]
    assert not validate_and_consume_approval(
        tmp_path, plan=plan, provider="http", config=config, control_store=store
    )[0]


def test_cli_init_and_invalid_config(tmp_path: Path, key: Any, capsys: Any) -> None:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(configuration(key)))
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "optimizer",
                "init",
                "--mission",
                "mission:test",
                "--config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    run_id = json.loads(capsys.readouterr().out)["run_id"]
    assert main(["--root", str(tmp_path), "optimizer", "step", "--run", run_id, "--json"]) == 0
    assert not json.loads(capsys.readouterr().out)["mutated_runtime"]
    config.write_text("{}")
    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "optimizer",
                "init",
                "--mission",
                "mission:test",
                "--config",
                str(config),
            ]
        )
        != 0
    )
    assert json.loads(capsys.readouterr().out)["blockers"]


def test_cli_complete_local_workflow(tmp_path: Path, key: Any, capsys: Any) -> None:
    store, run_id = start(tmp_path, key, training=1, holdout=2)

    def command(*args: str) -> dict[str, Any]:
        assert main(["--root", str(tmp_path), "optimizer", *args, "--run", run_id, "--json"]) == 0
        return json.loads(capsys.readouterr().out)

    trial = command("step", "--apply")["trial"]
    command("claim", "--trial", trial["trial_id"], "--worker", "producer")
    command(
        "heartbeat", "--trial", trial["trial_id"], "--worker", "producer", "--fencing-token", "1"
    )
    result_file = tmp_path / "signed-result.json"
    result_file.write_text(json.dumps(observation(store, run_id, trial, key)))
    assert command("ingest", "--file", str(result_file))["reward"] == 1
    assert command("status")["trials"][0]["reward"] == 1
    command("report")
    command("freeze")
    command("stop")
    assert command("export")["exports"]


def test_mission_and_workbench_show_scoped_optimizer(tmp_path: Path, key: Any) -> None:
    from ccr.extensions import loop_next
    from ccr.mission.init import asi_quickstart
    from ccr.mission.next import mission_next
    from ccr.mission.status import mission_status
    from ccr.workbench.static import export_static_workbench
    from ccr.workbench.summary import build_workbench_report

    asi_quickstart(tmp_path)
    store = ControlStore(tmp_path, "")
    first = engine.initialize(store, mission="mission:quickstart", config=configuration(key))[
        "run_id"
    ]
    engine.initialize(store, mission="mission:other", config=configuration(key))
    assert [
        r["run_id"] for r in mission_status(tmp_path, mission_id="mission:quickstart")["optimizer"]
    ] == [first]
    assert (
        len(mission_next(tmp_path, mission_id="mission:quickstart", compact=True)["optimizer"]) == 1
    )
    assert len(build_workbench_report(tmp_path, mission_id="mission:quickstart")["optimizer"]) == 1
    assert len(loop_next(tmp_path, compact=True)["optimizer"]) == 2
    export_static_workbench(tmp_path, mission_id="mission:quickstart", out=tmp_path / "site")
    assert first in (tmp_path / "site" / "index.html").read_text()


@pytest.mark.skipif(not os.getenv("CCR_TEST_POSTGRES_URL"), reason="requires real PostgreSQL")
def test_postgres_real_concurrency_and_shared_approval(tmp_path: Path, key: Any) -> None:
    import uuid

    store = ControlStore(tmp_path, os.environ["CCR_TEST_POSTGRES_URL"])
    run_id = engine.initialize(
        store, mission="mission:" + uuid.uuid4().hex, config=configuration(key)
    )["run_id"]
    contention(store, run_id)
    config = approved(store, operation(), "nonce." + uuid.uuid4().hex)
    other = ControlStore(tmp_path / "other-host", os.environ["CCR_TEST_POSTGRES_URL"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(
            pool.map(
                lambda _: validate_and_consume_approval(
                    other.root,
                    plan=operation(),
                    provider="http",
                    config=config,
                    control_store=other,
                )[0],
                range(8),
            )
        )
    assert sum(values) == 1
    trial = engine.load(other, run_id)["trials"][0]
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(
            pool.map(
                lambda i: engine.claim(other, run_id, trial["trial_id"], worker=f"worker.{i}"),
                range(8),
            )
        )
    assert sum(v["ok"] for v in values) == 1
    result = observation(other, run_id, trial, key)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: engine.ingest(other, run_id, result), range(8)))
    assert sum(t["reward"] or 0 for t in engine.report(other, run_id)["trials"]) == 1
    assert not (other.root / "ccr.sqlite").exists()


@pytest.mark.skipif(not os.getenv("CCR_TEST_POSTGRES_URL"), reason="requires real PostgreSQL")
@pytest.mark.parametrize("outcome", ["success", "timeout", "crash"])
def test_postgres_dispatch_restart_and_late_observation(
    tmp_path: Path, key: Any, monkeypatch: Any, outcome: str
) -> None:
    import uuid

    from ccr.providers.http import HttpProvider

    calls = []

    def external(self: Any, **kw: Any) -> dict[str, Any]:
        calls.append(kw)
        if outcome == "timeout":
            raise TimeoutError("after send")
        if outcome == "crash":
            raise SystemExit("process interruption after send")
        return {"ok": True, "network_call_performed": True, "effect_executed": True}

    monkeypatch.setattr(HttpProvider, "execute", external)
    store = ControlStore(tmp_path, os.environ["CCR_TEST_POSTGRES_URL"])
    config = configuration(key)
    for arm in config["interventions"]:
        arm["operation_plan"] = operation()
    run_id = engine.initialize(store, mission="mission:" + uuid.uuid4().hex, config=config)[
        "run_id"
    ]
    trial = claimed_step(store, run_id)
    with store.edit(run_id) as (run, _):
        run["trials"][0]["lease_expires_at"] = "2000-01-01T00:00:00Z"
    recovered = ControlStore(tmp_path / "another-host", os.environ["CCR_TEST_POSTGRES_URL"])
    assert (
        engine.claim(recovered, run_id, trial["trial_id"], worker="new-worker")["fencing_token"]
        == 2
    )
    settings = approved(store, trial["operation_plan"], "nonce." + uuid.uuid4().hex)
    with pytest.raises(ValueError, match="lease"):
        engine.dispatch(
            recovered,
            run_id,
            trial_id=trial["trial_id"],
            worker="producer",
            token=1,
            config=settings,
            execute=True,
        )
    if outcome == "crash":
        with pytest.raises(SystemExit):
            engine.dispatch(
                recovered,
                run_id,
                trial_id=trial["trial_id"],
                worker="new-worker",
                token=2,
                config=settings,
                execute=True,
            )
    else:
        engine.dispatch(
            recovered,
            run_id,
            trial_id=trial["trial_id"],
            worker="new-worker",
            token=2,
            config=settings,
            execute=True,
        )
    assert not engine.dispatch(
        recovered,
        run_id,
        trial_id=trial["trial_id"],
        worker="new-worker",
        token=2,
        config=settings,
        execute=True,
    )["ok"]
    assert len(calls) == 1
    assert engine.report(recovered, run_id)["accounts"]["training"]["reserved"]["cost"] == 1
    if outcome == "success":
        assert any(
            trial["operation_plan"]["plan_id"] in event.get("refs", [])
            for event in store.list_objects("event:")
        )
    engine.stop(recovered, run_id)
    assert (
        engine.ingest(recovered, run_id, observation(recovered, run_id, trial, key))["reward"] == 1
    )
    assert not (recovered.root / "ccr.sqlite").exists()
