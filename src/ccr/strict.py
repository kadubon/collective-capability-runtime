# SPDX-License-Identifier: Apache-2.0
"""Strict scalar adapters for untrusted report and provider input."""

from __future__ import annotations

from typing import Any


def strict_bool(value: Any, *, field: str, default: bool | None = None) -> bool:
    """Return a JSON boolean without accepting truthy strings or numbers."""

    if value is None and default is not None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a JSON boolean")
    return value
