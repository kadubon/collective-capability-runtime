# SPDX-License-Identifier: Apache-2.0
"""Packet distillation helpers."""

from __future__ import annotations

from typing import Any


def packet_summary_text(packet: dict[str, Any]) -> str:
    """Build concise text for verifier adapters."""

    claims = packet.get("claims", [])
    claim_text = "; ".join(
        str(item.get("claim_text", "")) for item in claims if isinstance(item, dict)
    )
    residual_count = len(packet.get("residuals", []))
    return (
        f"Packet {packet.get('packet_id')}: {packet.get('summary')}. "
        f"Claims: {claim_text}. Residuals declared: {residual_count}. "
        "CCR preserves residuals and does not treat accepted=true as settled."
    )
