# SPDX-License-Identifier: Apache-2.0
"""Packet file store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.constants import PACKET_STATUSES
from ccr.ids import validate_identifier
from ccr.io import read_json, write_json_atomic
from ccr.packets.model import packet_path
from ccr.schemas.validation import ValidationResult, validate_instance


def validate_packet(packet: dict[str, Any], *, root: Path) -> ValidationResult:
    """Validate a packet against the normative schema."""

    return validate_instance("packet", packet, root=root)


def submit_packet(root: Path, packet: dict[str, Any]) -> Path:
    """Store a packet according to its declared status."""

    validate_identifier(str(packet["packet_id"]), field="packet_id")
    status = str(packet.get("status", "candidate"))
    path = packet_path(root, str(packet["packet_id"]), status)
    write_json_atomic(path, packet, overwrite=False)
    return path


def find_packet_path(root: Path, packet_id_value: str) -> tuple[Path, str] | None:
    """Find a packet across status directories."""

    for status in PACKET_STATUSES:
        path = packet_path(root, packet_id_value, status)
        if path.exists():
            return path, status
    return None


def load_packet(root: Path, packet_id_value: str) -> tuple[dict[str, Any], Path, str]:
    """Load a packet by id."""

    found = find_packet_path(root, packet_id_value)
    if found is None:
        raise FileNotFoundError(packet_id_value)
    path, status = found
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"packet {packet_id_value} is not a JSON object")
    return data, path, status


def save_packet_at_status(
    root: Path,
    packet: dict[str, Any],
    *,
    status: str,
    old_path: Path | None = None,
) -> Path:
    """Save a packet at a status and remove the old path if status changed."""

    validate_identifier(str(packet["packet_id"]), field="packet_id")
    packet["status"] = status
    destination = packet_path(root, str(packet["packet_id"]), status)
    write_json_atomic(destination, packet, overwrite=True)
    if old_path is not None and old_path != destination and old_path.exists():
        old_path.unlink()
    return destination


def iter_packets(root: Path, *, status: str | None = None) -> list[dict[str, Any]]:
    """Return packets sorted by status and filename."""

    statuses = [status] if status else list(PACKET_STATUSES)
    packets: list[dict[str, Any]] = []
    for current in statuses:
        directory = root / "packets" / current
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            data = read_json(path)
            if isinstance(data, dict):
                packets.append(data)
    return packets
