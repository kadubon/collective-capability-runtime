# SPDX-License-Identifier: Apache-2.0
"""Residual model helpers."""

from __future__ import annotations

from typing import Any

from ccr.ids import stable_id
from ccr.time import now_iso

PACKET_RESIDUAL_KINDS = {
    "missing_evidence",
    "unverified_claim",
    "scope_gap",
    "authority_gap",
    "hazard",
    "identity_gap",
    "stale_source",
    "dependency_gap",
    "queue_overload",
    "negative_liquidity",
    "settlement_blocker",
    "other",
}


def build_residual(
    *,
    kind: str,
    description: str,
    blocking: bool,
    object_type: str = "unknown",
    object_id: str = "",
    severity: str = "medium",
    refs: list[str] | None = None,
    source: str = "ccr",
    repair_hint: str = "",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a valid CCR residual ledger entry."""

    residual_id = stable_id(
        "residual", kind, description, blocking, object_type, object_id, refs or [], source
    )
    return {
        "blocking": blocking,
        "created_at": now_iso(),
        "description": description,
        "extensions": extensions or {},
        "kind": kind,
        "object_id": object_id,
        "object_type": object_type,
        "refs": sorted(refs or []),
        "repair_hint": repair_hint,
        "residual_id": residual_id,
        "schema_version": "ccr.residual.v0.1",
        "severity": severity,
        "source": source,
        "status": "open",
    }


def to_packet_residual(residual: dict[str, Any]) -> dict[str, Any]:
    """Convert a ledger residual to the packet-embedded residual shape."""

    kind = str(residual.get("kind", "other"))
    if kind not in PACKET_RESIDUAL_KINDS:
        kind = "other"
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
        "kind": kind,
        "repair_hint": str(residual.get("repair_hint", "")),
        "residual_id": str(residual.get("residual_id")),
        "severity": str(residual.get("severity", "medium")),
    }
