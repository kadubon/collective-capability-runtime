# SPDX-License-Identifier: Apache-2.0
"""Time helpers with portable UTC handling."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_TTL_RE = re.compile(r"^(?P<value>\d+)(?P<unit>m|h|d)?$")
_UTC = timezone.utc


def now_utc() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(_UTC)


def now_iso() -> str:
    """Return a stable ISO-8601 UTC timestamp."""

    return now_utc().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse a stored UTC timestamp."""

    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def parse_ttl_minutes(value: str | int) -> int:
    """Parse a TTL such as ``30m``, ``2h``, or an integer minute value."""

    if isinstance(value, int):
        if value < 1:
            raise ValueError("ttl must be at least one minute")
        return value
    match = _TTL_RE.match(value.strip())
    if not match:
        raise ValueError("ttl must use minutes, hours, or days, for example 30m, 2h, or 1d")
    amount = int(match.group("value"))
    unit = match.group("unit") or "m"
    factors = {"m": 1, "h": 60, "d": 24 * 60}
    minutes = amount * factors[unit]
    if minutes < 1:
        raise ValueError("ttl must be at least one minute")
    return minutes


def expires_at(leased_at: str | None, ttl_minutes: int) -> datetime | None:
    """Return lease expiration time."""

    start = parse_timestamp(leased_at)
    if start is None:
        return None
    return start + timedelta(minutes=ttl_minutes)


def is_expired(leased_at: str | None, ttl_minutes: int, *, at: datetime | None = None) -> bool:
    """Return true when a lease has expired."""

    expiration = expires_at(leased_at, ttl_minutes)
    if expiration is None:
        return True
    return expiration <= (at or now_utc())
