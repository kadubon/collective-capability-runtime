# SPDX-License-Identifier: Apache-2.0
"""Bounded CCR-source export to CAIT's native finite accounting vocabulary.

This exporter is read-only. It does not add accounting totals back into reward.
Unsupported histories retain explicit obligations instead of fabricated sources.
"""

from __future__ import annotations

import importlib
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer import growth_ledger
from ccr.optimizer.model import timestamp


def export(run: dict[str, Any], current: str) -> dict[str, Any]:
    from importlib.metadata import version

    if version("cait-certificate-schema") != "0.2.0":
        raise ValueError("CAIT 0.2.0 required")
    source = importlib.import_module("cait_schema.accounting.source")
    g = run["config"]["growth"]
    ledger = growth_ledger.replay(run, current)
    origin = timestamp(run["created_at"])

    def tick(at: str) -> int:
        delta = timestamp(at) - origin
        if delta.microseconds or not 0 <= delta.total_seconds() <= 999999:
            raise ValueError("CAIT registered integer-second clock bounds")
        return int(delta.total_seconds())

    end = tick(current) + 1
    obligations: list[str] = []
    events: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    bindings: dict[str, Any] = {}
    receivers = {}
    for name, action in g["actions"].items():
        receiver = g["receivers"][action["receiver"]]
        receivers[name] = {
            "id": name,
            "context": receiver["context_sha256"],
            "task": action["target_id"],
            "evaluator": receiver["evaluator"],
            "protocol": receiver["protocol"],
            "checks": ["ccr-signed-result"],
        }
    if len(receivers) > 16:
        raise ValueError("CAIT receiver/task mapping bound")

    def add(
        row: dict[str, Any], kind: str, data: dict[str, Any], costs: list[str], proof: list[str]
    ) -> None:
        eid = kind + ":" + sha256_json([row["digest"], data])
        events.append(
            {
                "id": eid,
                "scope": run["mission_id"],
                "episode": run["run_id"],
                "contract": "0" * 64,
                "stream": "ccr-training",
                "sequence": len(events) + 1,
                "previous": "0" * 64,
                "time": tick(row["recorded_at"]),
                "recorded": tick(row["recorded_at"]),
                "arm": "training",
                "study": g["study_id"],
                "kind": kind,
                "dependencies": [],
                "evidence": proof,
                "costs": costs,
                "data": data,
            }
        )
        bindings[eid] = row["digest"]

    created: set[str] = set()
    for row in run["growth_events"]:
        p = row["payload"]
        if row["kind"] == "lifecycle":
            if p["asset"] in created and p["state"] == "withdrawn":
                add(
                    row,
                    "withdraw",
                    {"artifact": p["asset"], "reason": "ccr-signed-withdrawal"},
                    [],
                    [],
                )
            else:
                obligations.append("unsupported-lifecycle:" + row["digest"])
            continue
        if row["kind"] != "outcome" or p["group"] != "training":
            continue
        action = g["actions"][p["action_id"]]
        costs = []
        for unit, amount in p["costs"].items():
            cid = "cost:" + sha256_json([p["acceptance_evidence"], unit])
            costs.append(cid)
            stage = {
                "formation": "formation",
                "transfer_validation": "transfer",
                "repair": "repair",
            }.get(action["kind"], "execution")
            add(
                row,
                "cost",
                {
                    "cost_id": cid,
                    "unit": g["units"]["costs"][unit],
                    "quantity": {"declared": str(amount)},
                    "stage": stage,
                },
                [],
                [],
            )
        asset = p["artifact_sha256"]
        receiver = receivers[p["action_id"]]
        proof = "proof:" + p["acceptance_evidence"]
        record = {
            "id": proof,
            "scope": run["mission_id"],
            "arm": "training",
            "artifact": asset,
            "receiver": receiver["id"],
            "context": receiver["context"],
            "evaluator": receiver["evaluator"],
            "protocol": receiver["protocol"],
            "check": "ccr-signed-result",
            "outcome": "pass" if p["success"] else "fail",
            "valid_from": tick(row["recorded_at"]),
            "valid_until": end + 1,
            "dependencies": [],
            "blocking_defeaters": [],
            "cost_ids": costs,
        }
        evidence.append(source.envelope(record))
        if action["produces"]:
            if not p["success"] or g["assets"][asset]["parents"] or asset in created:
                obligations.append("unmapped-formation:" + row["digest"])
                continue
            expires = tick(g["assets"][asset]["expires_at"])
            add(
                row,
                "create",
                {
                    "artifact": asset,
                    "coordinate": "assets",
                    "quantity": {"declared": "1"},
                    "shares": {"endogenous": "0", "external": "0", "unresolved": "1"},
                    "parents": [],
                    "parent_shares": {},
                    "expires": expires,
                },
                costs,
                [proof],
            )
            created.add(asset)
        elif action["kind"] in {"reuse", "service"}:
            if asset not in created:
                obligations.append("missing-creation:" + row["digest"])
                continue
            target = next(
                t for t in run["config"]["task_manifest"] if t["target_id"] == action["target_id"]
            )
            outcome = {"success": "success", "failed": "failure", "timeout": "timeout"}.get(
                p["status"]
            )
            if outcome is None:
                obligations.append("unsupported-use-status:" + row["digest"])
                continue
            add(
                row,
                "use",
                {
                    "artifact": asset,
                    "coordinate": "task",
                    "quantity": {"declared": str(action["gains"]["task"])},
                    "receiver": receiver["id"],
                    "context": receiver["context"],
                    "task": receiver["task"],
                    "input": target["input_sha256"],
                    "evaluator": receiver["evaluator"],
                    "protocol": receiver["protocol"],
                    "outcome": outcome,
                },
                costs,
                [proof],
            )
    if not events:
        raise ValueError("source-bound accounting requires original signed CCR events")
    if any(t["group"] == "training" and t["state"] != "evaluated" for t in run["trials"]):
        obligations.append("unfinished-CCR-work")
    contract = {
        "record_type": "cait_computation_contract_v1",
        "scope": run["mission_id"],
        "episode": run["run_id"],
        "study": g["study_id"],
        "time_unit": "ccr-elapsed-second",
        "start": 0,
        "end": end,
        "cutoff": end,
        "checkpoint_time": 0,
        "basis": "synthetic" if g["evidence_mode"] == "synthetic" else "declared-record",
        "interpretation": "as_of",
        "coordinates": [
            {"id": "assets", "unit": "artifact", "meaning": "asset_stock"},
            {"id": "task", "unit": g["units"]["task"], "meaning": "service_outcome"},
        ],
        "receivers": list(receivers.values()),
        "arms": ["training"],
        "scenarios": ["declared"],
        "opening": [],
        "streams": [
            {
                "id": "ccr-training",
                "arm": "training",
                "checkpoint": g["checkpoint_digest"],
                "first": 1,
                "last": len(events),
                "terminal": "0" * 64,
            }
        ],
        "mandatory_events": [e["id"] for e in events],
        "mandatory_costs": [e["data"]["cost_id"] for e in events if e["kind"] == "cost"],
        "negative_terms_complete": not obligations,
        "allocations": {},
        "cost_units": list(g["units"]["costs"].values()),
        "resource_limits": {
            g["units"]["costs"][k]: {"declared": str(v)} for k, v in g["quota"]["budget"].items()
        },
        "valuation": {"version": "ccr-no-cross-unit-valuation", "target": "assets", "rates": {}},
        "operation_budget": 100000,
        "policy": "disjoint-origin-v1:content-dedup:propagate-revocation:half-open",
    }
    contract_digest = source.registration(contract)
    previous = g["checkpoint_digest"]
    wrapped = []
    for event in events:
        event["contract"], event["previous"] = contract_digest, previous
        item = source.envelope(event)
        wrapped.append(item)
        previous = item["sha256"]
    contract["streams"][0]["terminal"] = previous
    bundle = {
        "record_type": "cait_source_bundle_v1",
        "contract": contract,
        "events": wrapped,
        "evidence": evidence,
        "models": [],
    }
    # Shape/source validation is not a substitute for the independent report checker.
    source.prepare(bundle)
    return {
        "profile": "ccr-cait-source-export-1",
        "run_id": run["run_id"],
        "config_digest": run["config"]["config_digest"],
        "revision": run["revision"],
        "journal_digest": ledger["journal_digest"],
        "clock_origin": run["created_at"],
        "bundle": bundle,
        "event_bindings": bindings,
        "remaining_obligations": obligations,
        "ccr_sources": [
            row for row in run["growth_events"] if row["kind"] in {"outcome", "lifecycle"}
        ],
        "non_actionable": [
            "research coordinate overlaps task service; not added to CAIT totals",
            "origin shares remain unresolved",
        ],
        "source_authentication": (
            "CCR signatures checked separately; native CAIT authentication unestablished"
        ),
    }


def check_feedback(
    run: dict[str, Any], exported: dict[str, Any], report: dict[str, Any], current: str
) -> dict[str, Any]:
    """Independent source-to-event reconciliation; does not call the exporter."""
    from fractions import Fraction

    from ccr.optimizer.growth_model import closed

    closed(
        exported,
        "profile run_id config_digest revision journal_digest clock_origin bundle "
        "event_bindings remaining_obligations non_actionable source_authentication ccr_sources",
    )
    ledger = growth_ledger.replay(run, current)
    if (
        exported["profile"] != "ccr-cait-source-export-1"
        or exported["run_id"] != run["run_id"]
        or exported["config_digest"] != run["config"]["config_digest"]
        or exported["revision"] != run["revision"]
        or exported["journal_digest"] != ledger["journal_digest"]
        or exported["clock_origin"] != run["created_at"]
        or exported["ccr_sources"]
        != [r for r in run["growth_events"] if r["kind"] in {"outcome", "lifecycle"}]
    ):
        raise ValueError("stale or substituted CCR source history")
    checker = importlib.import_module("cait_schema.accounting.checker")
    source = importlib.import_module("cait_schema.accounting.source")
    checked = checker.check_report(exported["bundle"], report)
    if checked["status"] != "checked":
        raise ValueError("native CAIT report failed fresh checking")
    prepared = source.prepare(exported["bundle"])
    g, c = run["config"]["growth"], prepared.contract
    if (
        c["scope"] != run["mission_id"]
        or c["episode"] != run["run_id"]
        or c["study"] != g["study_id"]
        or c["arms"] != ["training"]
        or c["scenarios"] != ["declared"]
        or c["opening"]
        or c["allocations"]
        or c["valuation"]["rates"]
        or prepared.models
        or c["time_unit"] != "ccr-elapsed-second"
    ):
        raise ValueError("CAIT accounting premise substitution")
    originals = {r["digest"]: r for r in exported["ccr_sources"]}
    expected_obligations = set()
    formed = set()
    for original in exported["ccr_sources"]:
        payload = original["payload"]
        if original["kind"] == "lifecycle":
            if payload["state"] != "withdrawn" or payload["asset"] not in formed:
                expected_obligations.add("unsupported-lifecycle:" + original["digest"])
        elif payload["group"] == "training":
            action = g["actions"][payload["action_id"]]
            asset = payload["artifact_sha256"]
            if action["produces"]:
                if not payload["success"] or g["assets"][asset]["parents"] or asset in formed:
                    expected_obligations.add("unmapped-formation:" + original["digest"])
                else:
                    formed.add(asset)
            elif action["kind"] in {"reuse", "service"}:
                if asset not in formed:
                    expected_obligations.add("missing-creation:" + original["digest"])
                elif payload["status"] not in {"success", "failed", "timeout"}:
                    expected_obligations.add("unsupported-use-status:" + original["digest"])
    if any(t["group"] == "training" and t["state"] != "evaluated" for t in run["trials"]):
        expected_obligations.add("unfinished-CCR-work")
    if set(exported["remaining_obligations"]) != expected_obligations:
        raise ValueError("unsupported accounting obligation is not bound to CCR history")
    seen = set()
    for event in prepared.events:
        parent = originals.get(exported["event_bindings"].get(event["id"]))
        if parent is None:
            raise ValueError("unbound CAIT source event")
        p, data = parent["payload"], event["data"]
        expected_time = int(
            (timestamp(parent["recorded_at"]) - timestamp(run["created_at"])).total_seconds()
        )
        if event["time"] != expected_time or event["recorded"] != expected_time:
            raise ValueError("CAIT source clock substitution")
        if event["kind"] == "cost":
            if parent["kind"] != "outcome" or p["group"] != "training":
                raise ValueError("cost source is not a CCR training result")
            unit = next((u for u, v in g["units"]["costs"].items() if v == data["unit"]), None)
            if (
                unit is None
                or data["quantity"] != {"declared": str(p["costs"][unit])}
                or data["cost_id"] != "cost:" + sha256_json([p["acceptance_evidence"], unit])
            ):
                raise ValueError("physical cost identity or amount changed")
            identity = (parent["digest"], "cost", unit)
        elif event["kind"] == "withdraw":
            if (
                parent["kind"] != "lifecycle"
                or p["state"] != "withdrawn"
                or data["artifact"] != p["asset"]
            ):
                raise ValueError("loss is not an admitted signed CCR withdrawal")
            identity = (parent["digest"], "withdraw", "")
        elif event["kind"] in {"create", "use"}:
            if (
                parent["kind"] != "outcome"
                or p["group"] != "training"
                or data["artifact"] != p["artifact_sha256"]
            ):
                raise ValueError("unbound creation/service")
            action = g["actions"][p["action_id"]]
            if event["kind"] == "create":
                expires = int(
                    (
                        timestamp(g["assets"][data["artifact"]]["expires_at"])
                        - timestamp(run["created_at"])
                    ).total_seconds()
                )
                if (
                    not p["success"]
                    or action["produces"] != data["artifact"]
                    or data["quantity"] != {"declared": "1"}
                    or data["parents"]
                    or data["shares"] != {"endogenous": "0", "external": "0", "unresolved": "1"}
                    or data["expires"] != expires
                ):
                    raise ValueError("creation lacks matching current CCR evidence")
            else:
                receiver = g["receivers"][action["receiver"]]
                target = next(
                    t
                    for t in run["config"]["task_manifest"]
                    if t["target_id"] == action["target_id"]
                )
                if (
                    action["kind"] not in {"service", "reuse"}
                    or data["quantity"] != {"declared": str(action["gains"]["task"])}
                    or data["receiver"] != p["action_id"]
                    or data["task"] != action["target_id"]
                    or data["input"] != target["input_sha256"]
                    or data["context"] != receiver["context_sha256"]
                    or data["evaluator"] != receiver["evaluator"]
                    or data["protocol"] != receiver["protocol"]
                    or data["outcome"]
                    != {"success": "success", "failed": "failure", "timeout": "timeout"}.get(
                        p["status"]
                    )
                ):
                    raise ValueError("service scope or outcome substitution")
            identity = (parent["digest"], event["kind"], "")
        else:
            raise ValueError("unsupported accounting event projection")
        if identity in seen:
            raise ValueError("duplicate original CCR accounting event")
        seen.add(identity)
    expected_costs = {
        (r["digest"], "cost", u)
        for r in originals.values()
        if r["kind"] == "outcome" and r["payload"]["group"] == "training"
        for u in r["payload"]["costs"]
    }
    if not expected_costs <= seen:
        raise ValueError("missing physical cost history")
    for balance in report["balances"]:
        if any(
            Fraction(balance["costs"][g["units"]["costs"][u]]) != v
            for u, v in ledger["actual_costs"].items()
        ):
            raise ValueError("CAIT cost totals disagree with CCR signed history")
    complete = (
        not exported["remaining_obligations"] and report["completeness"] == "declared_complete"
    )
    if complete:
        balances = {b["coordinate"]: b for b in report["balances"]}
        if (
            Fraction(balances["assets"]["closing"]) != len(ledger["eligible_assets"])
            or Fraction(balances["task"]["service"]) != ledger["observed_service"]["task"]
        ):
            raise ValueError("CAIT stock/service totals disagree with CCR replay")
    return {
        "ok": True,
        "complete": complete,
        "native_check": checked,
        "journal_digest": ledger["journal_digest"],
        "costs": ledger["actual_costs"],
        "invalidated_assets": ledger["invalidated_assets"],
        "remaining_obligations": exported["remaining_obligations"],
        "source_authentication": "CCR signed source envelopes separately checked",
        "native_authentication": "unestablished",
        "reward_added": 0,
        "asset_stock_added": 0,
        "causal_attribution": None,
    }


def reconcile(
    store: Any,
    run_id: str,
    exported: dict[str, Any],
    report: dict[str, Any],
    *,
    expected_revision: int,
) -> dict[str, Any]:
    """Commit a derived view and bounded registered review eligibility, never reward."""
    from ccr.optimizer import engine
    from ccr.optimizer.growth_model import integer

    integer(expected_revision)
    identity = sha256_json({"export": exported, "report": report})
    snapshot = engine.load(store, run_id)
    if identity in snapshot.get("native_feedback", {}):
        return engine.response(idempotent=True, feedback_id=identity)
    checked = check_feedback(snapshot, exported, report, store.now())
    with engine.edit_run(store, run_id) as (run, current):
        if identity in run.get("native_feedback", {}):
            return engine.response(idempotent=True, feedback_id=identity)
        if (
            run["revision"] != expected_revision
            or run["growth_events"] != snapshot["growth_events"]
        ):
            raise ValueError("stale accounting feedback revision")
        if run["frozen_policy"] or run["state"] != "training":
            raise ValueError("accounting feedback cannot train a frozen policy")
        actions = []
        if checked["invalidated_assets"] or checked["remaining_obligations"]:
            for name, binding in run.get("native_registration", {}).get("bindings", {}).items():
                action = run["config"]["growth"]["actions"][name]
                if (
                    binding["producer"] == "cait"
                    and binding["contract_sha256"] == run["config"]["config_digest"]
                    and binding["source_action"] == "accounting-review"
                    and action["kind"] in {"diagnostic", "repair"}
                ):
                    actions.append(name)
        entry = {
            "source_journal": checked["journal_digest"],
            "actions": sorted(actions),
            "checked": checked,
        }
        run.setdefault("native_feedback", {})[identity] = entry
        growth_ledger.append(run, "native_feedback", {"feedback_id": identity, **entry}, current)
        run["revision"] += 1
        return engine.response(
            mutated_runtime=True, feedback_id=identity, revision=run["revision"], **checked
        )
