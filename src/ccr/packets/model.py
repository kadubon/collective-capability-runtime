# SPDX-License-Identifier: Apache-2.0
"""Packet model helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import json_file_name


def packet_id(packet: dict[str, Any]) -> str:
    """Return packet id."""

    return str(packet["packet_id"])


def packet_status(packet: dict[str, Any]) -> str:
    """Return packet status."""

    return str(packet.get("status", "candidate"))


def packet_path(root: Path, packet_id_value: str, status: str) -> Path:
    """Return packet path by status."""

    return root / "packets" / status / json_file_name(packet_id_value)
