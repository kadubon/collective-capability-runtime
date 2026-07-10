# SPDX-License-Identifier: Apache-2.0
"""Identifier and digest helpers."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

MAX_IDENTIFIER_LENGTH = 200
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


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


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    """Validate an identifier before it is used in a path or storage key."""

    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} exceeds {MAX_IDENTIFIER_LENGTH} characters")
    if value in {".", ".."} or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{field} contains non-portable or path-like characters")
    if value.rstrip(". ") != value:
        raise ValueError(f"{field} may not end with a dot or space")
    stem = value.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise ValueError(f"{field} is reserved on Windows")
    return value
