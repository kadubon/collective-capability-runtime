# SPDX-License-Identifier: Apache-2.0
"""Selected faults in the native-check boundary, checked by independent CCR logic.

These deliberately corrupt an already native-checked document in memory. They
are not represented as native conformance or exhaustive mutation qualification.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from ccr.ids import sha256_json
from ccr.optimizer import (
    engine,
    native_checks,
    native_projection,
    native_projection_check,
    native_runtime,
)
from ccr.optimizer.native_example import alt_profile, vek_single_work
from tests.test_growth import config, start
from tests.test_native_interchange import native, setup_run


def registered(
    tmp_path: Path, producer: str, *, clocked: bool = False
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    if producer == "cpcf":
        _, store, run_id, source, registration = setup_run(tmp_path)
        return engine.load(store, run_id), source, registration
    _, raw = config()
    if producer == "alt":
        raw, source, names = alt_profile(raw)
        units = {"resource": {"target": "cost", "rate": "1", "rounding": "exact"}}
    else:
        source = vek_single_work()
        documents = native_checks.inspect(source)["documents"]
        source_action = next(iter(documents["plan"]["schedule"]))
        work_id = next(
            a["work_id"]
            for a in documents["contract"]["actions"]
            if a["action_id"] == source_action
        )
        work = next(w for w in documents["contract"]["work"] if w["work_id"] == work_id)
        names = {source_action: "greedy"}
        action = raw["growth"]["actions"]["greedy"]
        action.update(kind="diagnostic", gains={"task": 0, "research": 0})
        for arm in raw["base"]["interventions"]:
            if arm["intervention_id"] == "greedy":
                arm["kind"] = "measurement"
        for target in raw["base"]["task_manifest"]:
            if target["target_id"] == action["target_id"]:
                target["input_sha256"] = work["input_digest"]
        for action in raw["growth"]["actions"].values():
            action["capacity"] = {"reviewer": 1}
        raw["growth"]["quota"]["capacity"] = raw["growth"]["quota"]["pool_capacity"] = {
            "reviewer": 1
        }
        units = {"check-work": {"target": "cost", "rate": "1", "rounding": "exact"}}
    if producer == "alt":
        from ccr.optimizer.native_example import serial_alt_source

        source = serial_alt_source(source)
    for name in names.values():
        raw["growth"]["actions"][name].update(
            duration_seconds=1 if producer == "alt" else 2, cleanup_seconds=1
        )
    store, run_id = start(tmp_path, raw)
    run = engine.load(store, run_id)
    inspected = native_checks.check(source)
    registration = {
        "schema_version": "ccr.native_registration.v1",
        "run_id": run_id,
        "config_digest": run["config"]["config_digest"],
        "study_id": raw["growth"]["study_id"],
        "arm": "training",
        "pool_id": raw["growth"]["quota"]["pool_id"],
        "units": units,
        "pools": {"verifier": "worker"} if producer == "alt" else {"reviewer-alias": "reviewer"},
        "bindings": {
            name: {
                "producer": producer,
                "source_action": original,
                "contract_sha256": inspected["document_sha256"]["contract"],
                "action_sha256": sha256_json(raw["growth"]["actions"][name]),
                "valid_from": "2020-01-01T00:00:00Z",
                "valid_until": raw["growth"]["window_end"],
            }
            for original, name in names.items()
        },
    }
    registration["clocks"] = {
        inspected["document_sha256"]["contract"]: {
            "utc_origin": "2090-01-01T00:00:00Z" if clocked else store.now(),
            "tick_origin": "3" if producer == "alt" else "0",
            "seconds_per_tick": "1" if producer == "alt" else "2",
        }
    }
    native_runtime.register(store, run_id, registration, expected_revision=0)
    return engine.load(store, run_id), source, registration


@native
@pytest.mark.parametrize("producer", ["alt", "vek", "cpcf"])
def test_independent_checker_rejects_selected_native_boundary_faults(
    tmp_path: Path, monkeypatch: Any, producer: str
) -> None:
    run, raw, registration = registered(tmp_path, producer)
    original = native_checks.check(raw)
    projected = native_projection.project(raw, registration)
    assert native_projection_check.check(run, raw, projected)["ok"]
    cases = []
    documents = original["documents"]

    def mutation(path: tuple[Any, ...], value: Any) -> None:
        changed = copy.deepcopy(original)
        cursor = changed["documents"]
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        cases.append(changed)

    if producer == "alt":
        options = documents["contract"]["options"]
        selected = documents["plan"]["selected"]
        first = next(i for i, option in enumerate(options) if option["id"] == selected[0])
        mutation(("contract", "sunk_cost_ids"), ["unbound"])
        mutation(("contract", "options", first, "kind"), "refresh")
        mutation(("contract", "options", first, "kind"), "scratch")
        mutation(("contract", "options", first, "end"), 1000)
        mutation(("contract", "qualifications", 0, "offer", "mission"), "substituted")
        mutation(("contract", "qualifications", 0, "offer", "context"), {"other": True})
        mutation(("contract", "qualifications", 0, "offer", "quality"), "substituted")
        mutation(("contract", "qualifications", 0, "candidate", "dependencies"), ["unmapped"])
        cost_id = options[first]["costs"][0]
        cost_index = next(
            i for i, c in enumerate(documents["contract"]["costs"]) if c["id"] == cost_id
        )
        mutation(("contract", "costs", cost_index, "amount"), "999")
        mutation(("contract", "costs", cost_index, "unit"), "unregistered")
        mutation(("contract", "options", first, "costs"), [cost_id, cost_id])
        occupied = next(i for i, o in enumerate(options) if o["id"] in selected and o["occupancy"])
        mutation(("contract", "options", occupied, "occupancy", 0, "quantity"), 2)
        mutation(("contract", "options", occupied, "occupancy", 0, "resource"), "unmapped")
    elif producer == "vek":
        action_id = next(iter(documents["plan"]["schedule"]))
        index = next(
            i for i, a in enumerate(documents["contract"]["actions"]) if a["action_id"] == action_id
        )
        work_id = documents["contract"]["actions"][index]["work_id"]
        work = next(
            i for i, w in enumerate(documents["contract"]["work"]) if w["work_id"] == work_id
        )
        mutation(("contract", "work", work, "input_digest"), "0" * 64)
        mutation(("contract", "work", work, "deadline"), 0)
        mutation(("contract", "work", work, "predecessors"), ["unmapped"])
        mutation(("contract", "actions", index, "requires_negative"), ["unmapped"])
        mutation(("contract", "actions", index, "costs"), [2, 1])
        mutation(("contract", "actions", index, "duration"), 100)
        changed = copy.deepcopy(original)
        changed["documents"]["contract"]["resources"].append(
            {"resource_id": "reviewer-alias", "kind": "pool", "unit": "work", "capacity": [1] * 16}
        )
        for action in changed["documents"]["contract"]["actions"]:
            action["costs"].append(1)
        cases.append(changed)
    else:
        row = next(
            i
            for i, a in enumerate(documents["contract"]["spec"]["action_catalogue"])
            if documents["objects"][a["action_digest"]]["spec"]["action_id"] == "prepare"
        )
        action_digest = documents["contract"]["spec"]["action_catalogue"][row]["action_digest"]
        capability_digest = documents["objects"][action_digest]["spec"]["capability_digest"]
        mutation(
            ("objects", capability_digest, "spec", "verifier_principal_id"), "substituted-verifier"
        )
        mutation(("objects", action_digest, "spec", "required_object_digests"), ["unmapped"])
        mutation(
            ("objects", capability_digest, "spec", "branches", 0, "rollback_obligations"),
            ["unmapped"],
        )
        mutation(("contract", "spec", "initial_state", "evidence"), {"unmapped": "1"})
        mutation(
            ("contract", "spec", "action_catalogue", row, "successors", 0, "reservations"),
            [{"unmapped": "pool"}],
        )
        mutation(("plan", "spec", "policy"), None)
        mutation(("plan", "spec", "history"), [{"action_id": "prepare", "observation": "red"}])
    for changed in cases:
        monkeypatch.setattr(native_projection_check, "native_check", lambda _, value=changed: value)
        with pytest.raises(ValueError):
            native_projection_check.check(run, raw, projected)
    assert original == native_checks.check(raw)


@native
@pytest.mark.parametrize("producer", ["alt", "vek"])
def test_exact_clock_projection_fits_native_endpoints(tmp_path: Path, producer: str) -> None:
    from ccr.optimizer import native_clock
    from ccr.optimizer.model import timestamp

    run, source, registration = registered(tmp_path, producer, clocked=True)
    checked = native_projection_check.check(
        run, source, native_projection.project(source, registration)
    )
    for name, envelope in checked["envelopes"].items():
        interval = envelope["clock_window"]
        action = run["config"]["growth"]["actions"][name]
        assert (
            timestamp(interval["execution_end"]) - timestamp(interval["start"])
        ).total_seconds() == action["duration_seconds"]
        assert native_clock.applicable(interval, interval["start"], action["duration_seconds"], 1)
        assert not native_clock.applicable(
            interval, interval["start"], action["duration_seconds"] + 1
        )
