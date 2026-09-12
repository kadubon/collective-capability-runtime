# SPDX-License-Identifier: Apache-2.0
"""Closed, exact, finite opt-in growth contracts. Forecasts are not observations."""

from __future__ import annotations

import copy
import re
from typing import Any

from ccr.ids import sha256_json, validate_identifier
from ccr.optimizer.model import normalize_config, timestamp

PROFILE = "ccr.growth_profile.v1"
RESULT = "ccr.growth_result.v1"
PLAN = "ccr.growth_plan.v1"
REPORT = "ccr.growth_report.v1"
KINDS = {
    "formation",
    "transfer_validation",
    "reuse",
    "verification_investment",
    "repair",
    "service",
    "diagnostic",
    "revalidation",
}
MAPPING = {
    "formation": "distillation",
    "transfer_validation": "verification",
    "reuse": "independent_proposal",
    "verification_investment": "measurement",
    "repair": "residual_repair",
    "service": "independent_proposal",
    "diagnostic": "measurement",
    "revalidation": "verification",
}


def closed(value: Any, fields: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(fields.split()):
        raise ValueError("closed record requires exactly: " + fields)
    return value


def integer(value: Any, *, minimum: int = 0, maximum: int = 2**53) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("integer base units outside finite range")
    return value


def text(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("nonempty bounded text required")
    return value


def digest(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("SHA256 digest required")
    return value


def integers(value: Any, keys: Any) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("every declared unit must be present")
    return {k: integer(v) for k, v in value.items()}


def unique(values: Any, *, limit: int = 128) -> list[str]:
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError("bounded list required")
    if any(not isinstance(v, str) for v in values) or len(set(values)) != len(values):
        raise ValueError("unique strings required")
    return [text(v) for v in values]


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    from ccr.schemas.validation import validate_instance

    validation = validate_instance("growth-profile", raw)
    if not validation.ok:
        raise ValueError("invalid growth profile: " + str(validation.errors))
    closed(raw, "schema_version policy base growth")
    if raw["schema_version"] != PROFILE or raw["policy"] != "verified_growth_v1":
        raise ValueError("explicit verified_growth_v1 profile required")
    base = normalize_config(raw["base"])
    g = copy.deepcopy(raw["growth"])
    closed(
        g,
        "study_id checkpoint_digest evidence_mode targets units horizon_seconds "
        "max_steps candidate_limit attribution_seconds window_end receivers assets "
        "actions bundles scenarios verifier_stages quota cost_order "
        "diagnostic_budget comparison",
    )
    validate_identifier(g["study_id"], field="study")
    digest(g["checkpoint_digest"])
    if g["evidence_mode"] not in {"synthetic", "observational"}:
        raise ValueError("explicit evidence mode required")
    integers(g["targets"], ["task", "research"])
    if not all(g["targets"].values()):
        raise ValueError("positive registered task and research targets required")
    closed(g["units"], "task research costs")
    text(g["units"]["task"])
    text(g["units"]["research"])
    costs = base["resource_limits"]
    if set(g["units"]["costs"]) != set(costs):
        raise ValueError("cost units must match base resources")
    for unit in g["units"]["costs"].values():
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", text(unit)) is None:
            raise ValueError("malformed cost unit")
    integers(costs, costs)
    integers(base["evaluation"]["resource_envelope"], costs)
    integer(g["max_steps"], minimum=1, maximum=8)
    integer(g["horizon_seconds"], minimum=1, maximum=86400)
    integer(g["candidate_limit"], minimum=1, maximum=128)
    integer(g["attribution_seconds"], minimum=1, maximum=31536000)
    if timestamp(g["window_end"]) > timestamp(base["deadline"]):
        raise ValueError("attribution window must fit registered deadline")
    if set(unique(g["cost_order"])) != set(costs):
        raise ValueError("declare the complete typed cost tie order")
    integers(g["diagnostic_budget"], costs)
    if base["max_inflight"] != 1:
        raise ValueError("growth v1 uses one verified immediate step per run")
    receivers = g["receivers"]
    if not isinstance(receivers, dict) or not 1 <= len(receivers) <= 32:
        raise ValueError("bounded receiver declarations required")
    for receiver, spec in receivers.items():
        text(receiver)
        closed(
            spec,
            "mission_id context_sha256 domain protocol evaluator quality cross_mission_allowed",
        )
        validate_identifier(spec["mission_id"], field="receiver mission")
        digest(spec["context_sha256"])
        for f in ("domain", "protocol", "evaluator", "quality"):
            text(spec[f])
        if type(spec["cross_mission_allowed"]) is not bool:
            raise ValueError("cross mission grant must be boolean")
    assets = g["assets"]
    if not isinstance(assets, dict) or len(assets) > 64:
        raise ValueError("bounded asset declarations required")
    for asset, spec in assets.items():
        digest(asset)
        closed(spec, "version source_mission receivers parents external_inputs expires_at")
        text(spec["version"])
        validate_identifier(spec["source_mission"], field="asset mission")
        if not set(unique(spec["receivers"])) <= set(receivers):
            raise ValueError("unknown receiver scope")
        for parent in unique(spec["parents"]):
            if parent not in assets or parent == asset:
                raise ValueError("unknown or self parent")
        unique(spec["external_inputs"])
        timestamp(spec["expires_at"])
    # Explicit acyclic coalitions; no recursive self-credit.
    remaining = set(assets)
    while remaining:
        removable = {a for a in remaining if not (set(assets[a]["parents"]) & remaining)}
        if not removable:
            raise ValueError("cyclic lineage")
        remaining -= removable
    stages = g["verifier_stages"]
    if not isinstance(stages, dict) or not 1 <= len(stages) <= 8:
        raise ValueError("bounded verifier stages required")
    for stage in stages.values():
        closed(
            stage,
            "domains quality service_units_per_second fresh_until independence_groups "
            "exposure_groups dependence",
        )
        unique(stage["domains"])
        text(stage["quality"])
        if stage["service_units_per_second"] is not None:
            integer(stage["service_units_per_second"])
        timestamp(stage["fresh_until"])
        unique(stage["independence_groups"])
        unique(stage["exposure_groups"])
        if stage["dependence"] not in {"unknown", "shared", "declared_independent"}:
            raise ValueError("dependence must remain explicit")
    actions = g["actions"]
    if not isinstance(actions, dict) or not 1 <= len(actions) <= 64:
        raise ValueError("1..64 finite actions required")
    arms = {a["intervention_id"]: a for a in base["interventions"]}
    targets = {t["target_id"] for t in base["task_manifest"]}
    for name, action in actions.items():
        validate_identifier(name, field="action")
        closed(
            action,
            "kind intervention_id target_id receiver requires produces gains "
            "duration_seconds cleanup_seconds cleanup_cost capacity verification_work "
            "authority evidence_refs service_measurement",
        )
        if action["kind"] not in KINDS or action["intervention_id"] not in arms:
            raise ValueError("unsupported intervention")
        arm = arms[action["intervention_id"]]
        if arm["kind"] != MAPPING[action["kind"]]:
            raise ValueError("intervention worker role mismatch")
        if action["target_id"] not in targets or action["receiver"] not in receivers:
            raise ValueError("unknown target or receiver")
        integers(arm["resource_upper_bound"], costs)
        integers(action["cleanup_cost"], costs)
        integers(action["gains"], g["targets"])
        if action["kind"] not in {"service", "reuse"} and any(action["gains"].values()):
            raise ValueError("preparation is not observed service")
        integer(action["duration_seconds"], minimum=1, maximum=86400)
        integer(action["cleanup_seconds"], minimum=1, maximum=86400)
        if action["authority"] not in {"local_only", "operation_approval_required"}:
            raise ValueError("unsupported authority")
        if ("operation_plan" in arm) != (action["authority"] == "operation_approval_required"):
            raise ValueError("external work must use existing operation approval")
        for a in unique(action["requires"]):
            if a not in assets:
                raise ValueError("unknown prerequisite asset")
        if action["produces"] is not None and action["produces"] not in assets:
            raise ValueError("undeclared output asset")
        integers(action["service_measurement"], stages)
        if (
            any(action["service_measurement"].values())
            and action["kind"] != "verification_investment"
        ):
            raise ValueError("service measurements require verifier investment")
        if action["kind"] == "verification_investment" and action["produces"] is None:
            raise ValueError("service investment needs a versioned evidence asset")
        if action["produces"] and set(assets[action["produces"]]["parents"]) != set(
            action["requires"]
        ):
            raise ValueError("formation prerequisites must bind every parent")
        integers(action["verification_work"], stages)
        unique(action["evidence_refs"])
        if not action["evidence_refs"]:
            raise ValueError("forecast provenance required")
    q = g["quota"]
    closed(q, "pool_id pool_budget pool_capacity budget capacity allocation_ref")
    validate_identifier(q["pool_id"], field="pool")
    text(q["allocation_ref"])
    for f in ("pool_budget", "budget"):
        integers(q[f], costs)
    if q["budget"] != costs:
        raise ValueError("quota must cover the registered physical run budget")
    for f in ("pool_capacity", "capacity"):
        integers(q[f], q["pool_capacity"])
    for action in actions.values():
        integers(action["capacity"], q["capacity"])
    bundles = g["bundles"]
    if not isinstance(bundles, dict) or not 1 <= len(bundles) <= 128:
        raise ValueError("1..128 bundles required")
    for name, steps in bundles.items():
        text(name)
        if not unique(steps, limit=g["max_steps"]) or not set(steps) <= set(actions):
            raise ValueError("bundle must contain known, unique actions")
    scenarios = g["scenarios"]
    if not isinstance(scenarios, dict) or not 1 <= len(scenarios) <= 16:
        raise ValueError("1..16 explicit joint scenarios required; empty means inconsistent")
    for scenario in scenarios.values():
        if not isinstance(scenario, dict) or set(scenario) != set(actions):
            raise ValueError("joint scenarios must cover every action")
        for effect in scenario.values():
            if effect is not None and type(effect) is not bool:
                raise ValueError("success forecast is boolean or unknown")
    c = g["comparison"]
    closed(c, "restricted_bundles independent_unit uncertainty_method")
    if not unique(c["restricted_bundles"]) or not set(c["restricted_bundles"]) <= set(bundles):
        raise ValueError("registered restricted comparator required")
    text(c["independent_unit"])
    if c["uncertainty_method"] != "unresolved":
        raise ValueError("growth v1 does not implement a causal or statistical estimator")
    base["growth"] = g
    base["config_digest"] = sha256_json(raw)
    return base
