# SPDX-License-Identifier: Apache-2.0
"""ASI-proxy threshold evaluation."""

from __future__ import annotations

from typing import Any


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
        "accepted_packet_count": observation.get("positive_packet_count", 0)
        >= threshold.get("minimum_accepted_packet_count", 1),
        "effective_edge_count": observation.get("effective_edge_count", 0)
        >= threshold.get("minimum_effective_edge_count", 1),
        "execution_available_path_density": observation.get("execution_available_path_density", 0.0)
        >= threshold.get("minimum_execution_available_path_density", 0.1),
        "closure_witness_count": observation.get("closure_witness_count", 0)
        >= threshold.get("minimum_closure_witness_count", 0),
        "residual_debt": observation.get("residual_debt", 0.0)
        <= threshold.get("maximum_residual_debt", 0.0),
        "false_liquidity_load": observation.get("false_liquidity_load", 1.0)
        <= threshold.get("maximum_false_liquidity_load", 0.5),
        "salience_obstruction": observation.get("salience_obstruction_load", 1.0)
        <= threshold.get("maximum_salience_obstruction", 0.5),
        "verification_throughput": observation.get("verification_throughput", 0.0)
        >= threshold.get("minimum_verification_throughput", 0.1),
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
    gaps = [
        float(observation.get("positive_packet_count", 0))
        - float(threshold.get("minimum_accepted_packet_count", 1)),
        float(observation.get("effective_edge_count", 0))
        - float(threshold.get("minimum_effective_edge_count", 1)),
        float(observation.get("execution_available_path_density", 0.0))
        - float(threshold.get("minimum_execution_available_path_density", 0.1)),
        float(observation.get("verification_throughput", 0.0))
        - float(threshold.get("minimum_verification_throughput", 0.1)),
        float(threshold.get("maximum_residual_debt", 0.0))
        - float(observation.get("residual_debt", 0.0)),
        float(threshold.get("maximum_false_liquidity_load", 0.5))
        - float(observation.get("false_liquidity_load", 1.0)),
    ]
    if not component_status.get("not_executed", True):
        gaps.append(-1.0)
    return min(gaps) if gaps else 0.0
