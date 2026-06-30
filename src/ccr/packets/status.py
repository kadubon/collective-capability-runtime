# SPDX-License-Identifier: Apache-2.0
"""Central CCR packet status semantics."""

from __future__ import annotations

from ccr.constants import PACKET_STATUSES

TERMINAL_STATUSES = {"rejected", "quarantined", "deprecated", "expired"}
PROMOTABLE_TARGETS = {"checked", "settled", "quarantined", "deprecated"}


def require_packet_status(status: str) -> str:
    """Validate and return a packet status."""

    if status not in PACKET_STATUSES:
        raise ValueError(f"unknown packet status: {status}")
    return status


def can_store_status(status: str) -> bool:
    """Return true when CCR has a storage directory for this status."""

    return status in PACKET_STATUSES


def can_attempt_promotion(status_before: str, target: str) -> bool:
    """Return true when a promotion target is structurally meaningful."""

    require_packet_status(status_before)
    require_packet_status(target)
    if target not in PROMOTABLE_TARGETS:
        return False
    if target in {"quarantined", "deprecated"}:
        return True
    if target == "checked":
        return status_before == "candidate"
    if target == "settled":
        return status_before == "checked"
    return False
