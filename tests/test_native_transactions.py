# SPDX-License-Identifier: Apache-2.0
"""Native admission contention and selected fault tests on authoritative stores."""

from __future__ import annotations

import copy
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from ccr.ids import sha256_json
from ccr.optimizer import engine, native_projection, native_runtime
from ccr.optimizer.native_projection_check import registration_check
from ccr.storage.control import ControlStore
from tests.test_native_interchange import native, setup_run


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
@native
def test_native_authoritative_admission_and_apply_contention(tmp_path: Path, backend: str) -> None:
    url = os.getenv("CCR_TEST_POSTGRES_URL", "") if backend == "postgres" else ""
    if backend == "postgres" and not url:
        pytest.skip("requires real PostgreSQL")
    _, store, run_id, raw, registration = setup_run(tmp_path, database_url=url)
    projection = native_projection.project(raw, registration)
    staged = native_runtime.stage(
        store, run_id, raw, projection, expected_revision=1, idempotency_key="source"
    )

    def admit(index: int) -> dict[str, Any]:
        remote = ControlStore(tmp_path / str(index), url) if url else ControlStore(tmp_path, "")
        return native_runtime.admit(remote, run_id, staged["proposal_id"], expected_revision=2)

    with ThreadPoolExecutor(max_workers=4) as workers:
        admitted = list(workers.map(admit, range(4)))
    assert sum(bool(row.get("mutated_runtime")) for row in admitted) == 1
    assert sum(bool(row.get("idempotent")) for row in admitted) == 3
    run = engine.load(store, run_id)
    assert run["revision"] == 3 and len(run["native_admitted"]) == 1
    assert sum(row["kind"] == "native_admission" for row in run["growth_events"]) == 1

    def apply(index: int) -> dict[str, Any]:
        remote = ControlStore(tmp_path / str(index), url) if url else ControlStore(tmp_path, "")
        return engine.step(remote, run_id, apply=True, expected_revision=3)

    with ThreadPoolExecutor(max_workers=4) as workers:
        applied = list(workers.map(apply, range(4)))
    assert sum(bool(row.get("trial")) for row in applied) == 1
    restored = ControlStore(tmp_path / "restarted", url) if url else ControlStore(tmp_path, "")
    run = engine.load(restored, run_id)
    assert len(run["trials"]) == 1 and run["growth_reservation"] is not None
    assert not run.get("native_feedback")


@native
def test_native_selected_transaction_faults(tmp_path: Path, monkeypatch: Any) -> None:
    _, store, run_id, raw, registration = setup_run(tmp_path)
    assert native_runtime.register(store, run_id, registration, expected_revision=0)["idempotent"]
    modified = copy.deepcopy(registration)
    modified["arm"] = "baseline"
    with pytest.raises(ValueError, match="stale"):
        native_runtime.register(store, run_id, modified, expected_revision=0)
    with pytest.raises(ValueError, match="immutable"):
        native_runtime.register(store, run_id, modified, expected_revision=1)
    projected = native_projection.project(raw, registration)
    before = engine.load(store, run_id)
    with pytest.raises(ValueError, match="stale"):
        native_runtime.stage(
            store, run_id, raw, projected, expected_revision=0, idempotency_key="stale"
        )
    assert engine.load(store, run_id) == before

    original_append = native_runtime.growth_ledger.append

    def crash(*args: Any, **kwargs: Any) -> None:
        original_append(*args, **kwargs)
        raise RuntimeError("selected fault after native journal append")

    with monkeypatch.context() as patch:
        patch.setattr(native_runtime.growth_ledger, "append", crash)
        with pytest.raises(RuntimeError, match="selected fault"):
            native_runtime.stage(
                store, run_id, raw, projected, expected_revision=1, idempotency_key="crash"
            )
    assert engine.load(store, run_id) == before
    staged = native_runtime.stage(
        store, run_id, raw, projected, expected_revision=1, idempotency_key="retry"
    )
    before = engine.load(store, run_id)
    with monkeypatch.context() as patch:
        patch.setattr(native_runtime.growth_ledger, "append", crash)
        with pytest.raises(RuntimeError, match="selected fault"):
            native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    assert engine.load(store, run_id) == before
    with pytest.raises(ValueError, match="stale"):
        native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=1)
    with pytest.raises(ValueError, match="explicitly staged"):
        native_runtime.admit(store, run_id, "0" * 64, expected_revision=2)
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    run = engine.load(store, run_id)
    assert native_runtime.blockers(run, "form", store.now(), "baseline")
    assert native_runtime.blockers(run, "greedy", store.now(), "training") == []
    for fault in ("source", "registration", "journal", "missing"):
        altered = copy.deepcopy(run)
        if fault == "source":
            altered["native_staged"]["retry"]["raw"] += " "
        elif fault == "registration":
            altered["native_registration"]["study_id"] += "changed"
        elif fault == "journal":
            altered["growth_events"] = [
                r for r in altered["growth_events"] if r["kind"] != "native_admission"
            ]
        else:
            altered["native_staged"] = {}
        assert native_runtime.blockers(altered, "form", store.now(), "training")
    assert engine.load(store, run_id) == run


@native
def test_registration_and_projection_negative_controls(tmp_path: Path) -> None:
    from ccr.optimizer.native_projection_check import check

    _, store, run_id, raw, registration = setup_run(tmp_path)
    run = engine.load(store, run_id)
    mutations = [
        ("arm", "baseline"),
        ("study_id", "other"),
        ("pool_id", "other"),
        ("pools", {"alias": "unregistered"}),
        ("clocks", {}),
        ("bindings", {}),
        ("units", {"x": {"target": "cost", "rate": "1", "rounding": "lower"}}),
        ("units", {"x": {"target": "other", "rate": "1", "rounding": "exact"}}),
    ]
    for key, value in mutations:
        altered = copy.deepcopy(registration)
        altered[key] = value
        with pytest.raises(ValueError):
            registration_check(run, altered)
    altered = copy.deepcopy(registration)
    altered["bindings"]["greedy"] = copy.deepcopy(altered["bindings"]["form"])
    with pytest.raises(ValueError, match="ambiguous"):
        registration_check(run, altered)
    for field, value in (("target_sha256", "0" * 64), ("host_verifier", "untrusted")):
        altered = copy.deepcopy(registration)
        altered["bindings"]["form"]["scope"][field] = value
        with pytest.raises(ValueError, match="scope is not registered"):
            registration_check(run, altered)
    altered = copy.deepcopy(registration)
    altered["bindings"]["form"]["producer"] = "alt"
    with pytest.raises(ValueError, match="scope on another producer"):
        registration_check(run, altered)
    for key, value in [
        ("producer", "unknown"),
        ("action_sha256", "0" * 64),
        ("valid_until", "2019-01-01T00:00:00Z"),
        ("source_action", ""),
        ("observations", {}),
        ("observations", {"hidden_model": "red"}),
    ]:
        altered = copy.deepcopy(registration)
        altered["bindings"]["form"][key] = value
        with pytest.raises(ValueError):
            registration_check(run, altered)
    projected = native_projection.project(raw, registration)
    for key, value in [
        ("service_credit", True),
        ("observed_capacity", 1),
        ("settled", True),
        ("bindings", []),
        ("source_sha256", "0" * 64),
        ("native_checker", {}),
    ]:
        altered = copy.deepcopy(projected)
        altered[key] = value
        with pytest.raises(ValueError):
            check(run, raw, altered)
    assert sha256_json(engine.load(store, run_id)) == sha256_json(run)


@native
def test_native_expiry_freeze_delivery_and_changed_check(tmp_path: Path, monkeypatch: Any) -> None:
    _, store, run_id, raw, registration = setup_run(tmp_path)
    projected = native_projection.project(raw, registration)
    staged = native_runtime.stage(
        store, run_id, raw, projected, expected_revision=1, idempotency_key="first"
    )
    assert native_runtime.stage(
        store, run_id, raw, projected, expected_revision=1, idempotency_key="first"
    )["idempotent"]
    changed_raw = raw + b" "
    changed_projection = native_projection.project(changed_raw, registration)
    with pytest.raises(ValueError, match="conflicting"):
        native_runtime.stage(
            store,
            run_id,
            changed_raw,
            changed_projection,
            expected_revision=2,
            idempotency_key="first",
        )
    original_edit = engine.edit_run

    @contextmanager
    def expired(*args: Any, **kwargs: Any) -> Any:
        with original_edit(*args, **kwargs) as (run, _):
            yield run, "2100-01-01T00:00:00Z"

    with monkeypatch.context() as patch:
        patch.setattr(engine, "edit_run", expired)
        with pytest.raises(ValueError, match="expired"):
            native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    with engine.edit_run(store, run_id) as (run, _):
        run["frozen_policy"] = {"selected_fault": True}
    with pytest.raises(ValueError, match="frozen"):
        native_runtime.stage(
            store,
            run_id,
            changed_raw,
            changed_projection,
            expected_revision=2,
            idempotency_key="new",
        )
    with pytest.raises(ValueError, match="frozen"):
        native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    with engine.edit_run(store, run_id) as (run, _):
        run["frozen_policy"] = None
    original_check = native_runtime.check

    def faulty_check(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {**original_check(*args, **kwargs), "selected_fault": True}

    with monkeypatch.context() as patch:
        patch.setattr(native_runtime, "check", faulty_check)
        with pytest.raises(ValueError, match="checker binding changed"):
            native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    trial = engine.step(store, run_id, apply=True, expected_revision=3)["trial"]
    with monkeypatch.context() as patch:
        patch.setattr(engine, "edit_run", expired)
        assert not engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    assert engine.load(store, run_id)["trials"][0]["state"] == "queued"


@native
@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_native_cleanup_cannot_cross_expiry_after_reservation(
    tmp_path: Path, monkeypatch: Any, backend: str
) -> None:
    from datetime import timedelta

    from ccr.optimizer import growth_checker
    from ccr.optimizer.model import timestamp

    url = os.getenv("CCR_TEST_POSTGRES_URL", "") if backend == "postgres" else ""
    if backend == "postgres" and not url:
        pytest.skip("requires real PostgreSQL")
    _, store, run_id, raw, registration = setup_run(tmp_path, database_url=url)
    projection = native_projection.project(raw, registration)
    snapshot = engine.load(store, run_id)
    action = snapshot["config"]["growth"]["actions"]["form"]
    cutoff = timestamp(registration["bindings"]["form"]["valid_until"])
    current = (
        cutoff - timedelta(seconds=action["duration_seconds"] + action["cleanup_seconds"])
    ).isoformat()
    original_edit = engine.edit_run

    @contextmanager
    def at_cutoff(*args: Any, **kwargs: Any) -> Any:
        with original_edit(*args, **kwargs) as (run, _):
            yield run, current

    # The exclusive native validity endpoint includes cleanup. Being valid at
    # dispatch is insufficient when the conservative end reaches that endpoint.
    with monkeypatch.context() as patch:
        patch.setattr(engine, "edit_run", at_cutoff)
        with pytest.raises(ValueError, match="ends after validity"):
            native_runtime.stage(
                store, run_id, raw, projection, expected_revision=1, idempotency_key="too-late"
            )
    assert engine.load(store, run_id) == snapshot
    staged = native_runtime.stage(
        store, run_id, raw, projection, expected_revision=1, idempotency_key="source"
    )
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    proposal = engine.plan(store, run_id)
    assert growth_checker.check(engine.load(store, run_id), proposal, current)["ok"] is False
    trial = engine.step(store, run_id, apply=True, expected_revision=3)["trial"]
    reserved = engine.load(store, run_id)
    with monkeypatch.context() as patch:
        patch.setattr(engine, "edit_run", at_cutoff)
        rejected = engine.claim(store, run_id, trial["trial_id"], worker="producer")
    assert rejected["ok"] is False and "native_source_expired" in rejected["blockers"]
    assert engine.load(store, run_id) == reserved
    assert reserved["growth_reservation"] is not None


@native
@pytest.mark.parametrize("late_event", [False, True])
def test_native_result_expiry_keeps_costs_and_cannot_be_promoted_on_replay(
    tmp_path: Path, monkeypatch: Any, late_event: bool
) -> None:
    from datetime import datetime, timedelta, timezone

    from ccr.optimizer import growth_ledger
    from ccr.optimizer.growth_example import observation, sign

    cutoff = (datetime.now(timezone.utc) + timedelta(minutes=2)).replace(microsecond=0).isoformat()
    key, store, run_id, raw, registration = setup_run(tmp_path, valid_until=cutoff)
    projected = native_projection.project(raw, registration)
    staged = native_runtime.stage(
        store, run_id, raw, projected, expected_revision=1, idempotency_key="source"
    )
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    trial = engine.step(store, run_id, apply=True)["trial"]
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    envelope = observation(store, run_id, trial["trial_id"], key)
    if late_event:
        result = {k: v for k, v in envelope["result"].items() if k != "signature_base64"}
        result["observed_at"] = cutoff
        envelope["result"] = sign(key, result)
        envelope = sign(key, {k: v for k, v in envelope.items() if k != "signature_base64"})
    original_edit = engine.edit_run

    @contextmanager
    def delayed(*args: Any, **kwargs: Any) -> Any:
        with original_edit(*args, **kwargs) as (run, _):
            yield run, cutoff

    with monkeypatch.context() as patch:
        patch.setattr(engine, "edit_run", delayed)
        result = engine.ingest(store, run_id, envelope)
    assert result["reward"] == 0
    run = engine.load(store, run_id)
    ledger = growth_ledger.replay(run, cutoff)
    assert ledger["actual_costs"] == {"cost": 2}
    assert ledger["asset_count"] == 0
    outcome = next(e for e in run["growth_events"] if e["kind"] == "outcome")
    assert not outcome["payload"]["qualified"]
    assert "native_result_outside_validity" in outcome["payload"]["reasons"]
    # Rehashing local derived journal flags cannot promote the unchanged signed
    # observation into eligibility. The replay rechecks its historical times.
    forged = copy.deepcopy(run)
    previous = None
    for event in forged["growth_events"]:
        if event["kind"] == "outcome":
            event["payload"].update(qualified=True, success=True, reasons=[])
        event["previous"] = previous
        event["digest"] = sha256_json({k: v for k, v in event.items() if k != "digest"})
        previous = event["digest"]
    with pytest.raises(ValueError, match="native result outside validity"):
        growth_ledger.replay(forged, cutoff)
    assert native_runtime.result_time_blockers(run, "greedy", cutoff, cutoff) == []


@native
@pytest.mark.parametrize("late", [False, True])
def test_source_clock_controls_admission_lease_and_result(
    tmp_path: Path, monkeypatch: Any, late: bool
) -> None:
    from ccr.optimizer.growth_example import observation
    from ccr.optimizer.native_projection_check import check

    origin = "2090-01-01T00:00:00Z"
    clock = {"utc_origin": origin, "tick_origin": "0", "seconds_per_tick": "1"}
    key, store, run_id, raw, registration = setup_run(tmp_path, clock=clock)
    changed = copy.deepcopy(registration)
    changed["clocks"] = {"0" * 64: clock}
    with pytest.raises(ValueError, match="no registered source"):
        registration_check(engine.load(store, run_id), changed)
    projected = native_projection.project(raw, registration)
    checked = check(engine.load(store, run_id), raw, projected)
    assert checked["envelopes"]["form"]["clock_window"]["end"] == "2090-01-01T00:00:05+00:00"
    before = engine.load(store, run_id)
    with pytest.raises(ValueError, match="future-dated"):
        native_runtime.stage(
            store, run_id, raw, projected, expected_revision=1, idempotency_key="future"
        )
    assert engine.load(store, run_id) == before
    current = origin
    original_edit = engine.edit_run

    @contextmanager
    def controlled(*args: Any, **kwargs: Any) -> Any:
        with original_edit(*args, **kwargs) as (run, _):
            yield run, current

    monkeypatch.setattr(engine, "edit_run", controlled)
    monkeypatch.setattr(ControlStore, "now", lambda _: current)
    staged = native_runtime.stage(
        store, run_id, raw, projected, expected_revision=1, idempotency_key="clock"
    )
    current = "2090-01-01T00:00:05Z"
    with pytest.raises(ValueError, match="expired"):
        native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    assert not engine.load(store, run_id)["native_admitted"]
    current = origin
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    assert (
        native_runtime.result_time_blockers(engine.load(store, run_id), "form", origin, origin)
        == []
    )
    trial = engine.step(store, run_id, apply=True)["trial"]
    current = "2090-01-01T00:00:03Z"
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["blockers"] == [
        "native_source_clock_window"
    ]
    assert engine.load(store, run_id)["growth_reservation"] is not None
    current = origin
    assert engine.claim(store, run_id, trial["trial_id"], worker="producer")["ok"]
    envelope = observation(store, run_id, trial["trial_id"], key)
    current = "2090-01-01T00:00:06Z" if late else "2090-01-01T00:00:02Z"
    result = engine.ingest(store, run_id, envelope)
    assert ("native_result_outside_source_clock" in result["blockers"]) == late
    assert result["reward"] == 0
    ledger = native_runtime.growth_ledger.replay(engine.load(store, run_id), current)
    assert ledger["actual_costs"] == {"cost": 2} and ledger["asset_count"] == (0 if late else 1)


@native
def test_registered_execution_must_fit_native_clock_interval(tmp_path: Path) -> None:
    from ccr.optimizer.native_projection_check import check

    clock = {"utc_origin": "2090-01-01T00:00:00Z", "tick_origin": "0", "seconds_per_tick": "1"}
    _, store, run_id, source, registration = setup_run(tmp_path, clock=clock, duration=5)
    with pytest.raises(ValueError, match="cannot fund execution and cleanup"):
        check(engine.load(store, run_id), source, native_projection.project(source, registration))


@native
def test_cpcf_result_requires_the_registered_check_scope(tmp_path: Path) -> None:
    from ccr.optimizer.growth_example import observation, sign

    key, store, run_id, raw, registration = setup_run(tmp_path, extra_verifier=True)
    staged = native_runtime.stage(
        store,
        run_id,
        raw,
        native_projection.project(raw, registration),
        expected_revision=1,
        idempotency_key="source",
    )
    native_runtime.admit(store, run_id, staged["proposal_id"], expected_revision=2)
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key)
    inner = {k: v for k, v in envelope["result"].items() if k != "signature_base64"}
    inner["verifier_id"] = "other-reviewer"
    envelope["result"] = sign(key, inner)
    envelope["verifier_id"] = "other-reviewer"
    envelope = sign(key, {k: v for k, v in envelope.items() if k != "signature_base64"})
    result = engine.ingest(store, run_id, envelope)
    assert "native_check_scope_mismatch" in result["blockers"]
    ledger = native_runtime.growth_ledger.replay(engine.load(store, run_id), store.now())
    assert ledger["asset_count"] == 0 and ledger["actual_costs"] == {"cost": 2}
    forged = engine.load(store, run_id)
    previous = None
    for event in forged["growth_events"]:
        if event["kind"] == "outcome":
            event["payload"].update(qualified=True, success=True, reasons=[])
        event["previous"] = previous
        event["digest"] = sha256_json({k: v for k, v in event.items() if k != "digest"})
        previous = event["digest"]
    with pytest.raises(ValueError, match="another native verifier"):
        native_runtime.growth_ledger.replay(forged, store.now())


@pytest.mark.parametrize(
    "observed,received,accepted", [(0, 2, True), (1, 2, True), (2, 2, False), (1, 3, False)]
)
def test_execution_endpoint_is_distinct_from_cleanup_endpoint(
    observed: int, received: int, accepted: bool
) -> None:
    # Independent interval oracle: execute in [0,1], receipt/cleanup through 2.
    # The extra cleanup second is not an extension of the source execution slot.
    def instant(seconds: int) -> str:
        return f"2090-01-01T00:00:0{seconds}Z"

    interval = {"start": instant(0), "execution_end": instant(1), "end": instant(2)}
    run = {
        "native_registration": {
            "bindings": {
                "work": {
                    "valid_from": instant(0),
                    "valid_until": instant(9),
                    "contract_sha256": "source",
                }
            },
            "clocks": {"source": {}},
        },
        "native_admitted": {"proposal": {"actions": ["work"], "admitted_at": instant(0)}},
        "native_staged": {
            "delivery": {
                "identity": "proposal",
                "check": {"envelopes": {"work": {"clock_window": interval}}},
            }
        },
    }
    blockers = native_runtime.result_time_blockers(
        run, "work", instant(observed), instant(received)
    )
    assert (blockers == []) is accepted
