# SPDX-License-Identifier: Apache-2.0
"""Phase observation metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.phase.graph import build_effective_graph
from ccr.residuals.store import iter_residuals
from ccr.runtime.config import load_config


def build_phase_observation(root: Path, graph: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build deterministic protocol-relative phase observation metrics."""

    graph = graph or build_effective_graph(root)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    residuals = list(iter_residuals(root, status="open"))
    accepted_packet_count = sum(1 for node in nodes if node.get("accepted"))
    positive_packet_count = int(graph.get("accepted_packet_capital", 0))
    candidate_only_count = int(graph.get("candidate_only_packets", 0))
    node_count = len(nodes)
    total_packets = max(1, node_count)
    effective_edge_count = int(graph.get("positive_edge_count", 0))
    execution_available_path_count = int(graph.get("execution_available_path_count", 0))
    executed_path_count = int(graph.get("executed_path_count", 0))
    closure_witness_count = _cycle_proxy(edges)
    residual_debt = float(len(residuals) + sum(1 for item in residuals if item.get("blocking")))
    false_liquidity_load = candidate_only_count / max(
        1, candidate_only_count + positive_packet_count
    )
    non_contributing = int(graph.get("non_contributing_volume", 0))
    waste_load = non_contributing / total_packets
    salience_obstruction = _salience_obstruction(residuals, total_packets)
    verification_throughput = accepted_packet_count / max(
        1, accepted_packet_count + candidate_only_count
    )
    execution_available_path_density = execution_available_path_count / max(
        1, positive_packet_count
    )
    closure_score = min(1.0, closure_witness_count / max(1, positive_packet_count))
    phase_gap_vector = {
        "accepted_packet_count": float(positive_packet_count),
        "effective_edge_count": float(effective_edge_count),
        "execution_available_path_density": execution_available_path_density,
        "autocatalytic_closure_score": closure_score,
        "verification_throughput": verification_throughput,
        "residual_debt": residual_debt,
        "false_liquidity_load": false_liquidity_load,
        "salience_obstruction_load": salience_obstruction,
    }
    coordinate_status = {
        "accepted_packet_count": "known",
        "closure_witness_count": "known" if positive_packet_count else "unknown",
        "effective_edge_count": "known",
        "execution_available_path_density": "known" if positive_packet_count else "unknown",
        "false_liquidity_load": "known"
        if candidate_only_count + positive_packet_count
        else "unknown",
        "residual_debt": "known",
        "salience_obstruction_load": "known" if node_count else "unknown",
        "verification_throughput": "known"
        if accepted_packet_count + candidate_only_count
        else "unknown",
    }
    config = load_config(root)
    observation_id = stable_id("phase-observation", graph.get("graph_id"), phase_gap_vector)
    return {
        "accepted": bool(positive_packet_count and effective_edge_count),
        "accepted_packet_count": accepted_packet_count,
        "autocatalytic_closure_score": closure_score,
        "candidate_only_packet_count": candidate_only_count,
        "closure_witness_count": closure_witness_count,
        "coordinate_status": coordinate_status,
        "effective_edge_count": effective_edge_count,
        "effective_node_count": len(nodes),
        "executed_path_count": executed_path_count,
        "execution_available_path_count": execution_available_path_count,
        "execution_available_path_density": execution_available_path_density,
        "false_liquidity_load": false_liquidity_load,
        "generated_at": str(config.get("created_at", "1970-01-01T00:00:00Z")),
        "graph_id": graph.get("graph_id", ""),
        "observation_id": observation_id,
        "phase_gap_vector": phase_gap_vector,
        "positive_packet_count": positive_packet_count,
        "protocol_relative_only": True,
        "proves_real_asi": False,
        "residual_debt": residual_debt,
        "resource_envelope": config.get("resource_envelope", {}),
        "salience_obstruction_load": salience_obstruction,
        "schema_version": "ccr.phase_observation.v1",
        "settled": False,
        "threshold_distance": 0.0,
        "verification_throughput": verification_throughput,
        "waste_load": waste_load,
        "workflow_usable": bool(nodes),
    }


def _cycle_proxy(edges: list[dict[str, Any]]) -> int:
    pairs = {
        (tuple(edge.get("source_node_ids", [])), str(edge.get("target_node_id", "")))
        for edge in edges
        if edge.get("positive_contribution")
    }
    count = 0
    for sources, target in pairs:
        for source in sources:
            if ((target,), source) in pairs:
                count += 1
    return count // 2


def _salience_obstruction(residuals: list[dict[str, Any]], total_packets: int) -> float:
    blocked = sum(
        1
        for item in residuals
        if item.get("kind") in {"queue_overload", "negative_liquidity", "settlement_blocker"}
    )
    return blocked / max(1, total_packets)
