# SPDX-License-Identifier: Apache-2.0
"""Source completeness and selected false-acceptance faults in native accounting."""

from __future__ import annotations

import copy
import importlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from ccr.optimizer import engine, native_accounting
from ccr.optimizer.growth_example import observation, sign
from ccr.optimizer.growth_runtime import lifecycle
from tests.test_growth import config, finish, start
from tests.test_native_interchange import native


def history(tmp_path: Path) -> tuple[Any, str, Any]:
    key, raw = config()
    for asset in raw["growth"]["assets"].values():
        asset["expires_at"] = (
            (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0).isoformat()
        )
    store, run_id = start(tmp_path, raw)
    for _ in range(4):
        finish(store, run_id, key)
    return store, run_id, key


@native
def test_cait_detects_selected_false_native_acceptance_faults(
    tmp_path: Path, monkeypatch: Any
) -> None:
    store, run_id, _ = history(tmp_path)
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    source = importlib.import_module("cait_schema.accounting.source")
    reports = importlib.import_module("cait_schema.accounting.report")
    checker = importlib.import_module("cait_schema.accounting.checker")
    prepared = source.prepare(exported["bundle"])
    report = reports.analyze(exported["bundle"])
    assert native_accounting.check_feedback(run, exported, report, store.now())["complete"]
    for key, value in (
        ("revision", run["revision"] + 1),
        ("ccr_sources", []),
        ("clock_origin", "2000-01-01T00:00:00Z"),
    ):
        altered = copy.deepcopy(exported)
        altered[key] = value
        with pytest.raises(ValueError, match="source history"):
            native_accounting.check_feedback(run, altered, report, store.now())
    native_result = checker.check_report(exported["bundle"], report)
    monkeypatch.setattr(checker, "check_report", lambda *_: native_result)
    for fault in (
        "missing-creation",
        "missing-service",
        "missing-cost",
        "duplicate",
        "wrong-scope",
        "unbound",
        "clock",
        "cost",
        "stock",
        "origin",
        "receiver",
        "coordinate",
        "unknown-kind",
    ):
        changed = copy.deepcopy(prepared)
        if fault.startswith("missing-"):
            kind = {"missing-creation": "create", "missing-service": "use", "missing-cost": "cost"}[
                fault
            ]
            changed.events[:] = [e for e in changed.events if e["kind"] != kind]
        elif fault == "duplicate":
            changed.events.append(copy.deepcopy(changed.events[0]))
        elif fault == "wrong-scope":
            changed.contract["arms"] = ["holdout"]
        elif fault == "unbound":
            changed.events[0]["id"] = "invented"
        elif fault == "clock":
            changed.events[0]["recorded"] += 1
        elif fault == "cost":
            next(e for e in changed.events if e["kind"] == "cost")["data"]["quantity"][
                "declared"
            ] = "999"
        elif fault in {"stock", "origin"}:
            event = next(e for e in changed.events if e["kind"] == "create")
            if fault == "stock":
                event["data"]["artifact"] = "0" * 64
            else:
                event["data"]["shares"] = {"endogenous": "1", "external": "0", "unresolved": "0"}
        elif fault in {"receiver", "coordinate"}:
            next(e for e in changed.events if e["kind"] == "use")["data"][fault] = "substituted"
        else:
            changed.events[0]["kind"] = "invented"
        monkeypatch.setattr(source, "prepare", lambda _, value=changed: value)
        with pytest.raises(ValueError):
            native_accounting.check_feedback(run, exported, report, store.now())
    monkeypatch.setattr(source, "prepare", lambda _: prepared)
    for field in ("costs", "closing", "service"):
        altered = copy.deepcopy(report)
        if field == "costs":
            altered["balances"][0]["costs"]["effort_unit"] = "999"
        else:
            next(
                b
                for b in altered["balances"]
                if b["coordinate"] == ("assets" if field == "closing" else "task")
            )[field] = "999"
        with pytest.raises(ValueError, match="totals"):
            native_accounting.check_feedback(run, exported, altered, store.now())
    assert engine.load(store, run_id) == run


@native
def test_cait_export_refuses_empty_history_and_preserves_partial_work(tmp_path: Path) -> None:
    key, raw = config()
    store, run_id = start(tmp_path, raw)
    with pytest.raises(ValueError, match="original signed"):
        native_accounting.export(engine.load(store, run_id), store.now())
    finish(store, run_id, key, success=False)
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    reports = importlib.import_module("cait_schema.accounting.report")
    report = reports.analyze(exported["bundle"])
    checked = native_accounting.check_feedback(run, exported, report, store.now())
    assert not checked["complete"] and checked["remaining_obligations"]
    assert checked["reward_added"] == checked["asset_stock_added"] == 0


@native
def test_cait_source_clock_and_scoped_lifecycle_limits(tmp_path: Path) -> None:
    store, run_id, key = history(tmp_path)
    run = engine.load(store, run_id)
    with pytest.raises(ValueError, match="clock bounds"):
        native_accounting.export(run, "2000-01-01T00:00:00Z")
    oversized = copy.deepcopy(run)
    actions = oversized["config"]["growth"]["actions"]
    for i in range(17):
        actions["extra" + str(i)] = copy.deepcopy(actions["greedy"])
    with pytest.raises(ValueError, match="mapping bound"):
        native_accounting.export(oversized, store.now())
    asset = next(iter(run["config"]["growth"]["assets"]))
    lifecycle(
        store,
        run_id,
        sign(
            key,
            {
                "event_id": "quarantine-for-review",
                "run_id": run_id,
                "config_digest": run["config"]["config_digest"],
                "asset": asset,
                "state": "quarantined",
                "reason": "unsupported native lifecycle remains partial",
                "observed_at": store.now(),
                "verifier_id": "reviewer",
                "worker_id": "producer",
            },
        ),
    )
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    checked = native_accounting.check_feedback(run, exported, report, store.now())
    assert not checked["complete"] and checked["invalidated_assets"] == [asset]
    assert checked["remaining_obligations"][0].startswith("unsupported-lifecycle:")


@native
def test_cait_missing_creation_is_partial(tmp_path: Path) -> None:
    key, raw = config()
    raw["growth"]["actions"]["form"]["verification_work"]["review"] = 100
    store, run_id = start(tmp_path, raw)
    assert engine.plan(store, run_id)["chosen"]["immediate_step"] == "greedy"
    finish(store, run_id, key)
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    checked = native_accounting.check_feedback(run, exported, report, store.now())
    assert not checked["complete"]
    assert checked["remaining_obligations"][0].startswith("missing-creation:")


@native
def test_cait_inconclusive_pending_and_feedback_bounds(tmp_path: Path) -> None:
    key, raw = config()
    for asset in raw["growth"]["assets"].values():
        asset["expires_at"] = (
            (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(microsecond=0).isoformat()
        )
    store, run_id = start(tmp_path, raw)
    finish(store, run_id, key)
    finish(store, run_id, key)
    trial = engine.step(store, run_id, apply=True)["trial"]
    engine.claim(store, run_id, trial["trial_id"], worker="producer")
    envelope = observation(store, run_id, trial["trial_id"], key, success=False)
    envelope["observation"]["status"] = "inconclusive"
    engine.ingest(
        store, run_id, sign(key, {k: v for k, v in envelope.items() if k != "signature_base64"})
    )
    engine.step(store, run_id, apply=True)
    run = engine.load(store, run_id)
    exported = native_accounting.export(run, store.now())
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    checked = native_accounting.check_feedback(run, exported, report, store.now())
    assert not checked["complete"] and "unfinished-CCR-work" in checked["remaining_obligations"]
    assert any(x.startswith("unsupported-use-status:") for x in checked["remaining_obligations"])
    with pytest.raises(ValueError, match="stale"):
        native_accounting.reconcile(
            store, run_id, exported, report, expected_revision=run["revision"] + 1
        )
    with engine.edit_run(store, run_id) as (edited, _):
        edited["frozen_policy"] = {"selected_fault": True}
    with pytest.raises(ValueError, match="frozen"):
        native_accounting.reconcile(
            store, run_id, exported, report, expected_revision=run["revision"]
        )
    with engine.edit_run(store, run_id) as (edited, _):
        edited["frozen_policy"] = None
        edited["native_feedback"] = {str(i): {} for i in range(64)}
    with pytest.raises(ValueError, match="bound reached"):
        native_accounting.reconcile(
            store, run_id, exported, report, expected_revision=run["revision"]
        )
