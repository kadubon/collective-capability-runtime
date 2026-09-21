# SPDX-License-Identifier: Apache-2.0
"""Independent reconstruction from original documents; never imports the projector."""

from __future__ import annotations

from fractions import Fraction
from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer.growth_model import closed, digest, integer, text
from ccr.optimizer.native_checks import PACKAGES
from ccr.optimizer.native_checks import check as native_check
from ccr.optimizer.native_history import cpcf_history
from ccr.optimizer.native_schemas import validate
from ccr.optimizer.native_wire import convert, rational


def registration_check(run: dict[str, Any], registration: dict[str, Any]) -> None:
    validate("native-registration", registration)
    closed(
        registration,
        "schema_version run_id config_digest study_id arm pool_id bindings units"
        + (" pools" if "pools" in registration else ""),
    )
    g = run["config"]["growth"]
    if (
        registration["schema_version"] != "ccr.native_registration.v1"
        or registration["run_id"] != run["run_id"]
        or registration["config_digest"] != run["config"]["config_digest"]
        or registration["study_id"] != g["study_id"]
        or registration["arm"] != "training"
        or registration["pool_id"] != g["quota"]["pool_id"]
        or g["evidence_mode"] != "synthetic"
    ):
        raise ValueError("native registration scope mismatch")
    bindings = registration["bindings"]
    for name, binding in bindings.items():
        closed(
            binding,
            "producer contract_sha256 source_action action_sha256 valid_from valid_until"
            + (" observations" if "observations" in binding else ""),
        )
        if name not in g["actions"] or binding["producer"] not in PACKAGES:
            raise ValueError("unregistered action or producer")
        digest(binding["contract_sha256"])
        text(binding["source_action"])
        if "observations" in binding:
            symbols = binding["observations"]
            if binding["producer"] != "cpcf":
                raise ValueError("invalid registered CPCF observation channel")
            for symbol in symbols.values():
                text(symbol)
        if binding["action_sha256"] != sha256_json(g["actions"][name]):
            raise ValueError("native binding cannot amend frozen action")
        from ccr.optimizer.model import timestamp

        if (
            not timestamp(binding["valid_from"])
            < timestamp(binding["valid_until"])
            <= timestamp(g["window_end"])
        ):
            raise ValueError("native validity outside observation window")
    units = registration["units"]
    if any(
        target not in g["quota"]["capacity"] for target in registration.get("pools", {}).values()
    ):
        raise ValueError("unknown canonical capacity pool")
    for unit, mapping in units.items():
        closed(mapping, "target rate rounding")
        if mapping["target"] not in g["units"]["costs"] or not unit:
            raise ValueError("unknown resource dimension")
        convert("0", mapping["rate"], rounding=mapping["rounding"])


def check(run: dict[str, Any], raw: bytes, projection: dict[str, Any]) -> dict[str, Any]:
    """Check native feasibility and CCR translation separately, without storage writes."""
    validate("native-projection", projection)
    registration = run["native_registration"]
    registration_check(run, registration)
    closed(
        projection,
        "schema_version registration_sha256 source_sha256 document_sha256 producer bindings "
        "native_checker source_authentication service_credit receiver_eligibility "
        "observed_capacity continuation_guarantee_transferred execution_authorization settled",
    )
    source = native_check(raw)
    if (
        projection["schema_version"] != "ccr.native_projection.v1"
        or projection["registration_sha256"] != sha256_json(registration)
        or any(
            projection[k] != source[k]
            for k in ("source_sha256", "document_sha256", "producer", "native_checker")
        )
        or projection["source_authentication"] != "unestablished"
        or type(projection["service_credit"]) is not int
        or projection["service_credit"] != 0
        or projection["observed_capacity"] is not None
        or any(
            projection[k] is not False
            for k in (
                "receiver_eligibility",
                "continuation_guarantee_transferred",
                "execution_authorization",
                "settled",
            )
        )
    ):
        raise ValueError("tampered projection identity or authority dimension")
    d, producer = source["documents"], source["producer"]
    if producer == "cait":
        raise ValueError("CAIT accounting requires source-bound reconciliation")
    if producer == "alt":
        selected = set(d["plan"]["selected"])
    elif producer == "vek":
        selected = set(d["plan"]["schedule"])
    else:
        policy = d["plan"]["spec"]["policy"]
        selected = {policy["action_id"]} if policy else set()
        if d["plan"]["spec"]["history"] != cpcf_history(run, source["document_sha256"]["contract"]):
            raise ValueError("CPCF visible history differs from signed CCR observations")
    expected = {}
    for name, binding in registration["bindings"].items():
        if (
            binding["producer"] == producer
            and binding["contract_sha256"] == source["document_sha256"]["contract"]
            and binding["source_action"] in selected
        ):
            if binding["source_action"] in expected:
                raise ValueError("ambiguous native action mapping")
            expected[binding["source_action"]] = name
    if set(expected) != selected or not selected:
        raise ValueError("incomplete actionable mapping; retain source obligations")
    actual = projection["bindings"]
    if not isinstance(actual, list) or len(actual) != len(expected):
        raise ValueError("projection binding cardinality")
    for row in actual:
        closed(row, "source_action ccr_action")
    if sorted((row["source_action"], row["ccr_action"]) for row in actual) != sorted(
        expected.items()
    ):
        raise ValueError("projection action substitution")
    g = run["config"]["growth"]
    consumed: set[str] = set()
    envelopes = {}
    if producer == "vek":
        elapsed = Fraction()
        for source_id in sorted(selected, key=lambda n: d["plan"]["schedule"][n]):
            target_action = g["actions"][expected[source_id]]
            original_action = next(
                a for a in d["contract"]["actions"] if a["action_id"] == source_id
            )
            work = next(
                w for w in d["contract"]["work"] if w["work_id"] == original_action["work_id"]
            )
            start = d["plan"]["schedule"][source_id] * rational(d["contract"]["slot_seconds"])
            if start < elapsed:
                raise ValueError("VEK serial translation loses reserved timing")
            elapsed = start + target_action["duration_seconds"] + target_action["cleanup_seconds"]
            if elapsed > work["deadline"] * rational(d["contract"]["slot_seconds"]):
                raise ValueError("VEK serial translation misses deadline or cleanup")
            if (
                work["predecessors"]
                or work["separate_from"]
                or original_action["requires_success"]
                or original_action["requires_negative"]
            ):
                raise ValueError(
                    "VEK contingent work requires additional signed prerequisite mapping"
                )
    for original, name in sorted(expected.items()):
        action = g["actions"][name]
        costs: dict[str, Fraction] = {}
        duration = Fraction(0)
        obligations: Any
        if producer == "alt":
            c = d["contract"]
            row = next(o for o in c["options"] if o["id"] == original)
            if c["sunk_cost_ids"] or c["completed_opportunities"] or c["unresolved_work"]:
                raise ValueError("inherited ALT history requires explicit accounting")
            if row["kind"] not in {"formation", "transfer", "reuse", "scratch"}:
                raise ValueError("unsupported ALT lifecycle projection")
            kinds = {
                "formation": "formation",
                "transfer": "transfer_validation",
                "reuse": "reuse",
                "scratch": "service",
            }
            if action["kind"] != kinds[row["kind"]]:
                raise ValueError("ALT task kind mismatch")
            candidates = {q["offer"]["candidate"] for q in c["qualifications"]}
            if row["kind"] == "formation" and action["produces"] not in candidates:
                raise ValueError("ALT candidate identity mismatch")
            if row["kind"] in {"transfer", "reuse"} and not set(action["requires"]) & candidates:
                raise ValueError("ALT missing candidate prerequisite")
            for cost_id in row["costs"]:
                if cost_id in consumed:
                    raise ValueError("shared ALT cost needs explicit single-owner allocation")
                consumed.add(cost_id)
                cost = next(v for v in c["costs"] if v["id"] == cost_id)
                costs[cost["unit"]] = costs.get(cost["unit"], Fraction()) + rational(cost["amount"])
            duration = (row["end"] - row["start"]) * rational(c["slot_seconds"])
            occupancy: dict[tuple[int, str], int] = {}
            for item in row["occupancy"]:
                pool = registration.get("pools", {}).get(item["resource"], item["resource"])
                key = (item["slot"], pool)
                occupancy[key] = occupancy.get(key, 0) + item["quantity"]
            if any(
                pool not in action["capacity"] or amount > action["capacity"][pool]
                for (_, pool), amount in occupancy.items()
            ):
                raise ValueError("ALT canonical pool occupancy underfunded or unmapped")
            if row["offer"] is not None:
                offer = next(q["offer"] for q in c["qualifications"] if q["id"] == row["offer"])
                receiver = g["receivers"][action["receiver"]]
                target = next(
                    t
                    for t in run["config"]["task_manifest"]
                    if t["target_id"] == action["target_id"]
                )
                if (
                    offer["receiver"] != action["receiver"]
                    or offer["mission"] != receiver["mission_id"]
                    or sha256_json(offer["context"]) != receiver["context_sha256"]
                    or offer["protocol"] != receiver["protocol"]
                    or offer["evaluator"] != receiver["evaluator"]
                    or offer["task_family"] != receiver["domain"]
                    or target["input_sha256"] not in offer["inputs"]
                ):
                    raise ValueError("ALT receiver/input/evaluator substitution")
            obligations = row["prerequisites"]
        elif producer == "vek":
            c = d["contract"]
            row = next(a for a in c["actions"] if a["action_id"] == original)
            work = next(w for w in c["work"] if w["work_id"] == row["work_id"])
            if action["kind"] not in {"diagnostic", "repair", "transfer_validation"}:
                raise ValueError("VEK work cannot become capability service")
            duration = row["duration"] * rational(c["slot_seconds"])
            pools: dict[str, int] = {}
            for resource, amount in zip(c["resources"], row["costs"], strict=True):
                if resource["kind"] == "budget":
                    costs[resource["unit"]] = costs.get(resource["unit"], Fraction()) + amount
                else:
                    pool = registration.get("pools", {}).get(
                        resource["resource_id"], resource["resource_id"]
                    )
                    pools[pool] = pools.get(pool, 0) + amount
            if any(
                pool not in action["capacity"] or amount > action["capacity"][pool]
                for pool, amount in pools.items()
            ):
                raise ValueError("VEK canonical pool mapping missing or underfunded")
            target = next(
                t for t in run["config"]["task_manifest"] if t["target_id"] == action["target_id"]
            )
            if work["input_digest"] != target["input_sha256"]:
                raise ValueError("VEK input identity mismatch")
            start = d["plan"]["schedule"][original]
            if start + row["duration"] > work["deadline"]:
                raise ValueError("VEK deadline violation")
            for other, offset in d["plan"]["schedule"].items():
                other_row = next(a for a in c["actions"] if a["action_id"] == other)
                if (
                    other != original
                    and start < offset + other_row["duration"]
                    and offset < start + row["duration"]
                ):
                    raise ValueError("parallel VEK schedule cannot be silently serialized")
            obligations = {"work": work, "action": row, "services": c["services"]}
        else:
            c = d["contract"]["spec"]
            objects = d["objects"]
            row = next(
                a
                for a in c["action_catalogue"]
                if objects[a["action_digest"]]["spec"]["action_id"] == original
            )
            for successor in row["successors"]:
                duration = max(duration, rational(successor["duration"]))
                branch: dict[str, Fraction] = {}
                for category in successor["charges"].values():
                    for unit, value in category.items():
                        branch[unit] = branch.get(unit, Fraction()) + rational(value)
                for unit, value in branch.items():
                    costs[unit] = max(costs.get(unit, Fraction()), value)
                if successor["reservations"]:
                    raise ValueError("CPCF interval reservations need an explicit pool projection")
            obligations = row
        translated = dict.fromkeys(g["units"]["costs"], 0)
        for unit, amount in costs.items():
            if unit not in registration["units"]:
                raise ValueError("missing typed unit conversion")
            mapping = registration["units"][unit]
            translated[mapping["target"]] += convert(
                str(amount), mapping["rate"], rounding=mapping["rounding"]
            )
        arm = next(
            a
            for a in run["config"]["interventions"]
            if a["intervention_id"] == action["intervention_id"]
        )
        if any(arm["resource_upper_bound"][k] < v for k, v in translated.items()):
            raise ValueError("registered action underfunds source work")
        seconds = convert(str(duration), "1", rounding="upper")
        if action["duration_seconds"] < seconds:
            raise ValueError("registered duration loses source work")
        integer(sum(translated.values()))
        envelopes[name] = {
            "costs": translated,
            "duration_seconds": seconds,
            "obligations": obligations,
        }
    return {
        "ok": True,
        "observation_sha256": (
            sha256_json(d["plan"]["spec"]["history"]) if producer == "cpcf" else None
        ),
        "source_sha256": source["source_sha256"],
        "registration_sha256": sha256_json(registration),
        "envelopes": envelopes,
        "native_checker": source["native_checker"],
        "source_authentication": "unestablished",
        "service_credit": 0,
        "execution_authorization": False,
    }
