# SPDX-License-Identifier: Apache-2.0
"""Explicit affine producer clocks with conservative UTC boundary conversion."""

from __future__ import annotations

from datetime import timedelta
from fractions import Fraction
from typing import Any

from ccr.optimizer.growth_model import closed
from ccr.optimizer.model import timestamp
from ccr.optimizer.native_wire import rational


def validate(clock: dict[str, Any]) -> None:
    closed(clock, "utc_origin tick_origin seconds_per_tick")
    timestamp(clock["utc_origin"])
    if rational(clock["tick_origin"]) < 0 or rational(clock["seconds_per_tick"]) <= 0:
        raise ValueError("invalid native clock origin or rate")


def utc(clock: dict[str, Any], tick: Fraction, *, lower: bool) -> str:
    """Earliest times round later; deadlines round earlier, without float loss."""
    validate(clock)
    micros = (
        (tick - rational(clock["tick_origin"])) * rational(clock["seconds_per_tick"]) * 1_000_000
    )
    rounded = (
        -(-micros.numerator // micros.denominator)
        if lower
        else micros.numerator // micros.denominator
    )
    try:
        return (timestamp(clock["utc_origin"]) + timedelta(microseconds=rounded)).isoformat()
    except OverflowError as error:
        raise ValueError("native clock exceeds UTC range") from error


def window(
    producer: str, documents: dict[str, Any], original: str, clock: dict[str, Any]
) -> dict[str, str]:
    """Reconstruct time bounds from native source, never from projected totals.

    Execution preserves the native endpoint. Cleanup must fit before the next
    selected slot and native deadline; it cannot silently shift subsequent work.
    """
    c = documents["contract"]
    if producer in {"alt", "vek"}:
        if rational(clock["seconds_per_tick"]) != rational(c["slot_seconds"]):
            raise ValueError("native slot duration differs from registered clock rate")
    elif producer != "cpcf" or rational(clock["seconds_per_tick"]) != 1:
        raise ValueError("unsupported native clock dimension")
    if producer == "alt":
        row = next(a for a in c["options"] if a["id"] == original)
        available = Fraction(c["evidence_cutoff"])
        start = Fraction(c["checkpoint"] + row["start"])
        end = Fraction(c["checkpoint"] + row["end"])
        cleanup = Fraction(
            c["checkpoint"]
            + min(
                [c["horizon"]]
                + [
                    a["start"]
                    for a in c["options"]
                    if a["id"] in documents["plan"]["selected"] and a["start"] > row["start"]
                ]
            )
        )
        if row["offer"] is not None:
            offer = next(q["offer"] for q in c["qualifications"] if q["id"] == row["offer"])
            start = max(start, Fraction(offer["valid_from"]))
            end = min(end, Fraction(offer["valid_until"]))
            cleanup = min(cleanup, Fraction(offer["valid_until"]))
    elif producer == "vek":
        if documents["history"]["events"]:
            raise ValueError("VEK historical clock events need an explicit cutoff mapping")
        row = next(a for a in c["actions"] if a["action_id"] == original)
        work = next(w for w in c["work"] if w["work_id"] == row["work_id"])
        service = next(s for s in c["services"] if s["service_id"] == row["service_id"])
        available = Fraction(0)
        start = Fraction(max(work["arrival"], documents["plan"]["schedule"][original]))
        end = Fraction(min(int(start) + row["duration"], work["deadline"], service["valid_until"]))
        cleanup = Fraction(
            min(
                [work["deadline"], service["valid_until"]]
                + [value for value in documents["plan"]["schedule"].values() if value > start]
            )
        )
    else:
        c = c["spec"]
        row = next(
            a
            for a in c["action_catalogue"]
            if documents["objects"][a["action_digest"]]["spec"]["action_id"] == original
        )
        available = rational(c["initial_state"]["elapsed"])
        history_rows = [
            next(
                a
                for a in c["action_catalogue"]
                if documents["objects"][a["action_digest"]]["spec"]["action_id"]
                == item["action_id"]
            )
            for item in documents["plan"]["spec"]["history"]
        ]
        # Use every branch's upper elapsed bound; do not select a hidden model.
        for prior in history_rows:
            available += max(rational(s["duration"]) for s in prior["successors"])
        start = max(available, rational(row["earliest"]))
        end = min(rational(row["expires"]), rational(c["deadline"]))
        for evidence in row["required_evidence"]:
            expiries = [
                rational(s["evidence_added"][evidence])
                for prior in history_rows
                for s in prior["successors"]
                if evidence in s["evidence_added"]
            ]
            if not expiries:
                raise ValueError("CPCF evidence has no mapped source clock")
            end = min(end, *expiries)
        cleanup = end
    if start >= end or available > start:
        raise ValueError("empty or anticipatory native time interval")
    return {
        "available_at": utc(clock, available, lower=True),
        "start": utc(clock, start, lower=True),
        "execution_end": utc(clock, end, lower=False),
        "end": utc(clock, cleanup, lower=False),
    }


def applicable(window: dict[str, str], current: str, seconds: int = 0, cleanup: int = 0) -> bool:
    return (
        timestamp(window["available_at"])
        <= timestamp(window["start"])
        <= timestamp(current)
        < timestamp(window["execution_end"])
        and timestamp(current) + timedelta(seconds=seconds) <= timestamp(window["execution_end"])
        and timestamp(current) + timedelta(seconds=seconds + cleanup) <= timestamp(window["end"])
    )
