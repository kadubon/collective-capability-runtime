# SPDX-License-Identifier: Apache-2.0
"""Effective packet graph construction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.packets.store import iter_packets
from ccr.phase.eligibility import packet_eligibility
from ccr.runtime.config import load_config


def build_effective_graph(root: Path) -> dict[str, Any]:
    """Build a protocol-relative effective packet graph from local packets."""

    packets = iter_packets(root)
    nodes: list[dict[str, Any]] = []
    packet_by_id: dict[str, dict[str, Any]] = {}
    eligibility_by_id: dict[str, dict[str, Any]] = {}
    for packet in packets:
        packet_id = str(packet.get("packet_id", "unknown"))
        eligibility = packet_eligibility(root, packet)
        packet_by_id[packet_id] = packet
        eligibility_by_id[packet_id] = eligibility
        contribution_status = _contribution_status(eligibility)
        nodes.append(
            {
                "accepted": bool(eligibility["accepted_or_certificate_admissible"]),
                "candidate_only": bool(eligibility["candidate_only"]),
                "contribution": contribution_status,
                "eligibility": eligibility,
                "executed": False,
                "execution_available": bool(eligibility["execution_available"]),
                "node_id": packet_id,
                "packet_id": packet_id,
                "positive_contribution": bool(eligibility["positive_contribution"]),
                "reasons": eligibility["reasons"],
                "settled": packet.get("status") == "settled",
                "status": packet.get("status", "candidate"),
                "summary": packet.get("summary", ""),
            }
        )

    edges = _build_edges(packet_by_id, eligibility_by_id)
    positive_nodes = [node for node in nodes if node["positive_contribution"]]
    diagnostic_nodes = [node for node in nodes if not node["positive_contribution"]]
    positive_edges = [edge for edge in edges if edge["positive_contribution"]]
    graph_id = stable_id("graph:effective", [node["node_id"] for node in nodes], edges)
    config = load_config(root)
    return {
        "accepted": bool(positive_nodes),
        "accepted_packet_capital": len(positive_nodes),
        "candidate_only_packets": sum(1 for node in nodes if node["candidate_only"]),
        "diagnostic_packet_count": len(diagnostic_nodes),
        "edge_count_by_relation": _count_by(edges, "relation_type"),
        "edges": edges,
        "executed_path_count": 0,
        "execution_available_path_count": sum(
            1 for node in positive_nodes if node["execution_available"]
        ),
        "generated_at": str(config.get("created_at", "1970-01-01T00:00:00Z")),
        "graph_id": graph_id,
        "graph_safety_boundary": [
            "raw packet volume is diagnostic only",
            "candidate-only nodes do not improve positive phase components",
            "execution-available paths are not executed paths",
            "graph construction does not settle claims",
        ],
        "missing_edge_evidence": [
            edge["edge_id"] for edge in edges if not edge["evidence"].get("evidence_supported")
        ],
        "node_count_by_status": _count_by(nodes, "status"),
        "nodes": nodes,
        "non_contributing_volume": len(diagnostic_nodes),
        "positive_edge_count": len(positive_edges),
        "proves_real_asi": False,
        "protocol_relative_only": True,
        "rejected_or_quarantined_packets": sum(
            1 for node in nodes if node["status"] in {"rejected", "quarantined"}
        ),
        "schema_version": "ccr.effective_graph.v1",
        "settled": False,
        "workflow_usable": bool(nodes),
    }


def _build_edges(
    packet_by_id: dict[str, dict[str, Any]],
    eligibility_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for packet_id, packet in sorted(packet_by_id.items()):
        for dependency in packet.get("dependencies", []):
            if not isinstance(dependency, dict):
                continue
            source_id = str(dependency.get("dependency_id", ""))
            if source_id not in packet_by_id:
                continue
            relation = str(dependency.get("relation", "requires"))
            edges.append(
                _edge_record(
                    source_ids=[source_id],
                    target_id=packet_id,
                    relation=relation,
                    status=str(packet.get("status", "candidate")),
                    eligibility_by_id=eligibility_by_id,
                    source="dependency",
                )
            )
        for semantic_edge in packet.get("semantic_edges", []):
            if not isinstance(semantic_edge, dict):
                continue
            source_ids = [
                str(item)
                for item in semantic_edge.get("source_ids", [])
                if str(item) in packet_by_id
            ]
            target_ids = [
                str(item)
                for item in semantic_edge.get("target_ids", [])
                if str(item) in packet_by_id
            ]
            for target_id in target_ids:
                if source_ids:
                    edges.append(
                        _edge_record(
                            source_ids=source_ids,
                            target_id=target_id,
                            relation=str(semantic_edge.get("relation", "other")),
                            status=str(
                                semantic_edge.get("status", packet.get("status", "candidate"))
                            ),
                            eligibility_by_id=eligibility_by_id,
                            source=str(semantic_edge.get("edge_id", "semantic_edge")),
                        )
                    )
    edges.sort(key=lambda item: item["edge_id"])
    return edges


def _edge_record(
    *,
    source_ids: list[str],
    target_id: str,
    relation: str,
    status: str,
    eligibility_by_id: dict[str, dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    all_ids = [*source_ids, target_id]
    all_positive = all(
        eligibility_by_id.get(packet_id, {}).get("positive_contribution") for packet_id in all_ids
    )
    evidence_supported = status in {"checked", "settled"} and all_positive
    edge_id = stable_id("edge", source, source_ids, target_id, relation)
    reasons: list[str] = []
    if not evidence_supported:
        reasons.append("edge is diagnostic until endpoints and edge evidence are accepted")
    return {
        "accepted": evidence_supported,
        "edge_id": edge_id,
        "evidence": {
            "evidence_refs": [source],
            "evidence_supported": evidence_supported,
            "missing_evidence": [] if evidence_supported else [source],
        },
        "positive_contribution": evidence_supported,
        "protocol_relative_only": True,
        "reasons": reasons,
        "relation_type": relation,
        "settled": False,
        "source_node_ids": source_ids,
        "target_node_id": target_id,
    }


def _contribution_status(eligibility: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_only": bool(eligibility["candidate_only"]),
        "non_contributing_reason": "; ".join(eligibility["reasons"]),
        "positive_contribution": bool(eligibility["positive_contribution"]),
        "settled": False,
        "status": "positive" if eligibility["positive_contribution"] else "diagnostic",
    }


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key, "unknown"))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))
