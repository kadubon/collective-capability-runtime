# SPDX-License-Identifier: Apache-2.0
"""Claim audit and overclaim detection."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccr.claims.extract import extract_claim_file
from ccr.ids import stable_id
from ccr.mission.model import FIXED_CREATED_AT, MISSION_NON_CLAIMS

OVERCLAIM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "real_asi_detection",
        re.compile(r"\b(?:detects?|proves?|identif(?:y|ies))\b.*\breal\s+asi\b"),
    ),
    (
        "real_asi_creation",
        re.compile(r"\b(?:creates?|builds?|forms?)\b.*\breal\s+asi\b"),
    ),
    (
        "model_self_rewrite",
        re.compile(r"\b(?:self[- ]?rewrite|self[- ]?modif(?:y|ies)|rewrite[s]? its own model)\b"),
    ),
    (
        "model_weight_update",
        re.compile(r"\b(?:updates?|modif(?:y|ies))\b.*\bmodel\s+weights?\b"),
    ),
    (
        "hidden_capability_injection",
        re.compile(r"\bhidden\s+capabilit(?:y|ies)\s+injection\b|\binjects?\b.*\bcapabilit"),
    ),
    (
        "execution_authority_grant",
        re.compile(
            r"\bgrants?\b.*\bexecution\s+authority\b|\bexecute[s]?\b.*\bwithout\s+authority\b"
        ),
    ),
    (
        "physical_outcome_proof",
        re.compile(r"\bproves?\b.*\bphysical\s+outcome\b|\bphysical\s+outcome\s+proof\b"),
    ),
    (
        "provider_output_as_settlement",
        re.compile(
            r"\b(?:pic|provider)\s+output\b.*\bsettlement\b|\bsettles?\b.*\b(?:pic|provider)\b"
        ),
    ),
)
NEGATION_RE = re.compile(
    r"\b(?:does\s+not|do\s+not|must\s+not|is\s+not|are\s+not|never|cannot|can't|not)\b"
)


def audit_claim_file(path: Path, *, fail_on: list[str] | None = None) -> dict[str, Any]:
    """Audit claims from a local file."""

    extracted = extract_claim_file(path)
    claims = extracted.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    return audit_claims(claims, source=path.name, fail_on=fail_on or [])


def audit_claims(
    claims: list[Any],
    *,
    source: str,
    fail_on: list[str] | None = None,
) -> dict[str, Any]:
    """Audit extracted claims for unsupported claims and ASI-proxy overclaims."""

    fail_set = set(fail_on or [])
    normalized_claims = [claim for claim in claims if isinstance(claim, dict)]
    residual_ready: list[dict[str, Any]] = []
    non_claims: list[str] = []
    overclaim_count = 0
    unsupported_count = 0
    audited_claims: list[dict[str, Any]] = []
    for claim in normalized_claims:
        text = str(claim.get("text", ""))
        overclaim_kinds = _overclaim_kinds(text)
        is_non_claim = _is_explicit_non_claim(text)
        if is_non_claim:
            non_claims.append(text)
        if overclaim_kinds and not is_non_claim:
            overclaim_count += 1
            residual_ready.append(
                _claim_residual(
                    "settlement_blocker",
                    f"Overclaim requires removal or explicit non-claim boundary: {text}",
                    blocking=True,
                    claim=claim,
                    source=source,
                    residual_kind="overclaim",
                    extensions={"overclaim_kinds": overclaim_kinds},
                )
            )
        supported = bool(claim.get("supported") or claim.get("evidence_refs"))
        if not supported and not is_non_claim:
            unsupported_count += 1
            residual_ready.append(
                _claim_residual(
                    "unverified_claim",
                    f"Unsupported candidate claim requires evidence mapping: {text}",
                    blocking="unsupported_claim" in fail_set,
                    claim=claim,
                    source=source,
                    residual_kind="unsupported_claim",
                    extensions={},
                )
            )
        audited_claims.append(
            {
                **claim,
                "explicit_non_claim": is_non_claim,
                "overclaim_kinds": overclaim_kinds if not is_non_claim else [],
            }
        )
    blocking = [item for item in residual_ready if item.get("blocking")]
    return {
        "claim_count": len(normalized_claims),
        "claims": audited_claims,
        "external_execution": False,
        "non_claims": sorted(set([*non_claims, *MISSION_NON_CLAIMS])),
        "ok": not blocking,
        "overclaim_count": overclaim_count,
        "residual_ready": residual_ready,
        "schema_version": "ccr.claim_audit.v1",
        "settled": False,
        "source": source,
        "unsupported_claim_count": unsupported_count,
    }


def _overclaim_kinds(text: str) -> list[str]:
    lowered = text.lower()
    return [kind for kind, pattern in OVERCLAIM_PATTERNS if pattern.search(lowered)]


def _is_explicit_non_claim(text: str) -> bool:
    lowered = text.lower()
    if not NEGATION_RE.search(lowered):
        return False
    return bool(_overclaim_kinds(text) or "real asi" in lowered or "settlement" in lowered)


def _claim_residual(
    kind: str,
    description: str,
    *,
    blocking: bool,
    claim: dict[str, Any],
    source: str,
    residual_kind: str,
    extensions: dict[str, Any],
) -> dict[str, Any]:
    claim_id = str(claim.get("claim_id", stable_id("claim", source, description)))
    return {
        "blocking": blocking,
        "created_at": FIXED_CREATED_AT,
        "description": description,
        "extensions": {"claim_id": claim_id, "finding_kind": residual_kind, **extensions},
        "kind": kind,
        "object_id": claim_id,
        "object_type": "report",
        "refs": [source],
        "repair_hint": "Add evidence, weaken the claim, or make the non-claim boundary explicit.",
        "residual_id": stable_id("residual", source, claim_id, residual_kind, blocking),
        "schema_version": "ccr.residual.v0.1",
        "severity": "high" if blocking else "medium",
        "source": "ccr.claim.audit",
        "status": "open",
    }
