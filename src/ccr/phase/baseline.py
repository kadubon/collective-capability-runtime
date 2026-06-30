# SPDX-License-Identifier: Apache-2.0
"""Resource-matched baseline comparison."""

from __future__ import annotations

from typing import Any

from ccr.residuals.model import build_residual


def compare_observation_to_baseline(
    baseline: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    """Compare a candidate phase observation against a resource-matched baseline."""

    baseline_envelope = baseline.get("resource_envelope", {})
    candidate_envelope = observation.get("resource_envelope", {})
    metrics = baseline.get("metrics", {})
    deltas: dict[str, float] = {}
    for key, baseline_value in metrics.items():
        if isinstance(baseline_value, int | float):
            candidate_value = observation.get(key)
            if candidate_value is None:
                candidate_value = observation.get("phase_gap_vector", {}).get(key, 0.0)
            if isinstance(candidate_value, int | float):
                deltas[key] = float(candidate_value) - float(baseline_value)
    resource_matched = baseline_envelope == candidate_envelope
    residual_ready = None
    if not resource_matched:
        residual_ready = build_residual(
            kind="settlement_blocker",
            description="Baseline resource envelope does not match candidate observation.",
            blocking=True,
            object_type="phase",
            object_id=str(observation.get("observation_id", "unknown")),
            refs=[str(baseline.get("baseline_id", "baseline"))],
            source="ccr.phase.compare",
            repair_hint="Compare only observations with the same declared resource envelope.",
        )
    improved = bool(deltas) and all(value >= 0 for value in deltas.values())
    return {
        "accepted": resource_matched and improved and observation.get("residual_debt", 0.0) == 0.0,
        "baseline_id": baseline.get("baseline_id", "baseline"),
        "candidate_observation_id": observation.get("observation_id", ""),
        "comparison_id": (
            f"comparison:{baseline.get('baseline_id', 'baseline')}:"
            f"{observation.get('observation_id', 'unknown')}"
        ),
        "deltas": dict(sorted(deltas.items())),
        "improved_relative_to_baseline": improved,
        "protocol_relative_only": True,
        "residual_ready": residual_ready,
        "resource_matched": resource_matched,
        "schema_version": "ccr.phase_comparison.v1",
        "settled": False,
    }
