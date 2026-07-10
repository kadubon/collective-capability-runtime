# SPDX-License-Identifier: Apache-2.0
"""Packet eligibility rules for phase formation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.residuals.store import linked_open_blocking_residuals

CONTRIBUTING_STATUSES = {"checked", "settled"}
EFFECTIVE_GRAPH_STATUSES = {"checked", "provisional", "settled"}
DIAGNOSTIC_ONLY_STATUSES = {
    "raw",
    "proposed",
    "candidate",
    "speculative",
    "rejected",
    "quarantined",
    "deprecated",
    "expired",
}


def packet_eligibility(root: Path, packet: dict[str, Any]) -> dict[str, Any]:
    """Return phase-formation eligibility for one packet."""

    status = str(packet.get("status", "candidate"))
    packet_id = str(packet.get("packet_id", "unknown"))
    risk = packet.get("risk", {}) if isinstance(packet.get("risk"), dict) else {}
    execution = (
        packet.get("execution_availability", {})
        if isinstance(packet.get("execution_availability"), dict)
        else {}
    )
    packet_residuals = [
        item
        for item in packet.get("residuals", [])
        if isinstance(item, dict) and item.get("blocking")
    ]
    ledger_blockers = linked_open_blocking_residuals(root, packet_id)
    blockers = packet_residuals + ledger_blockers
    authority_level = str(risk.get("authority_level", "none"))
    side_effect_policy = str(execution.get("side_effect_policy", "none"))
    authority_valid = (
        authority_level != "external_side_effect" and side_effect_policy != "unsafe_not_allowed"
    )
    execution_mode = str(execution.get("mode", "not_applicable"))
    execution_available = (
        execution_mode not in {"not_applicable", "unknown", ""}
        and authority_valid
        and side_effect_policy
        in {"none", "dry_run_only", "sandbox_only", "operator_approval_required"}
    )
    metrics = packet.get("metrics", {}) if isinstance(packet.get("metrics"), dict) else {}
    coordinates = {
        "reuse_score": _coordinate(metrics.get("reuse_score"), unit="ratio"),
        "residual_load": _coordinate(metrics.get("residual_load"), unit="load"),
        "hazard_load": _coordinate(metrics.get("hazard_load"), unit="load"),
        "queue_load": _coordinate(metrics.get("queue_load"), unit="load"),
    }
    coordinates_known = all(item["status"] == "known" for item in coordinates.values())
    liquidity_lower_bound = None
    if coordinates_known:
        liquidity_lower_bound = (
            float(coordinates["reuse_score"]["value"])
            - float(coordinates["residual_load"]["value"])
            - float(coordinates["hazard_load"]["value"])
            - float(coordinates["queue_load"]["value"])
        )
    accepted_or_certificate_admissible = status in EFFECTIVE_GRAPH_STATUSES
    candidate_only = status in DIAGNOSTIC_ONLY_STATUSES or status == "provisional"
    positive_contribution = (
        status in CONTRIBUTING_STATUSES
        and not blockers
        and authority_valid
        and coordinates_known
        and liquidity_lower_bound is not None
        and liquidity_lower_bound >= 0
    )
    reasons: list[str] = []
    if status not in EFFECTIVE_GRAPH_STATUSES:
        reasons.append("packet status is diagnostic-only for phase formation")
    if status == "provisional":
        reasons.append("provisional packets enter graph but do not settle phase coordinates")
    if blockers:
        reasons.append("blocking residuals prevent positive phase contribution")
    if not authority_valid:
        reasons.append("authority or side-effect policy is outside the phase envelope")
    for name, coordinate in coordinates.items():
        if coordinate["status"] == "unknown":
            reasons.append(f"missing explicit phase coordinate: {name}")
    if liquidity_lower_bound is not None and liquidity_lower_bound < 0:
        reasons.append("liquidity lower bound is negative after residual and hazard charges")
    return {
        "accepted_or_certificate_admissible": accepted_or_certificate_admissible,
        "accumulated": bool(packet.get("artifacts")),
        "available": accepted_or_certificate_admissible and bool(packet.get("artifacts")),
        "authority_valid": authority_valid,
        "blocking_residual_ids": [str(item.get("residual_id", "")) for item in blockers],
        "candidate_only": candidate_only,
        "coordinates": coordinates,
        "execution_available": execution_available,
        "executed": False,
        "liquidity_lower_bound": liquidity_lower_bound,
        "positive_contribution": positive_contribution,
        "reasons": reasons,
        "residuals_preserved": "residuals" in packet,
        "status": status,
    }


def _coordinate(value: Any, *, unit: str) -> dict[str, Any]:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return {"status": "unknown", "unit": unit, "validity_domain": None, "value": None}
    number = float(value)
    if number < 0:
        return {"status": "unknown", "unit": unit, "validity_domain": None, "value": None}
    return {
        "status": "known",
        "unit": unit,
        "validity_domain": "declared-packet-metrics",
        "value": number,
    }
