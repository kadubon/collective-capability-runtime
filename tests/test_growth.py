# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from hypothesis import given, settings
from hypothesis import strategies as st

from ccr.ids import sha256_json
from ccr.optimizer import engine, growth_checker, growth_ledger, growth_model, growth_planner
from ccr.optimizer.growth_example import fixture, observation, run_example, sign
from ccr.optimizer.growth_runtime import lifecycle
from ccr.storage.control import ControlStore


def test_growth_unknown_dispatch_retains_bundle_and_no_resend(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from ccr.providers.http import HttpProvider
    from tests.test_optimizer import approved, operation

    key, raw = config()
    raw["base"]["interventions"][0]["operation_plan"] = operation()
    raw["growth"]["actions"]["form"]["authority"] = "operation_approval_required"
    calls = []

    def timeout(self: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        raise TimeoutError("synthetic ambiguous send")

    monkeypatch.setattr(HttpProvider, "execute", timeout)
    store, run_id = start(tmp_path, raw)
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    settings = approved(store, trial["operation_plan"], "nonce.growth")
    reserved = engine.load(store, run_id)["growth_reservation"]
    args = dict(
        trial_id=trial["trial_id"], worker="producer", token=1, config=settings, execute=True
    )
    assert engine.dispatch(store, run_id, **args)["state"] == "outcome_unknown"
    restored = ControlStore(tmp_path, "")
    assert engine.load(restored, run_id)["growth_reservation"] == reserved
    assert "unresolved_execution" in engine.plan(restored, run_id)["blockers"]
    assert not engine.dispatch(restored, run_id, **args)["ok"]
    assert len(calls) == 1
    report = engine.report(restored, run_id)
    assert report["verifier_pressure"]["unfinished_trials"] == [trial["trial_id"]]
    assert report["ledgers"]["training"]["observed_service"] == {"task": 0, "research": 0}
    engine.ingest(restored, run_id, observation(restored, run_id, trial["trial_id"], key))
    assert engine.load(restored, run_id)["growth_reservation"] is None


def test_verifier_investment_changes_supported_service(tmp_path: Path) -> None:
    key, raw = config()
    g = raw["growth"]
    g["actions"]["form"]["kind"] = "verification_investment"
    g["actions"]["form"]["service_measurement"]["review"] = 2
    raw["base"]["interventions"][0]["kind"] = "measurement"
    for n in ("reuse", "reuse_again"):
        g["actions"][n]["verification_work"]["review"] = 4
    store, run_id = start(tmp_path, raw)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "form"
    assert not engine.report(store, run_id)["ledgers"]["training"]["measured_verifier_service"]
    finish(store, run_id, key)
    ledger = engine.report(store, run_id)["ledgers"]["training"]
    assert next(iter(ledger["measured_verifier_service"].values())) == {"review": 2}
    for _ in range(3):
        finish(store, run_id, key)
    assert engine.report(store, run_id)["ledgers"]["training"]["observed_service"]["task"] == 4


@pytest.mark.parametrize(
    "missing", ["quality", "service", "freshness", "scope", "budget", "expiry", "capacity"]
)
def test_insufficient_bundle_evidence_prefers_admissible_baseline(
    tmp_path: Path, missing: str
) -> None:
    _, raw = config()
    g = raw["growth"]
    if missing == "quality":
        g["receivers"]["receiver"]["quality"] = "higher"
    elif missing == "service":
        g["actions"]["reuse"]["verification_work"]["review"] = 100
    elif missing == "freshness":
        g["assets"][next(iter(g["assets"]))]["expires_at"] = "2000-01-01T00:00:00Z"
    elif missing == "scope":
        g["assets"][next(iter(g["assets"]))]["receivers"] = ["source"]
    elif missing == "budget":
        raw["base"]["interventions"][0]["resource_upper_bound"]["cost"] = 19
    elif missing == "expiry":
        g["actions"]["form"]["duration_seconds"] = 30
    else:
        g["actions"]["form"]["capacity"]["worker"] = 2
    store, run_id = start(tmp_path, raw)
    plan = engine.plan(store, run_id)
    assert plan["chosen"]["bundle_id"] == "simple"
    rejected = next(c for c in plan["candidates"] if c["bundle_id"] == "delayed")
    forged = {
        **plan,
        "chosen": rejected,
        "selected": {"group": "training", "intervention_id": "form", "target_id": "target:form"},
    }
    assert not growth_checker.check(engine.load(store, run_id), forged, store.now())["ok"]
    assert growth_checker.check(engine.load(store, run_id), plan, store.now())["ok"]


def test_budget_truncation_and_null_are_not_impossibility(tmp_path: Path) -> None:
    _, raw = config()
    raw["growth"]["candidate_limit"] = 1
    raw["growth"]["scenarios"]["finite"]["form"] = None
    store, run_id = start(tmp_path, raw)
    plan = engine.plan(store, run_id)
    assert not plan["search"]["complete"]
    assert "search_incomplete_unknown" in plan["blockers"]
    assert not plan["global_optimality"]


def test_atomic_growth_ingest_and_outbox_failure(tmp_path: Path, monkeypatch: Any) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key)
    original = store.sql
    before = engine.load(store, run_id)

    def fail(connection: Any, query: str, values: Any = ()) -> Any:
        if query.startswith("INSERT INTO ccr_control_outbox"):
            raise RuntimeError("injected outbox fault")
        return original(connection, query, values)

    monkeypatch.setattr(store, "sql", fail)
    with pytest.raises(RuntimeError, match="outbox"):
        engine.ingest(store, run_id, envelope)
    assert engine.load(store, run_id) == before
    monkeypatch.setattr(store, "sql", original)
    assert engine.ingest(store, run_id, envelope)["ok"]


def test_pinned_interchange_and_unknown_fields_remain_evidence(tmp_path: Path) -> None:
    from ccr.optimizer.growth_interchange import export_cait, import_evidence, read_fixture

    sources = json.loads(read_fixture("sources.json"))
    for tool in ("vek", "alt"):
        p = json.loads(read_fixture(tool + ".json"))
        source = sources[tool]
        envelope = {
            "tool": tool,
            "source_commit": source["commit"],
            "schema_sha256": source["sha256"],
            "payload": p,
        }
        report = import_evidence(envelope)
        assert report["original"] == p
        assert report["service_credit"] == 0 and not report["receiver_qualified"]
        assert not report["execution_authorized"]
        envelope["source_commit"] = "unknown"
        with pytest.raises(ValueError, match="version"):
            import_evidence(envelope)
        envelope["source_commit"] = source["commit"]
        envelope["payload"] = {}
        with pytest.raises(ValueError, match="schema"):
            import_evidence(envelope)
    _, raw = config()
    store, run_id = start(tmp_path, raw)
    exported = export_cait(engine.report(store, run_id))
    assert not exported["cait_conformant_certificate"]
    assert exported["arrival_certificate"] is None


def test_schema_contracts_and_legacy_result_separation(tmp_path: Path) -> None:
    from ccr.schemas.registry import validate_registered_report
    from ccr.schemas.validation import validate_instance

    key, raw = config()
    assert validate_instance("growth-profile", raw).ok
    store, run_id = start(tmp_path, raw)
    assert not validate_registered_report(
        engine.plan(store, run_id), root=Path(__file__).resolve().parents[1]
    )
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key)
    assert validate_instance("growth-result", envelope).ok
    with pytest.raises(ValueError, match="separate signed"):
        engine.ingest(store, run_id, envelope["result"])
    engine.ingest(store, run_id, envelope)
    assert not validate_registered_report(
        engine.report(store, run_id), root=Path(__file__).resolve().parents[1]
    )


def add_action(raw: dict[str, Any], name: str, template: str) -> dict[str, Any]:
    a = copy.deepcopy(raw["growth"]["actions"][template])
    a.update(intervention_id=name, target_id="target:" + name)
    raw["growth"]["actions"][name] = a
    arm = copy.deepcopy(
        next(i for i in raw["base"]["interventions"] if i["intervention_id"] == template)
    )
    arm["intervention_id"] = name
    raw["base"]["interventions"].append(arm)
    target = copy.deepcopy(raw["base"]["task_manifest"][0])
    target["target_id"] = a["target_id"]
    raw["base"]["task_manifest"].append(target)
    for scenario in raw["growth"]["scenarios"].values():
        scenario[name] = True
    return a


def test_multi_parent_coalition_and_distinct_reuse_conserve_credit(tmp_path: Path) -> None:
    key, raw = config()
    g = raw["growth"]
    first = next(iter(g["assets"]))
    second, child = sha256_json("coinput"), sha256_json("child")
    g["assets"][second] = copy.deepcopy(g["assets"][first])
    g["assets"][child] = {**copy.deepcopy(g["assets"][first]), "parents": [first, second]}
    add_action(raw, "form_second", "form")["produces"] = second
    c = add_action(raw, "form_child", "form")
    c.update(produces=child, requires=[first, second])
    g["actions"]["transfer"]["requires"] = [child]
    g["actions"]["reuse"]["requires"] = [child]
    g["actions"]["reuse_again"]["requires"] = [child]
    g["bundles"]["delayed"] = [
        "form",
        "form_second",
        "form_child",
        "transfer",
        "reuse",
        "reuse_again",
    ]
    store, run_id = start(tmp_path, raw)
    for _ in range(6):
        finish(store, run_id, key)
    ledger = engine.report(store, run_id)["ledgers"]["training"]
    assert ledger["observed_service"] == {"task": 4, "research": 4}
    assert ledger["asset_count"] == 3
    assert ledger["assets"][child]["parents"] == [first, second]
    assert len(ledger["service_events"]) == 2
    assert ledger["attribution_unresolved"]


def test_revalidation_requires_new_signed_trial(tmp_path: Path) -> None:
    key, raw = config()
    g = raw["growth"]
    a = add_action(raw, "revalidate", "form")
    a["kind"] = "revalidation"
    raw["base"]["interventions"][-1]["kind"] = "verification"
    g["bundles"]["revalidation"] = ["revalidate", "transfer", "reuse", "reuse_again"]
    store, run_id = start(tmp_path, raw)
    finish(store, run_id, key)
    run = engine.load(store, run_id)
    asset = next(iter(g["assets"]))
    event = sign(
        key,
        {
            "event_id": "quarantine:1",
            "run_id": run_id,
            "config_digest": run["config"]["config_digest"],
            "asset": asset,
            "state": "quarantined",
            "reason": "needs fresh evaluation",
            "observed_at": store.now(),
            "verifier_id": "reviewer",
            "worker_id": "producer",
        },
    )
    lifecycle(store, run_id, event)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "revalidate"
    finish(store, run_id, key)
    assert asset in engine.report(store, run_id)["ledgers"]["training"]["eligible_assets"]


def test_cli_growth_views_and_interchange(tmp_path: Path, capsys: Any) -> None:
    from ccr.cli import main
    from ccr.optimizer.growth_interchange import read_fixture

    _, raw = config()
    store, run_id = start(tmp_path, raw)
    prefix = ["--root", str(tmp_path), "optimizer"]
    for command in ("growth-ledger", "replay"):
        assert main([*prefix, command, "--run", run_id, "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["ledgers"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(engine.plan(store, run_id)))
    assert main([*prefix, "check-plan", "--run", run_id, "--file", str(path)]) == 0
    capsys.readouterr()
    source = json.loads(read_fixture("sources.json"))["vek"]
    path.write_text(
        json.dumps(
            {
                "tool": "vek",
                "source_commit": source["commit"],
                "schema_sha256": source["sha256"],
                "payload": json.loads(read_fixture("vek.json")),
            }
        )
    )
    for _ in range(2):
        assert (
            main(
                [
                    *prefix,
                    "interchange",
                    "--run",
                    run_id,
                    "--tool",
                    "vek",
                    "--file",
                    str(path),
                    "--apply",
                ]
            )
            == 0
        )
        capsys.readouterr()
    assert len(engine.report(store, run_id)["residuals"]) == 1
    assert main([*prefix, "interchange", "--run", run_id, "--tool", "cait"]) == 0
    assert not json.loads(capsys.readouterr().out)["cait_conformant_certificate"]


def config() -> tuple[Any, dict[str, Any]]:
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode()
    return key, fixture(public, study="study:" + uuid4().hex)


def start(root: Path, raw: dict[str, Any]) -> tuple[ControlStore, str]:
    store = ControlStore(root, "")
    return store, engine.initialize(store, mission="mission:source", config=raw)["run_id"]


def finish(store: ControlStore, run_id: str, key: Any, **kwargs: Any) -> dict[str, Any]:
    proposal = engine.plan(store, run_id)
    assert proposal["ok"], proposal
    assert growth_checker.check(engine.load(store, run_id), proposal, store.now())["ok"]
    trial = engine.step(store, run_id, apply=True, expected_revision=proposal["revision"])["trial"]
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    envelope = observation(store, run_id, trial["trial_id"], key, **kwargs)
    engine.ingest(store, run_id, envelope)
    return envelope


def test_real_loop_and_frozen_comparison(tmp_path: Path) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    first = engine.plan(store, run_id)
    before = engine.load(store, run_id)
    assert first["chosen"]["immediate_step"] == "form"
    assert first["chosen"]["objective"] == "1"
    assert engine.step(store, run_id) == first
    assert engine.load(store, run_id) == before
    for _ in range(4):
        envelope = finish(store, run_id, key)
        assert engine.ingest(store, run_id, envelope)["idempotent"]
    ledger = engine.report(store, run_id)["ledgers"]["training"]
    assert ledger["asset_count"] == 1
    assert len(ledger["service_events"]) == 2
    assert ledger["observed_service"] == {"task": 4, "research": 4}
    assert ledger["actual_costs"] == {"cost": 8}
    assert ledger["attribution_unresolved"] and ledger["causal_gain"] is None
    frozen = engine.freeze(store, run_id)["frozen_policy"]
    for _ in range(8):
        finish(store, run_id, key)
    report = engine.report(store, run_id)
    assert report["evaluation_complete"]
    assert report["frozen_policy"] == frozen
    assert report["observed_comparison"] == {"task": 0, "research": 0}
    assert not report["improvement_claim_admissible"]
    assert report["accounts"]["candidate"]["used"] == {"cost": 16}
    assert report["accounts"]["baseline"]["used"] == {"cost": 8}
    assert store.export(run_id) == store.export(run_id)


@pytest.mark.parametrize(
    "field", ["objective", "steps", "reservation", "duration_seconds", "immediate_step"]
)
def test_independent_checker_rejects_tampering(tmp_path: Path, field: str) -> None:
    _, raw = config()
    store, run_id = start(tmp_path, raw)
    plan = engine.plan(store, run_id)
    plan["chosen"][field] = "forged"
    assert not growth_checker.check(engine.load(store, run_id), plan, store.now())["ok"]


@pytest.mark.parametrize(
    "field",
    [
        "receiver",
        "context_sha256",
        "protocol",
        "evaluator",
        "parents",
        "evidence_mode",
        "artifact_version",
        "external_inputs",
        "action_id",
        "study_id",
    ],
)
def test_signed_scope_tampering_fails(tmp_path: Path, field: str) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    o = observation(store, run_id, trial["trial_id"], key)
    o["observation"][field] = "tampered"
    before = engine.load(store, run_id)
    with pytest.raises(ValueError):
        engine.ingest(store, run_id, sign(key, o))
    assert engine.load(store, run_id) == before


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), 1.5, "1", None])
def test_exact_units_fail_closed(tmp_path: Path, value: Any) -> None:
    _, raw = config()
    raw["growth"]["actions"]["form"]["cleanup_cost"]["cost"] = value
    with pytest.raises(ValueError):
        start(tmp_path, raw)
    assert not (tmp_path / "ccr.sqlite").exists()


def test_pending_failure_and_model_inconsistency(tmp_path: Path) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    finish(store, run_id, key)
    assert (
        engine.report(store, run_id)["ledgers"]["training"]["delayed_reuse"][0]["state"]
        == "pending"
    )
    finish(store, run_id, key, success=False)
    report = engine.report(store, run_id)
    assert report["ledgers"]["training"]["observed_service"] == {"task": 0, "research": 0}
    assert not report["next_action"]["ok"]
    assert report["ledgers"]["training"]["compatible_scenarios"] == []
    with pytest.raises(ValueError, match="inconsistent"):
        engine.freeze(store, run_id)
    ledger = growth_ledger.replay(engine.load(store, run_id), "2099-01-02T00:00:00Z")
    assert ledger["delayed_reuse"][0]["state"] == "censored"
    assert ledger["invalidated_assets"]


def test_withdrawal_preserves_history_and_blocks_receiver(tmp_path: Path) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    for _ in range(3):
        finish(store, run_id, key)
    run = engine.load(store, run_id)
    asset = next(iter(raw["growth"]["assets"]))
    event = sign(
        key,
        {
            "event_id": "withdraw:1",
            "run_id": run_id,
            "config_digest": run["config"]["config_digest"],
            "asset": asset,
            "state": "withdrawn",
            "reason": "counterexample",
            "observed_at": store.now(),
            "verifier_id": "reviewer",
            "worker_id": "producer",
        },
    )
    assert lifecycle(store, run_id, event)["ok"]
    assert lifecycle(store, run_id, event)["idempotent"]
    report = engine.report(store, run_id)
    assert report["ledgers"]["training"]["observed_service"] == {"task": 2, "research": 2}
    assert not report["ledgers"]["training"]["eligible_assets"]
    assert report["next_action"]["chosen"]["immediate_step"] == "greedy"
    event["reason"] = "conflicting duplicate"
    with pytest.raises(ValueError, match="conflicting"):
        lifecycle(store, run_id, sign(key, event))
    corrupted = engine.load(store, run_id)
    corrupted["growth_events"][0]["policy_revision"] += 1
    with pytest.raises(ValueError, match="journal"):
        growth_ledger.replay(corrupted, store.now())


def test_receiver_grants_and_unverified_prerequisites(tmp_path: Path) -> None:
    key, raw = config()
    raw["growth"]["receivers"]["receiver"]["cross_mission_allowed"] = False
    store, run_id = start(tmp_path, raw)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "greedy"
    finish(store, run_id, key)
    assert engine.report(store, run_id)["ledgers"]["training"]["asset_count"] == 0


def test_quota_and_study_restart_conservation(tmp_path: Path) -> None:
    _, raw = config()
    store, run_id = start(tmp_path, raw)
    with pytest.raises(FileExistsError):
        start(tmp_path, raw)
    other = copy.deepcopy(raw)
    other["growth"]["study_id"] += "other"
    with pytest.raises(ValueError, match="quota"):
        start(tmp_path, other)
    assert len(store.list_objects("optimizer:")) == 1
    assert engine.load(store, run_id)["revision"] == 0


def test_concurrent_reserve_and_fences(tmp_path: Path) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: engine.step(store, run_id, apply=True, expected_revision=0), range(8)
            )
        )
    assert sum(r.get("mutated_runtime", False) for r in results) == 1
    trial = engine.load(store, run_id)["trials"][0]
    assert engine.report(store, run_id)["accounts"]["training"]["reserved"] == {"cost": 8}
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key)
    with store.edit(run_id) as (run, _):
        run["trials"][0]["lease_expires_at"] = "2000-01-01T00:00:00Z"
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    with pytest.raises(ValueError, match="fencing"):
        engine.ingest(store, run_id, envelope)
    engine.stop(store, run_id)
    assert engine.report(store, run_id)["accounts"]["training"]["reserved"] == {"cost": 8}


@settings(max_examples=12, deadline=None)
@given(
    st.integers(min_value=1, max_value=12),
    st.permutations(["delayed", "simple", "holdout_delayed", "holdout_simple"]),
)
def test_tiny_independent_oracle_and_catalogue_permutation(
    formation_cost: int, order: list[str]
) -> None:
    # Independent arithmetic oracle for this two-alternative finite domain.
    # It never invokes planner/checker helpers to calculate the optimum.
    _, raw = config()
    raw["base"]["interventions"][0]["resource_upper_bound"]["cost"] = formation_cost
    raw["growth"]["bundles"] = {k: raw["growth"]["bundles"][k] for k in order}
    normalized = growth_model.normalize(raw)
    run = {
        "config": normalized,
        "run_id": "optimizer:oracle",
        "revision": 0,
        "state": "training",
        "blockers": [],
        "trials": [],
        "growth_events": [],
        "frozen_policy": None,
    }
    candidates = [(Fraction(1, 4), 2, "simple")]
    if formation_cost + 7 <= 18:
        candidates.append((Fraction(1), formation_cost + 7, "delayed"))
    oracle = sorted(candidates, key=lambda c: (-c[0], c[1], c[2]))[0]
    plan = growth_planner.plan(run, "2026-09-12T00:00:00Z")
    assert plan["chosen"]["bundle_id"] == oracle[2]
    assert plan["chosen"]["objective"] == str(oracle[0])
    assert growth_checker.check(run, plan, "2026-09-12T00:00:00Z")["ok"]


def test_offline_packaged_entry() -> None:
    result = run_example()
    assert result["ok"] and not result["network_call_performed"]


def test_api_identity_and_new_path(tmp_path: Path, monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    import ccr.distributed.server as server
    from ccr.storage.local_store import SQLiteRuntimeStore

    key, raw = config()
    identity = {"sub": "human:operator"}
    monkeypatch.setattr(server, "verify_oidc_dpop", lambda **kw: dict(identity))
    client = TestClient(
        server.create_app(root=tmp_path, store=SQLiteRuntimeStore(tmp_path), auth_config={})
    )
    run_id = client.post("/v1/optimizer", json={"mission": "mission:source", "config": raw}).json()[
        "run_id"
    ]
    proposal = client.post(f"/v1/optimizer/{run_id}/step", json={}).json()
    assert client.post(f"/v1/optimizer/{run_id}/check-plan", json=proposal).json()["ok"]
    trial = client.post(f"/v1/optimizer/{run_id}/step", json={"apply": True}).json()["trial"]
    identity["sub"] = "worker:actual"
    client.post(
        f"/v1/optimizer/{run_id}/claim", json={"trial_id": trial["trial_id"], "worker": "spoof"}
    )
    envelope = observation(ControlStore(tmp_path, ""), run_id, trial["trial_id"], key)
    identity["sub"] = "worker:spoof"
    assert client.post(f"/v1/optimizer/{run_id}/ingest", json=envelope).status_code == 409
    identity["sub"] = "worker:actual"
    assert client.post(f"/v1/optimizer/{run_id}/ingest", json=envelope).json()["ok"]
    assert client.post(f"/v1/optimizer/{run_id}/stop", json={}).status_code == 401


def test_real_oidc_dpop_growth_loop(tmp_path: Path) -> None:
    from authlib.jose import JsonWebKey, JsonWebToken
    from fastapi.testclient import TestClient

    from ccr.distributed.auth import _jwk_thumbprint
    from ccr.distributed.server import create_app
    from ccr.storage.local_store import SQLiteRuntimeStore

    issuer_key = JsonWebKey.generate_key("EC", "P-256", is_private=True, options={"kid": "issuer"})
    proof_key = JsonWebKey.generate_key("EC", "P-256", is_private=True)
    proof_public = proof_key.as_dict(is_private=False)
    jwt = JsonWebToken(["ES256"])
    store = SQLiteRuntimeStore(tmp_path)
    store.initialize()
    auth = {
        "audience": "ccr-api",
        "issuer": "https://issuer.example",
        "jwks": {"keys": [issuer_key.as_dict(is_private=False)]},
    }
    client = TestClient(create_app(root=tmp_path, store=store, auth_config=auth))

    def request(path: str, body: dict[str, Any], subject: str) -> Any:
        now = int(time.time())
        credential = jwt.encode(
            {"alg": "ES256", "kid": "issuer"},
            {
                "aud": "ccr-api",
                "iss": auth["issuer"],
                "sub": subject,
                "iat": now,
                "exp": now + 300,
                "cnf": {"jkt": _jwk_thumbprint(proof_public)},
            },
            issuer_key,
        ).decode()
        ath = (
            base64.urlsafe_b64encode(hashlib.sha256(credential.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        proof = jwt.encode(
            {"alg": "ES256", "typ": "dpop+jwt", "jwk": proof_public},
            {
                "ath": ath,
                "htm": "POST",
                "htu": "http://testserver" + path,
                "iat": now,
                "jti": uuid4().hex,
            },
            proof_key,
        ).decode()
        return client.post(
            path, json=body, headers={"authorization": "DPoP " + credential, "dpop": proof}
        )

    key, raw = config()
    created = request(
        "/v1/optimizer", {"mission": "mission:source", "config": raw}, "human:operator"
    )
    assert created.status_code == 200, created.text
    run_id = created.json()["run_id"]
    for _ in range(4):
        trial = request(f"/v1/optimizer/{run_id}/step", {"apply": True}, "human:operator").json()[
            "trial"
        ]
        claimed = request(
            f"/v1/optimizer/{run_id}/claim",
            {"trial_id": trial["trial_id"], "worker": "forged"},
            "worker:actual",
        )
        assert claimed.status_code == 200
        envelope = observation(ControlStore(tmp_path, ""), run_id, trial["trial_id"], key)
        assert envelope["worker_id"] == "worker:actual"
        assert request(f"/v1/optimizer/{run_id}/ingest", envelope, "worker:actual").json()["ok"]
    assert request(f"/v1/optimizer/{run_id}/freeze", {}, "worker:actual").status_code == 401
    assert request(f"/v1/optimizer/{run_id}/freeze", {}, "human:operator").json()["ok"]


@pytest.mark.skipif(not os.getenv("CCR_TEST_POSTGRES_URL"), reason="disposable PostgreSQL required")
def test_postgres_growth_concurrent_quota_and_outcomes(tmp_path: Path) -> None:
    key, raw = config()
    store = ControlStore(tmp_path, os.environ["CCR_TEST_POSTGRES_URL"])
    run_id = engine.initialize(store, mission="mission:source", config=raw)["run_id"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: engine.step(store, run_id, apply=True, expected_revision=0), range(8)
            )
        )
    assert sum(r.get("mutated_runtime", False) for r in results) == 1
    trial = engine.load(store, run_id)["trials"][0]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: engine.ingest(store, run_id, envelope), range(8)))
    assert sum(r.get("mutated_runtime", False) for r in results) == 1
    for _ in range(3):
        finish(store, run_id, key)
    assert engine.report(store, run_id)["ledgers"]["training"]["observed_service"] == {
        "task": 4,
        "research": 4,
    }
    other = copy.deepcopy(raw)
    other["growth"]["study_id"] += ":other"
    with pytest.raises(ValueError, match="quota"):
        engine.initialize(store, mission="mission:source", config=other)
