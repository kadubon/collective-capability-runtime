# SPDX-License-Identifier: Apache-2.0
"""Bounded, non-executing input helpers for local CCR commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.ids import stable_id

FIXED_CREATED_AT = "1970-01-01T00:00:00Z"
DEFAULT_MAX_BYTES = 1_000_000


def safe_relative_display(path: Path, *, root: Path | None = None) -> str:
    """Return a stable display path without leaking user-specific absolute paths."""

    try:
        if root is not None:
            return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except (OSError, ValueError):
        pass
    return path.name


def is_path_within_root(path: Path, root: Path) -> bool:
    """Return whether a path resolves inside root."""

    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def read_text_bounded(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    root: Path | None = None,
    source: str = "ccr.input",
) -> dict[str, Any]:
    """Read UTF-8 text with bounds and binary detection."""

    display = safe_relative_display(path, root=root)
    if root is not None and not is_path_within_root(path, root):
        return _read_failure("path_traversal", display, "Input path resolves outside root.", source)
    try:
        if not path.exists():
            return _read_failure("missing_file", display, "Input file is missing.", source)
        if not path.is_file():
            return _read_failure("not_file", display, "Input path is not a file.", source)
        size = path.stat().st_size
    except OSError as exc:
        return _read_failure("input_unreadable", display, f"Input cannot be read: {exc}", source)
    if size > max_bytes:
        return _read_failure("input_too_large", display, "Input exceeds local size bound.", source)
    try:
        data = path.read_bytes()
    except OSError as exc:
        return _read_failure("input_unreadable", display, f"Input cannot be read: {exc}", source)
    if _looks_binary(data):
        return _read_failure("input_binary", display, "Input appears to be binary.", source)
    try:
        return {
            "display": display,
            "ok": True,
            "text": data.decode("utf-8"),
        }
    except UnicodeDecodeError:
        return _read_failure("input_decode_error", display, "Input is not valid UTF-8.", source)


def read_json_bounded(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    root: Path | None = None,
    source: str = "ccr.input",
) -> dict[str, Any]:
    """Read a bounded JSON object."""

    read = read_text_bounded(path, max_bytes=max_bytes, root=root, source=source)
    if not read.get("ok"):
        return read
    try:
        data = json.loads(str(read["text"]))
    except json.JSONDecodeError as exc:
        return _read_failure(
            "malformed_json",
            str(read["display"]),
            f"Input is malformed JSON at line {exc.lineno}.",
            source,
        )
    if not isinstance(data, dict):
        return _read_failure(
            "json_not_object",
            str(read["display"]),
            "Input JSON must contain an object.",
            source,
        )
    return {"data": data, "display": read["display"], "ok": True}


def residual_ready(
    kind: str,
    location: str,
    description: str,
    source: str,
    *,
    blocking: bool = True,
    severity: str = "high",
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a schema-compatible residual-ready object."""

    residual_kind = "validation_error" if kind not in _RESIDUAL_KINDS else kind
    return {
        "blocking": blocking,
        "created_at": FIXED_CREATED_AT,
        "description": description,
        "extensions": {"finding_kind": kind, **(extensions or {})},
        "kind": residual_kind,
        "object_id": location,
        "object_type": "report",
        "refs": [location] if location else [],
        "repair_hint": "Repair the local input and rerun the CCR command.",
        "residual_id": stable_id("residual", source, kind, location, description, blocking),
        "schema_version": "ccr.residual.v0.1",
        "severity": severity,
        "source": source,
        "status": "open",
    }


def _read_failure(kind: str, location: str, description: str, source: str) -> dict[str, Any]:
    return {
        "display": location,
        "ok": False,
        "residual_ready": residual_ready(kind, location, description, source),
    }


def _looks_binary(data: bytes) -> bool:
    if b"\x00" in data:
        return True
    if not data:
        return False
    sample = data[:4096]
    control = sum(1 for byte in sample if byte < 32 and byte not in {9, 10, 13})
    return control / len(sample) > 0.10


_RESIDUAL_KINDS = {
    "authority_gap",
    "candidate_only_reason",
    "dependency_gap",
    "hazard",
    "identity_gap",
    "missing_evidence",
    "negative_liquidity",
    "other",
    "provider_missing",
    "queue_overload",
    "safe_command_hint",
    "scope_gap",
    "settlement_blocker",
    "stale_source",
    "unverified_claim",
    "validation_error",
}
