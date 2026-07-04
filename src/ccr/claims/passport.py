# SPDX-License-Identifier: Apache-2.0
"""Claim passport generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.claims.audit import audit_claims
from ccr.io import read_json, write_json_atomic
from ccr.mission.model import FIXED_CREATED_AT, MISSION_NON_CLAIMS


def build_claim_passport(claims_payload: dict[str, Any]) -> dict[str, Any]:
    """Build a compact claim passport from extracted claims."""

    claims = claims_payload.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    source = str(claims_payload.get("source", "claims"))
    audit = audit_claims(claims, source=source, fail_on=[])
    passport_claims = []
    for claim in audit["claims"]:
        passport_claims.append(
            {
                "claim_id": claim.get("claim_id"),
                "evidence_refs": claim.get("evidence_refs", []),
                "explicit_non_claim": claim.get("explicit_non_claim", False),
                "must_not_be_read_as": claim.get("must_not_be_read_as", []),
                "overclaim_kinds": claim.get("overclaim_kinds", []),
                "status": claim.get("status", "candidate"),
                "supported": bool(claim.get("supported", False)),
            }
        )
    return {
        "claim_count": audit["claim_count"],
        "claims": passport_claims,
        "created_at": FIXED_CREATED_AT,
        "external_execution": False,
        "non_claims": sorted(set([*audit.get("non_claims", []), *MISSION_NON_CLAIMS])),
        "ok": audit["overclaim_count"] == 0,
        "overclaim_count": audit["overclaim_count"],
        "schema_version": "ccr.claim_passport.v1",
        "settled": False,
        "source": source,
        "unsupported_claim_count": audit["unsupported_claim_count"],
    }


def write_claim_passport(claims_path: Path, out: Path) -> dict[str, Any]:
    """Build and write a claim passport."""

    payload = read_json(claims_path)
    if not isinstance(payload, dict):
        raise ValueError("claims input must be a JSON object")
    passport = build_claim_passport(payload)
    write_json_atomic(out, passport, overwrite=True)
    return {
        "claim_count": passport["claim_count"],
        "external_execution": False,
        "ok": bool(passport["ok"]),
        "out": str(out),
        "schema_version": "ccr.claim_passport_write.v1",
        "settled": False,
    }
