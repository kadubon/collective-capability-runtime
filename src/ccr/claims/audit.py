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
    ("real_asi_claim", re.compile(r"\bccr\s+(?:is|as)\s+(?:a\s+)?real\s+asi\b")),
    (
        "real_asi_detection",
        re.compile(r"\b(?:detects?|identif(?:y|ies))\b.{0,80}\breal\s+asi\b(?!\s+proxy)"),
    ),
    (
        "real_asi_proof",
        re.compile(
            r"\b(?:proof\s+of\s+real\s+asi(?!\s+proxy)|"
            r"proves?\s+(?:real\s+)?asi\b(?!\s+proxy))"
        ),
    ),
    (
        "real_asi_creation",
        re.compile(r"\b(?:creates?|builds?|forms?)\b.{0,80}\b(?:real\s+)?asi\b(?!\s+proxy)"),
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
            r"\bgrants?\b.{0,80}\b(?:execution\s+)?authority\b|"
            r"\bexecute[s]?\b.{0,80}\bwithout\s+authority\b"
        ),
    ),
    (
        "physical_outcome_proof",
        re.compile(r"\bproves?\b.*\bphysical\s+outcome\b|\bphysical\s+outcome\s+proof\b"),
    ),
    (
        "provider_output_as_settlement",
        re.compile(
            r"\b(?:pic|provider)\s+(?:output|acceptance)\b.{0,80}\bsettle(?:s|ment|d)?\b|"
            r"\b(?:provider\s+output)\b.{0,80}\bsettlement\s+oracle\b"
        ),
    ),
    (
        "execution_available_as_executed",
        re.compile(r"\bexecution_available\b.{0,80}\b(?:means|implies|is)\b.{0,40}\bexecuted\b"),
    ),
    (
        "preflight_as_dispatch",
        re.compile(r"\bpreflight\b.{0,80}\b(?:means|implies|is)\b.{0,40}\bdispatch\b"),
    ),
    (
        "physical_readiness_as_outcome_proof",
        re.compile(r"\bphysical\s+readiness\b.{0,80}\bproves?\b.{0,40}\bphysical\s+outcome\b"),
    ),
    (
        "cache_hit_as_proof",
        re.compile(r"\bcache\s+hit\b.{0,80}\b(?:is|means|implies)\b.{0,40}\bproof\b"),
    ),
    (
        "index_hit_as_proof",
        re.compile(r"\bindex\s+hit\b.{0,80}\b(?:is|means|implies)\b.{0,40}\bproof\b"),
    ),
    (
        "safe_command_as_authority",
        re.compile(r"\bsafe\s+command\b.{0,80}\b(?:is|means|implies)\b.{0,40}\bauthority\b"),
    ),
    (
        "mcp_descriptor_as_authority",
        re.compile(
            r"\b(?:mcp\s+)?descriptor\b.{0,80}\b(?:grants?|is|means|implies)\b"
            r".{0,40}\bauthority\b"
        ),
    ),
    (
        "a2a_handoff_as_authority",
        re.compile(
            r"\b(?:a2a\s+)?handoff\b.{0,80}\b(?:grants?|is|means|implies)\b"
            r".{0,40}\b(?:delegated\s+)?authority\b"
        ),
    ),
    (
        "conformance_as_settlement",
        re.compile(
            r"\bconformance\b.{0,80}\b(?:is|means|implies|proves?|grants?)\b"
            r".{0,40}\bsettle(?:s|ment|d)?\b"
        ),
    ),
    (
        "observation_as_physical_proof",
        re.compile(
            r"\bobservation(?:\s+verifier)?\b.{0,80}\b(?:is|means|implies|proves?)\b"
            r".{0,40}\bphysical\s+outcome\b"
        ),
    ),
    (
        "provider_registry_as_authority",
        re.compile(
            r"\bprovider\s+registry\b.{0,80}\b(?:grants?|is|means|implies)\b"
            r".{0,40}\bauthority\b"
        ),
    ),
)
NEGATION_TOKENS = {"not", "never", "cannot", "cant"}
NON_CLAIM_BOUNDARY_PATTERNS = (
    re.compile(r"\bmust\s+not\b"),
    re.compile(r"\bevidence\s+only\b"),
    re.compile(r"\bnot\s+(?:a\s+)?proof\b"),
    re.compile(r"\bnot\s+settlement\b"),
    re.compile(r"\bnot\s+(?:execution\s+)?authority\b"),
    re.compile(r"\bis\s+not\s+execution\b"),
    re.compile(r"\bis\s+not\s+physical\s+outcome\s+proof\b"),
)


def audit_claim_file(path: Path, *, fail_on: list[str] | None = None) -> dict[str, Any]:
    """Audit claims from a local file."""

    extracted = extract_claim_file(path)
    if not extracted.get("ok", False):
        residuals = extracted.get("residual_ready", [])
        residual_ready = [item for item in residuals if isinstance(item, dict)]
        return {
            "claim_count": 0,
            "claims": [],
            "external_execution": False,
            "fail_on": sorted(set(fail_on or [])),
            "non_claims": list(MISSION_NON_CLAIMS),
            "ok": False,
            "overclaim_count": 0,
            "policy_failures": ["schema_error"]
            if "schema_error" in {item.strip().lower() for item in fail_on or []}
            else [],
            "residual_ready": residual_ready,
            "schema_version": "ccr.claim_audit.v1",
            "settled": False,
            "source": str(extracted.get("source", path.name)),
            "schema_error_count": 1,
            "unsupported_claim_count": 0,
        }
    claims = extracted.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    report = audit_claims(claims, source=path.name, fail_on=fail_on or [])
    report["fail_on"] = sorted(set(fail_on or []))
    report["policy_failures"] = _policy_failures(report, fail_on or [])
    if report["policy_failures"]:
        report["ok"] = False
    return report


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
    report = {
        "claim_count": len(normalized_claims),
        "claims": audited_claims,
        "external_execution": False,
        "fail_on": sorted(fail_set),
        "non_claims": sorted(set([*non_claims, *MISSION_NON_CLAIMS])),
        "ok": not blocking,
        "overclaim_count": overclaim_count,
        "policy_failures": [],
        "residual_ready": residual_ready,
        "schema_version": "ccr.claim_audit.v1",
        "settled": False,
        "source": source,
        "unsupported_claim_count": unsupported_count,
    }
    report["policy_failures"] = _policy_failures(report, sorted(fail_set))
    if report["policy_failures"]:
        report["ok"] = False
    return report


def _overclaim_kinds(text: str) -> list[str]:
    normalized = _normalize_for_audit(text)
    kinds = []
    for kind, pattern in OVERCLAIM_PATTERNS:
        match = pattern.search(normalized)
        if match and not _has_negative_context(normalized, match):
            kinds.append(kind)
    return kinds


def _is_explicit_non_claim(text: str) -> bool:
    normalized = _normalize_for_audit(text)
    has_boundary_phrase = any(pattern.search(normalized) for pattern in NON_CLAIM_BOUNDARY_PATTERNS)
    for _kind, pattern in OVERCLAIM_PATTERNS:
        match = pattern.search(normalized)
        if match and _has_negative_context(normalized, match):
            return True
        if match and has_boundary_phrase:
            return True
    return False


def _normalize_for_audit(text: str) -> str:
    normalized = text.lower().replace("can't", "cant")
    normalized = re.sub(r"[^a-z0-9_]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _has_negative_context(text: str, match: re.Match[str]) -> bool:
    tokens = list(re.finditer(r"[a-z0-9_]+", text))
    match_tokens = [
        token.group(0)
        for token in tokens
        if token.start() >= match.start() and token.end() <= match.end()
    ]
    if any(token in NEGATION_TOKENS for token in match_tokens):
        return True
    before = [token.group(0) for token in tokens if token.end() <= match.start()]
    return any(token in NEGATION_TOKENS for token in before[-5:])


def _policy_failures(report: dict[str, Any], fail_on: list[str]) -> list[str]:
    failures: list[str] = []
    normalized = {item.strip().lower() for item in fail_on if item.strip()}
    if "overclaim" in normalized and int(report.get("overclaim_count", 0)) > 0:
        failures.append("overclaim")
    if "unsupported_claim" in normalized and int(report.get("unsupported_claim_count", 0)) > 0:
        failures.append("unsupported_claim")
    if "schema_error" in normalized and report.get("schema_error_count", 0):
        failures.append("schema_error")
    return sorted(set(failures))


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
