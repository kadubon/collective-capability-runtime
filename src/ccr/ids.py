# SPDX-License-Identifier: Apache-2.0
"""Identifier and digest helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Return canonical JSON bytes for deterministic hashes."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    """Return SHA-256 hex digest."""

    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    """Return SHA-256 digest for a JSON-compatible value."""

    return sha256_bytes(canonical_bytes(value))


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    """Build a schema-safe deterministic identifier from JSON-compatible parts."""

    digest = sha256_json(parts)[:length]
    clean_prefix = prefix.rstrip(":")
    return f"{clean_prefix}:{digest}"
