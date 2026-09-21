# SPDX-License-Identifier: Apache-2.0
"""Bounded native JSON and exact registered unit conversion. No I/O or resolution."""

from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from typing import Any

MAX_BYTES = 2_000_000
MAX_NODES = 50_000
MAX_DEPTH = 24
MAX_INTEGER = 2**53


def raw_digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _invalid_number(value: str) -> Any:
    raise ValueError("native JSON requires integer tokens or exact rational strings")


def loads(raw: bytes) -> dict[str, Any]:
    """Check lexical depth before invoking the JSON parser, then bound the tree."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BYTES:
        raise ValueError("native source byte limit")
    text = raw.decode("utf-8", errors="strict")
    depth = 0
    quoted = escaped = False
    for char in text:
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char in "[{":
                depth += 1
                if depth > MAX_DEPTH:
                    raise ValueError("native nesting limit")
            elif char in "]}":
                depth -= 1
    value = json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_float=_invalid_number,
        parse_constant=_invalid_number,
    )
    pending = [value]
    count = 0
    while pending:
        item = pending.pop()
        count += 1
        if count > MAX_NODES:
            raise ValueError("native node limit")
        if isinstance(item, dict):
            if len(item) > 512:
                raise ValueError("native object limit")
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, list):
            if len(item) > 512:
                raise ValueError("native array limit")
            pending.extend(item)
        elif isinstance(item, str) and len(item) > 131072:
            raise ValueError("native string limit")
        elif type(item) is int and abs(item) > MAX_INTEGER:
            raise ValueError("native integer limit")
    if not isinstance(value, dict):
        raise ValueError("native document must be an object")
    return value


def rational(value: Any) -> Fraction:
    if (
        not isinstance(value, str)
        or len(value) > 81
        or re.fullmatch(r"-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?", value) is None
    ):
        raise ValueError("canonical rational required")
    result = Fraction(value)
    if str(result) != value or max(abs(result.numerator), result.denominator).bit_length() > 128:
        raise ValueError("noncanonical or oversized rational")
    return result


def convert(value: str, rate: str, *, rounding: str = "exact") -> int:
    """Only explicit same-dimension registrations may call this elementary operation."""
    amount, scale = rational(value), rational(rate)
    if amount < 0 or scale <= 0 or rounding not in {"exact", "upper", "lower"}:
        raise ValueError("invalid unit conversion")
    product = amount * scale
    if rounding == "exact" and product.denominator != 1:
        raise ValueError("lossy unit conversion")
    result = product.numerator // product.denominator
    if rounding == "upper" and product.denominator != 1:
        result += 1
    if result > MAX_INTEGER:
        raise ValueError("CCR integer overflow")
    return result
