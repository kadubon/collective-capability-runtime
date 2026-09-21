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
        ("bindings", {}),
        ("units", {"x": {"target": "cost", "rate": "1", "rounding": "lower"}}),
        ("units", {"x": {"target": "other", "rate": "1", "rounding": "exact"}}),
    ]
    for key, value in mutations:
        altered = copy.deepcopy(registration)
        altered[key] = value
        with pytest.raises(ValueError):
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
