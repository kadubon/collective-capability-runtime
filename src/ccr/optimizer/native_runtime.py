# SPDX-License-Identifier: Apache-2.0
"""Opt-in native proposal admission in CCR's existing authoritative aggregate."""

from __future__ import annotations

import copy
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer import engine, growth_ledger
from ccr.optimizer.growth_model import integer, text
from ccr.optimizer.model import timestamp
from ccr.optimizer.native_history import cpcf_history
from ccr.optimizer.native_projection_check import check, registration_check
from ccr.optimizer.native_wire import raw_digest
from ccr.storage.control import ControlStore


def register(
    store: ControlStore, run_id: str, registration: dict[str, Any], *, expected_revision: int
) -> dict[str, Any]:
    integer(expected_revision)
    with engine.edit_run(store, run_id) as (run, current):
        if run.get("native_registration") == registration:
            return engine.response(idempotent=True)
        if run["revision"] != expected_revision:
            raise ValueError("stale native registration revision")
        if run["trials"] or run.get("native_registration") or run["frozen_policy"]:
            raise ValueError("native bindings must be registered before work and remain immutable")
        registration_check(run, registration)
        run["native_registration"] = copy.deepcopy(registration)
        run["native_staged"] = {}
        run["native_admitted"] = {}
        growth_ledger.append(run, "native_registration", copy.deepcopy(registration), current)
        run["revision"] += 1
        return engine.response(mutated_runtime=True, revision=run["revision"])


def stage(
    store: ControlStore,
    run_id: str,
    raw: bytes,
    projection: dict[str, Any],
    *,
    expected_revision: int,
    idempotency_key: str,
) -> dict[str, Any]:
    integer(expected_revision)
    text(idempotency_key)
    snapshot = engine.load(store, run_id)
    checked = check(snapshot, raw, projection)
    record = {"raw": raw.decode("utf-8"), "projection": projection, "check": checked}
    identity = sha256_json(record)
    with engine.edit_run(store, run_id) as (run, current):
        staged = run["native_staged"]
        if idempotency_key in staged:
            if staged[idempotency_key]["identity"] != identity:
                raise ValueError("conflicting staged delivery")
            return engine.response(idempotent=True, proposal_id=identity)
        if any(r["identity"] == identity for r in staged.values()):
            return engine.response(idempotent=True, proposal_id=identity)
        if (
            run["revision"] != expected_revision
            or run["native_registration"] != snapshot["native_registration"]
        ):
            raise ValueError("stale native projection")
        if len(staged) >= 64 or run["frozen_policy"]:
            raise ValueError("native staging bound or frozen training policy")
        _valid(run, checked["envelopes"], current)
        staged[idempotency_key] = {"identity": identity, **copy.deepcopy(record)}
        growth_ledger.append(run, "native_stage", {"proposal_id": identity}, current)
        run["revision"] += 1
        return engine.response(mutated_runtime=True, proposal_id=identity, revision=run["revision"])


def _valid(run: dict[str, Any], names: Any, current: str) -> None:
    for name in names:
        binding = run["native_registration"]["bindings"][name]
        if (
            not timestamp(binding["valid_from"])
            <= timestamp(current)
            < timestamp(binding["valid_until"])
        ):
            raise ValueError("native binding expired or not yet valid")


def admit(
    store: ControlStore,
    run_id: str,
    proposal_id: str,
    *,
    expected_revision: int,
) -> dict[str, Any]:
    integer(expected_revision)
    snapshot = engine.load(store, run_id)
    records = [r for r in snapshot["native_staged"].values() if r["identity"] == proposal_id]
    if len(records) != 1:
        raise ValueError("one explicitly staged native proposal required")
    record = records[0]
    # Native work is repeated freshly outside the database lock.
    checked = check(snapshot, record["raw"].encode("utf-8"), record["projection"])
    with engine.edit_run(store, run_id) as (run, current):
        if proposal_id in run["native_admitted"]:
            return engine.response(idempotent=True, proposal_id=proposal_id)
        if (
            run["revision"] != expected_revision
            or run["native_registration"] != snapshot["native_registration"]
        ):
            raise ValueError("stale native admission revision")
        if run["frozen_policy"] or run["state"] != "training":
            raise ValueError("native admission cannot train a frozen policy")
        stored = next(
            (r for r in run["native_staged"].values() if r["identity"] == proposal_id), None
        )
        if stored != record or checked != record["check"]:
            raise ValueError("native staged source or checker binding changed")
        _valid(run, checked["envelopes"], current)
        entry = {
            "source_sha256": raw_digest(record["raw"].encode("utf-8")),
            "actions": sorted(checked["envelopes"]),
            "registration_sha256": sha256_json(run["native_registration"]),
            "admitted_at": current,
            "observation_sha256": checked["observation_sha256"],
        }
        run["native_admitted"][proposal_id] = entry
        growth_ledger.append(
            run, "native_admission", {"proposal_id": proposal_id, **entry}, current
        )
        run["revision"] += 1
        return engine.response(
            mutated_runtime=True,
            revision=run["revision"],
            admitted_actions=entry["actions"],
            service_credit=0,
            receiver_eligibility=False,
            observed_capacity=None,
        )


def blockers(run: dict[str, Any], name: str, current: str, group: str) -> list[str]:
    registration = run.get("native_registration")
    if not registration or name not in registration["bindings"]:
        return []
    if group != registration["arm"]:
        return ["native_evidence_outside_registered_arm"]
    try:
        _valid(run, [name], current)
    except ValueError:
        return ["native_source_expired"]
    if registration["bindings"][name]["producer"] == "cait":
        for identity, feedback in run.get("native_feedback", {}).items():
            if name in feedback["actions"] and any(
                row["kind"] == "native_feedback"
                and row["payload"] == {"feedback_id": identity, **feedback}
                for row in run["growth_events"]
            ):
                return []
        return ["source_bound_accounting_review_not_admitted"]
    for identity, entry in run["native_admitted"].items():
        if name not in entry["actions"]:
            continue
        records = [r for r in run["native_staged"].values() if r["identity"] == identity]
        if len(records) != 1:
            return ["native_source_missing"]
        record = records[0]
        payload = {k: v for k, v in record.items() if k != "identity"}
        if (
            sha256_json(payload) != identity
            or entry["registration_sha256"] != sha256_json(registration)
            or entry["source_sha256"] != raw_digest(record["raw"].encode("utf-8"))
            or name not in record["check"]["envelopes"]
            or not any(
                row["kind"] == "native_admission"
                and row["payload"] == {"proposal_id": identity, **entry}
                for row in run["growth_events"]
            )
        ):
            return ["native_admission_integrity"]
        if registration["bindings"][name]["producer"] == "cpcf":
            try:
                history = cpcf_history(run, registration["bindings"][name]["contract_sha256"])
            except ValueError:
                return ["native_observation_unmapped"]
            if entry["observation_sha256"] != sha256_json(history):
                continue
        if registration["bindings"][name]["producer"] == "alt":
            growth_ledger.replay(run, current, group=group)
            completed = {
                registration["bindings"][row["payload"]["action_id"]]["source_action"]
                for row in run["growth_events"]
                if row["kind"] == "outcome"
                and row["payload"]["group"] == group
                and row["payload"]["success"]
                and row["payload"]["action_id"] in registration["bindings"]
                and registration["bindings"][row["payload"]["action_id"]]["contract_sha256"]
                == registration["bindings"][name]["contract_sha256"]
            }
            if not set(record["check"]["envelopes"][name]["obligations"]) <= completed:
                return ["native_ALT_prerequisite_not_observed"]
        return []
    return ["native_proposal_not_admitted:" + name]


def verification_work(run: dict[str, Any], current: str) -> dict[str, Any]:
    """Replay typed VEK work status without converting it into service capacity.

    Invalid means a signed result failed CCR qualification. Censored means the
    observation window ended without a result; reservations remain authoritative.
    Neither label fabricates a negative check or releases uncertain execution.
    """
    growth_ledger.replay(run, current)
    outcomes = {
        row["payload"]["action_id"]: row["payload"]
        for row in run["growth_events"]
        if row["kind"] == "outcome" and row["payload"]["group"] == "training"
    }
    work = {}
    for name, binding in run.get("native_registration", {}).get("bindings", {}).items():
        if binding["producer"] != "vek":
            continue
        outcome = outcomes.get(name)
        if outcome is None:
            status = (
                "censored"
                if timestamp(current) >= timestamp(run["config"]["growth"]["window_end"])
                else "pending"
            )
        elif not outcome["qualified"]:
            status = "invalid"
        else:
            status = {
                "success": "positive",
                "failed": "negative",
                "timeout": "timeout",
                "inconclusive": "inconclusive",
            }[outcome["status"]]
        work[name] = {
            "source_action": binding["source_action"],
            "status": status,
            "verification_completed": status in {"positive", "negative"},
            "signed_source": outcome["acceptance_evidence"] if outcome else None,
            "service_credit": 0,
            "observed_capacity": None,
        }
    return work
