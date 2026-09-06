# SPDX-License-Identifier: Apache-2.0
"""Immutable optimizer configuration and finite input validation."""

from __future__ import annotations

import base64
import copy
import math
from datetime import datetime
from typing import Any

from ccr.ids import sha256_json, validate_identifier
from ccr.schemas.validation import validate_instance

KINDS = {
    "verification": "verifier",
    "residual_repair": "integrator",
    "independent_proposal": "generator",
    "distillation": "integrator",
    "measurement": "benchmark_runner",
}
WORKFLOWS = {
    "verification": "Independently verify the referenced artifact and retain failed checks.",
    "residual_repair": "Repair the referenced residual using artifact-bound independent evidence.",
    "independent_proposal": "Use CCR workcells for independent proposal, reveal, and critique.",
    "distillation": "Distill the artifact into a reusable capability packet with provenance.",
    "measurement": "Acquire missing measurements or a resource-matched preregistered baseline.",
}
CONFIG_VERSION = "ccr.optimizer_config.v1"
PLAN_VERSION = "ccr.optimizer_plan.v1"
TRIAL_VERSION = "ccr.optimizer_trial.v1"
RESULT_VERSION = "ccr.optimizer_result.v1"
REPORT_VERSION = "ccr.optimizer_report.v1"


def number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError("resource and outcome values must be finite numbers")
    if value < 0:
        raise ValueError("resource and outcome values must be nonnegative")
    return float(value)


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    return parsed


def vector(value: Any, keys: dict[str, Any]) -> dict[str, float]:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("all resource dimensions must be explicitly supplied")
    return {key: number(value[key]) for key in keys}


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("optimizer config must be a JSON object")
    config = copy.deepcopy(raw)
    config.setdefault("schema_version", CONFIG_VERSION)
    config.setdefault("epsilon", 0.2)
    config.setdefault("diagnostic_reserve", 0.2)
    config.setdefault("policy_version", 1)
    validation = validate_instance("optimizer-config", config)
    if not validation.ok:
        raise ValueError("; ".join(issue.message for issue in validation.errors))
    number(config["epsilon"])
    number(config["diagnostic_reserve"])
    number(config["evaluation"]["alpha"])
    timestamp(config["deadline"])
    limits = config["resource_limits"]
    vector(limits, limits)
    if not limits or any(number(value) <= 0 for value in limits.values()):
        raise ValueError("resource limits must be positive")
    if config["effort_resource"] not in limits:
        raise ValueError("effort_resource must name a resource dimension")
    targets = config["task_manifest"]
    target_ids = [item["target_id"] for item in targets]
    if len(set(target_ids)) != len(target_ids):
        raise ValueError("duplicate target_id")
    for item in targets:
        validate_identifier(item["target_id"], field="target_id")
    evaluation = config["evaluation"]
    holdout = evaluation["holdout_tasks"]
    if len(set(holdout)) != len(holdout) or not set(holdout) < set(target_ids):
        raise ValueError("holdout tasks must be a unique proper subset of task_manifest")
    if evaluation["horizon"] != len(holdout):
        raise ValueError("fixed horizon must equal the number of holdout tasks")
    envelope = vector(evaluation["resource_envelope"], limits)
    if any(envelope[k] <= 0 or 2 * envelope[k] >= limits[k] for k in limits):
        raise ValueError("two evaluation envelopes must leave positive training resources")
    ids = [arm["intervention_id"] for arm in config["interventions"]]
    if len(set(ids)) != len(ids) or evaluation["baseline_intervention"] not in ids:
        raise ValueError("intervention ids must be unique and baseline must be registered")
    for arm in config["interventions"]:
        validate_identifier(arm["intervention_id"], field="intervention_id")
        cost = vector(arm["resource_upper_bound"], limits)
        if cost[config["effort_resource"]] <= 0:
            raise ValueError("intervention effort upper bound must be positive")
        if arm["kind"] not in KINDS:
            raise ValueError("unsupported intervention kind")
        if "operation_plan" in arm:
            if "calls" in cost and cost["calls"] < 1:
                raise ValueError("HTTP trials must reserve at least one call")
            plan = arm["operation_plan"]
            if plan.get("schema_version") != "ccr.trc_operation_plan.v1":
                raise ValueError("operation_plan must use the existing TRC contract")
            if len(plan.get("operations", [])) != 1:
                raise ValueError("one bounded operation per optimizer trial is required")
    for key in config["trusted_verifiers"].values():
        try:
            if len(base64.b64decode(key, validate=True)) != 32:
                raise ValueError("verifier keys must be Ed25519 public keys")
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid verifier key") from exc
    config["config_digest"] = sha256_json(config)
    return config
