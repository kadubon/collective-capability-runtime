# SPDX-License-Identifier: Apache-2.0
"""Replay service accounting without capital multiplication or causal attribution."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer.model import timestamp


def append(run: dict[str, Any], kind: str, payload: dict[str, Any], current: str) -> None:
    journal = run["growth_events"]
    row = {
        "sequence": len(journal),
        "previous": journal[-1]["digest"] if journal else None,
        "kind": kind,
        "payload": payload,
        "recorded_at": current,
        "policy_revision": run["revision"],
    }
    row["digest"] = sha256_json(row)
    journal.append(row)


def replay(run: dict[str, Any], current: str, *, group: str = "training") -> dict[str, Any]:
    from pathlib import Path

    from ccr.optimizer.engine import _trial, _verify
    from ccr.optimizer.growth_planner import service_identity
    from ccr.phase.eligibility import packet_eligibility
    from ccr.schemas.validation import validate_instance

    g = run["config"]["growth"]
    assets: dict[str, Any] = {}
    qualifications: dict[str, Any] = {}
    outcomes: dict[str, Any] = {}
    costs = dict.fromkeys(g["units"]["costs"], 0)
    attempts = []
    invalidated: set[str] = set()
    measured_service = {}
    previous = None
    compatible = set(g["scenarios"])
    committed = {
        t["trial_id"]: t["growth_envelope_digest"]
        for t in run["trials"]
        if t.get("growth_envelope_digest")
    }
    replayed = {}
    for index, event in enumerate(run["growth_events"]):
        unsigned = {k: v for k, v in event.items() if k != "digest"}
        if (
            event["sequence"] != index
            or event["previous"] != previous
            or sha256_json(unsigned) != event["digest"]
        ):
            raise ValueError("growth journal digest chain invalid")
        previous = event["digest"]
        p = event["payload"]
        if event["kind"] == "lifecycle":
            _verify(run["config"], p)
            if (
                p["run_id"] != run["run_id"]
                or p["config_digest"] != run["config"]["config_digest"]
                or p["state"] not in {"withdrawn", "quarantined", "expired", "corrected"}
            ):
                raise ValueError("invalid lifecycle scope or authority")
            if p["state"] in {"withdrawn", "quarantined", "expired", "corrected"}:
                invalidated.add(p["asset"])
                for _ in g["assets"]:
                    invalidated.update(
                        a for a, spec in g["assets"].items() if set(spec["parents"]) & invalidated
                    )
            continue
        if event["kind"] != "outcome":
            continue
        envelope = p["envelope"]
        _verify(run["config"], envelope)
        _verify(run["config"], envelope["result"])
        trial = _trial(run, p["trial_id"])
        action = g["actions"][trial["growth_action"]]
        signed_fields = {
            "artifact_sha256": envelope["result"].get("artifact_sha256"),
            "observed_at": envelope["result"]["observed_at"],
            **{
                k: envelope["observation"][k]
                for k in (
                    "artifact_version",
                    "parents",
                    "external_inputs",
                    "status",
                    "measured_service",
                )
            },
            "service_identity": service_identity(run, action, trial["group"]),
        }
        if any(p[k] != value for k, value in signed_fields.items()):
            raise ValueError("journal derived fields differ from signed scope")
        if (
            sha256_json(envelope) != p["acceptance_evidence"]
            or p["costs"] != envelope["result"]["actual_resources"]
            or p["action_id"] != envelope["observation"]["action_id"]
        ):
            raise ValueError("journal differs from authenticated observation")
        if (
            p["group"] != trial["group"]
            or p["action_id"] != trial["growth_action"]
            or p["success"] != (envelope["result"]["accepted"] and p["qualified"])
        ):
            raise ValueError("journal trial or success binding mismatch")
        if p["success"]:
            result = envelope["result"]
            packet = result.get("packet")
            if (
                not isinstance(packet, dict)
                or not validate_instance("packet", packet).ok
                or not packet_eligibility(Path("."), packet, ledger_blockers=result["residuals"])[
                    "positive_contribution"
                ]
            ):
                raise ValueError("journal cannot promote ineligible signed evidence")
        replayed[p["trial_id"]] = p["acceptance_evidence"]
        if p["group"] == "training" and p["qualified"] and p["status"] in {"success", "failed"}:
            compatible = {
                s for s in compatible if g["scenarios"][s][p["action_id"]] in {None, p["success"]}
            }
        if p["group"] != group:
            continue
        for k in costs:
            costs[k] += p["costs"][k]
        attempts.append(p)
        if not p["qualified"] or not p["success"]:
            continue
        action = g["actions"][p["action_id"]]
        asset = p["artifact_sha256"]
        if action["kind"] == "revalidation":
            invalidated.discard(asset)
        if action["kind"] == "verification_investment":
            measured_service[asset] = p["measured_service"]
        if action["produces"]:
            assets.setdefault(
                asset,
                {
                    "source_event": event["digest"],
                    "created_at": p["observed_at"],
                    "parents": g["assets"][asset]["parents"],
                },
            )
            qualifications[f"{asset}:{action['receiver']}"] = event["digest"]
        if action["kind"] == "transfer_validation":
            for a in action["requires"]:
                qualifications[f"{a}:{action['receiver']}"] = event["digest"]
        if action["kind"] in {"service", "reuse"}:
            # Identity includes arm, task, input, receiver, protocol. Asset identity is separate.
            key = sha256_json(p["service_identity"])
            outcomes.setdefault(
                key,
                {
                    "gains": action["gains"],
                    "event": event["digest"],
                    "parents": action["requires"],
                    "action_id": p["action_id"],
                    "observed_at": p["observed_at"],
                },
            )
    # Transitive invalidation affects future eligibility, not historical receipts.
    if any(replayed.get(trial) != digest for trial, digest in committed.items()):
        raise ValueError("committed observation missing from replay")
    changed = True
    while changed:
        before = set(invalidated)
        for a, spec in g["assets"].items():
            if (
                timestamp(spec["expires_at"]) <= timestamp(current)
                or set(spec["parents"]) & invalidated
            ):
                invalidated.add(a)
        changed = before != invalidated
    available = sorted(a for a in assets if a not in invalidated)
    eligible = sorted(k for k in qualifications if k.split(":", 1)[0] in available)
    observed = {k: sum(o["gains"][k] for o in outcomes.values()) for k in g["targets"]}
    pending = []
    for a, record in assets.items():
        end = min(
            timestamp(g["window_end"]),
            timestamp(record["created_at"]) + timedelta(seconds=g["attribution_seconds"]),
        )
        uses = [
            o for o in outcomes.values() if a in o["parents"] and timestamp(o["observed_at"]) <= end
        ]
        pending.append(
            {
                "asset": a,
                "window_end": end.isoformat(),
                "downstream_uses": len(uses),
                "state": "observed"
                if uses
                else ("pending" if timestamp(current) < end else "censored"),
                "attribution_unresolved": True,
            }
        )
    return {
        "observed_service": observed,
        "service_events": outcomes,
        "asset_count": len(assets),
        "assets": assets,
        "eligible_assets": available,
        "receiver_qualifications": eligible,
        "invalidated_assets": sorted(invalidated),
        "actual_costs": costs,
        "attempts": attempts,
        "delayed_reuse": pending,
        "compatible_scenarios": sorted(compatible),
        "journal_digest": previous,
        "attribution_unresolved": True,
        "overlapping_measurements": sum(all(o["gains"].values()) for o in outcomes.values()),
        "measured_verifier_service": {a: v for a, v in measured_service.items() if a in available},
        "joint_service_capacity": None,
        "causal_gain": None,
        "statistical_improvement": None,
    }


def prerequisites(g: dict[str, Any], action: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    receiver = g["receivers"][action["receiver"]]
    reasons = []
    for a in action["requires"]:
        spec = g["assets"][a]
        if a not in ledger["eligible_assets"]:
            reasons.append("source_not_currently_eligible:" + a)
        if action["receiver"] not in spec["receivers"]:
            reasons.append("receiver_not_in_transfer_scope:" + a)
        if (
            spec["source_mission"] != receiver["mission_id"]
            and not receiver["cross_mission_allowed"]
        ):
            reasons.append("cross_mission_not_authorized:" + a)
        if (
            action["kind"] != "transfer_validation"
            and f"{a}:{action['receiver']}" not in ledger["receiver_qualifications"]
        ):
            reasons.append("receiver_not_qualified:" + a)
    return reasons
