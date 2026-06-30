# SPDX-License-Identifier: Apache-2.0
"""Collective phase certificate candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.phase.graph import build_effective_graph
from ccr.phase.observe import build_phase_observation
from ccr.phase.threshold import default_threshold, evaluate_threshold
from ccr.residuals.store import iter_residuals


def build_certificate_candidate(
    root: Path,
    *,
    graph: dict[str, Any] | None = None,
    observation: dict[str, Any] | None = None,
    threshold_status: dict[str, Any] | None = None,
    threshold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a protocol-relative ASI-proxy certificate candidate."""

    graph = graph or build_effective_graph(root)
    observation = observation or build_phase_observation(root, graph)
    threshold = threshold or default_threshold()
    threshold_status = threshold_status or evaluate_threshold(observation, threshold)
    blocking_residuals = [
        item for item in iter_residuals(root, status="open") if item.get("blocking")
    ]
    defects = [
        {
            "component": item,
            "defect_id": f"defect:{item}",
            "defect_type": "threshold_component_failed",
            "required_remediation": f"Improve or repair phase component {item}.",
            "residual_preserved": True,
        }
        for item in threshold_status.get("failed_components", [])
    ]
    for residual in blocking_residuals:
        defects.append(
            {
                "component": "residual",
                "defect_id": f"defect:{residual.get('residual_id')}",
                "defect_type": "blocking_residual",
                "required_remediation": str(residual.get("repair_hint", "Resolve residual.")),
                "residual_preserved": True,
            }
        )
    accepted = bool(threshold_status.get("accepted")) and not blocking_residuals
    return {
        "accepted": accepted,
        "certificate_id": f"collective-phase-certificate:{observation.get('observation_id')}",
        "certificate_status": "accepted" if accepted else "abstain",
        "defects": defects,
        "finite_requirements_passed": accepted,
        "graph_id": graph.get("graph_id", ""),
        "observation_id": observation.get("observation_id", ""),
        "operationally_usable": accepted,
        "protocol_relative_only": True,
        "proves_physical_or_oracle_truth": False,
        "proves_real_asi": False,
        "reasons": [] if accepted else ["threshold or residual obligations remain unresolved"],
        "schema_version": "ccr.phase_certificate_candidate.v1",
        "settled": False,
        "threshold_status": threshold_status,
        "workflow_usable": bool(graph.get("nodes")),
    }
