# SPDX-License-Identifier: Apache-2.0
"""ASI-proxy threshold evaluation."""

from __future__ import annotations

from typing import Any, cast


def default_threshold(profile: str = "development") -> dict[str, Any]:
    """Return a conservative development threshold."""

    return {
        "maximum_false_liquidity_load": 0.5,
        "maximum_residual_debt": 0.0,
        "maximum_salience_obstruction": 0.5,
        "minimum_accepted_packet_count": 1,
        "minimum_closure_witness_count": 0,
        "minimum_effective_edge_count": 1,
        "minimum_execution_available_path_density": 0.1,
        "minimum_verification_throughput": 0.1,
        "profile": profile,
        "required_authority_status": "explicit-scope-bounded",
        "required_identity_mode": "declared",
        "required_rollback_availability": True,
        "schema_version": "ccr.asi_proxy_threshold.v1",
        "threshold_id": f"asi-proxy-{profile}",
    }


def evaluate_threshold(observation: dict[str, Any], threshold: dict[str, Any]) -> dict[str, Any]:
    """Evaluate an observation against an ASI-proxy threshold."""

    component_status = {
        "accepted_packet_count": _at_least(
            observation, "positive_packet_count", threshold, "minimum_accepted_packet_count"
        ),
        "effective_edge_count": _at_least(
            observation, "effective_edge_count", threshold, "minimum_effective_edge_count"
        ),
        "execution_available_path_density": _at_least(
            observation,
            "execution_available_path_density",
            threshold,
            "minimum_execution_available_path_density",
        ),
        "closure_witness_count": _at_least(
            observation, "closure_witness_count", threshold, "minimum_closure_witness_count"
        ),
        "residual_debt": _at_most(observation, "residual_debt", threshold, "maximum_residual_debt"),
        "false_liquidity_load": _at_most(
            observation, "false_liquidity_load", threshold, "maximum_false_liquidity_load"
        ),
        "salience_obstruction": _at_most(
            observation, "salience_obstruction_load", threshold, "maximum_salience_obstruction"
        ),
        "verification_throughput": _at_least(
            observation, "verification_throughput", threshold, "minimum_verification_throughput"
        ),
        "not_executed": observation.get("executed_path_count", 0) == 0,
        "non_claims_preserved": not observation.get("proves_real_asi", False),
    }
    failed = [key for key, value in component_status.items() if not value]
    accepted = not failed
    threshold_distance = _threshold_distance(observation, threshold, component_status)
    return {
        "accepted": accepted,
        "abstention_reasons": [f"component failed: {key}" for key in failed],
        "certificate_status": "accepted" if accepted else "abstain",
        "component_status": component_status,
        "failed_components": failed,
        "observation_id": observation.get("observation_id", ""),
        "protocol_relative_only": True,
        "proves_real_asi": False,
        "rejection_reasons": [],
        "schema_version": "ccr.asi_proxy_threshold_status.v1",
        "settled": False,
        "status_id": f"threshold-status:{observation.get('observation_id', 'unknown')}",
        "threshold": threshold,
        "threshold_distance": threshold_distance,
    }


def _threshold_distance(
    observation: dict[str, Any], threshold: dict[str, Any], component_status: dict[str, bool]
) -> float:
    pairs = [
        ("positive_packet_count", "minimum_accepted_packet_count", 1.0),
        ("effective_edge_count", "minimum_effective_edge_count", 1.0),
        ("execution_available_path_density", "minimum_execution_available_path_density", 1.0),
        ("verification_throughput", "minimum_verification_throughput", 1.0),
        ("residual_debt", "maximum_residual_debt", -1.0),
        ("false_liquidity_load", "maximum_false_liquidity_load", -1.0),
    ]
    gaps: list[float] = []
    for observation_key, threshold_key, direction in pairs:
        observed = observation.get(observation_key)
        limit = threshold.get(threshold_key)
        if (
            _coordinate_known(observation, observation_key)
            and _is_number(observed)
            and _is_number(limit)
        ):
            gaps.append(
                direction * (float(cast(int | float, observed)) - float(cast(int | float, limit)))
            )
        else:
            gaps.append(-1.0)
    if not component_status.get("not_executed", True):
        gaps.append(-1.0)
    return min(gaps) if gaps else 0.0


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int | float)


def _at_least(
    observation: dict[str, Any], observation_key: str, threshold: dict[str, Any], threshold_key: str
) -> bool:
    observed = observation.get(observation_key)
    limit = threshold.get(threshold_key)
    return (
        _coordinate_known(observation, observation_key)
        and _is_number(observed)
        and _is_number(limit)
        and float(cast(int | float, observed)) >= float(cast(int | float, limit))
    )


def _at_most(
    observation: dict[str, Any], observation_key: str, threshold: dict[str, Any], threshold_key: str
) -> bool:
    observed = observation.get(observation_key)
    limit = threshold.get(threshold_key)
    return (
        _coordinate_known(observation, observation_key)
        and _is_number(observed)
        and _is_number(limit)
        and float(cast(int | float, observed)) <= float(cast(int | float, limit))
    )


def _coordinate_known(observation: dict[str, Any], key: str) -> bool:
    statuses = observation.get("coordinate_status")
    if not isinstance(statuses, dict):
        return True
    return statuses.get(key) == "known"
