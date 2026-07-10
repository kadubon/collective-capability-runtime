# SPDX-License-Identifier: Apache-2.0
"""Generic preregistered collective-capability evaluation protocol."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ccr.ids import stable_id, validate_identifier
from ccr.io import read_json, write_json_atomic
from ccr.safe_io import require_path_within_root

_MANIFEST_FIELDS = {
    "evaluation_design",
    "evaluator_plugin",
    "outcome_schema",
    "resource_envelope",
    "task_manifest",
}


def register_experiment(root: Path, *, suite: str, manifest_path: Path) -> dict[str, Any]:
    validate_identifier(suite, field="experiment suite")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ValueError("experiment manifest must be a JSON object")
    missing = sorted(_MANIFEST_FIELDS - manifest.keys())
    if missing:
        raise ValueError(f"experiment manifest missing fields: {', '.join(missing)}")
    design = manifest.get("evaluation_design")
    if not isinstance(design, dict) or design.get("mode") not in {
        "confidence_sequence",
        "fixed_horizon",
    }:
        raise ValueError("evaluation_design.mode must be confidence_sequence or fixed_horizon")
    if manifest.get("pre_registered") is not True:
        raise ValueError("experiment manifest must explicitly set pre_registered=true")
    payload = {
        **manifest,
        "manifest_id": stable_id("experiment-manifest", suite, manifest),
        "schema_version": "ccr.experiment_manifest.v1",
        "suite": suite,
    }
    path = require_path_within_root(
        root / "experiments" / suite / "manifest.json", root, field="experiment path"
    )
    write_json_atomic(path, payload, overwrite=False)
    return {"manifest": payload, "ok": True, "path": str(path)}


def ingest_experiment_result(
    root: Path, *, suite: str, label: str, result_path: Path
) -> dict[str, Any]:
    validate_identifier(suite, field="experiment suite")
    if label not in {"baseline", "collective"}:
        raise ValueError("experiment label must be baseline or collective")
    manifest_path = require_path_within_root(
        root / "experiments" / suite / "manifest.json", root, field="experiment path"
    )
    manifest = read_json(manifest_path)
    result = read_json(result_path)
    if not isinstance(manifest, dict) or not isinstance(result, dict):
        raise ValueError("experiment manifest and result must be JSON objects")
    required = {"outcomes", "resource_envelope", "seed", "tool_model_version"}
    missing = sorted(required - result.keys())
    if missing:
        raise ValueError(f"experiment result missing fields: {', '.join(missing)}")
    if result.get("resource_envelope") != manifest.get("resource_envelope"):
        raise ValueError("experiment result resource envelope does not match registration")
    payload = {
        **result,
        "label": label,
        "manifest_id": manifest.get("manifest_id"),
        "schema_version": "ccr.experiment_result.v1",
    }
    destination = require_path_within_root(
        root / "experiments" / suite / f"{label}.json", root, field="experiment path"
    )
    write_json_atomic(destination, payload)
    return {"ok": True, "path": str(destination), "result": payload}


def compare_experiment_results(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    base_env = baseline.get("resource_envelope")
    candidate_env = candidate.get("resource_envelope")
    matched = isinstance(base_env, dict) and base_env == candidate_env
    base_samples = _samples(baseline)
    candidate_samples = _samples(candidate)
    count = min(len(base_samples), len(candidate_samples))
    differences = [candidate_samples[index] - base_samples[index] for index in range(count)]
    delta = _mean(differences) if matched and differences else None
    design = candidate.get("evaluation_design") or baseline.get("evaluation_design")
    interval, design_valid = _evaluation_interval(differences, design)
    metrics = {
        "best_solo_uplift": _difference(
            _mean(candidate_samples),
            _number(candidate.get("best_solo_score"), _mean(base_samples)),
        ),
        "communication_cost": _number(candidate.get("communication_cost")),
        "effective_agent_count": _effective_agent_count(candidate.get("agent_weights")),
        "error_correlation": _number(candidate.get("error_correlation")),
        "residual_half_life": _residual_half_life(candidate),
        "resource_matched_collective_uplift": delta,
        "time_to_checked": _number(candidate.get("time_to_checked")),
        "verification_cost": _number(candidate.get("verification_cost")),
        "verification_yield": _ratio(
            candidate.get("accepted_verifications"), candidate.get("verification_calls")
        ),
    }
    lower_bound = interval[0] if interval is not None else None
    acceleration_admissible = bool(
        matched and design_valid and lower_bound is not None and lower_bound > 0
    )
    return {
        "accepted": matched,
        "acceleration_claim_admissible": acceleration_admissible,
        "confidence_interval": interval,
        "delta": delta,
        "evaluation_design_valid": design_valid,
        "limitations": [
            "Metrics are finite-protocol and resource-envelope relative.",
            "Raw agent count and candidate volume do not count as progress.",
        ],
        "metrics": metrics,
        "ok": matched,
        "resource_matched": matched,
        "sample_count": count,
        "schema_version": "ccr.experiment_compare.v2",
        "settled": False,
    }


def _evaluation_interval(differences: list[float], design: Any) -> tuple[list[float] | None, bool]:
    if not differences or not isinstance(design, dict) or design.get("pre_registered") is not True:
        return None, False
    alpha = _number(design.get("alpha"), 0.05)
    if alpha is None or not 0 < alpha < 1:
        return None, False
    count = len(differences)
    mean = _mean(differences)
    if mean is None:
        return None, False
    mode = design.get("mode")
    if mode == "fixed_horizon":
        horizon = design.get("horizon")
        if not isinstance(horizon, int) or horizon < 1 or count != horizon:
            return None, False
        radius = 2 * math.sqrt(math.log(2 / alpha) / (2 * count))
    elif mode == "confidence_sequence":
        alpha_t = alpha / (count * (count + 1))
        radius = 2 * math.sqrt(math.log(2 / alpha_t) / (2 * count))
    else:
        return None, False
    return [max(-1.0, mean - radius), min(1.0, mean + radius)], True


def _samples(result: dict[str, Any]) -> list[float]:
    outcomes = result.get("outcomes")
    if isinstance(outcomes, list):
        return [
            float(item) for item in outcomes if _number(item) is not None and 0 <= float(item) <= 1
        ]
    score = _number(result.get("success_score"))
    return [score] if score is not None else []


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _number(value: Any, default: float | None = None) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    number = float(value)
    return number if math.isfinite(number) else default


def _difference(left: float | None, right: float | None) -> float | None:
    return left - right if left is not None and right is not None else None


def _ratio(numerator: Any, denominator: Any) -> float | None:
    left = _number(numerator)
    right = _number(denominator)
    return left / right if left is not None and right is not None and right > 0 else None


def _effective_agent_count(value: Any) -> float | None:
    if not isinstance(value, list):
        return None
    weights = [number for item in value if (number := _number(item)) is not None and number > 0]
    denominator = sum(item * item for item in weights)
    return (sum(weights) ** 2) / denominator if denominator > 0 else None


def _residual_half_life(result: dict[str, Any]) -> float | None:
    opened = _number(result.get("residuals_opened"))
    remaining = _number(result.get("residuals_remaining"))
    elapsed = _number(result.get("elapsed_seconds"))
    if (
        opened is None
        or remaining is None
        or elapsed is None
        or opened <= remaining
        or remaining <= 0
    ):
        return None
    return elapsed * math.log(2) / math.log(opened / remaining)
