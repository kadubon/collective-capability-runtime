# SPDX-License-Identifier: Apache-2.0
"""Deterministic claim extraction from prose."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import write_json_atomic
from ccr.mission.model import FIXED_CREATED_AT

MAX_CLAIM_BYTES = 1_000_000
MAX_CLAIMS = 200
DECLARATIVE_START = re.compile(
    r"^(?:CCR|PIC|The |This |A |An |Agents?|Packets?|Providers?|Mission|Workbench|Runtime)\b"
)


def extract_claim_file(path: Path) -> dict[str, Any]:
    """Extract candidate claims from a local text file."""

    if not path.exists():
        raise FileNotFoundError(path)
    if path.stat().st_size > MAX_CLAIM_BYTES:
        return {
            "claim_count": 0,
            "claims": [],
            "created_at": FIXED_CREATED_AT,
            "ok": False,
            "residual_ready": [
                {
                    "blocking": True,
                    "description": "Claim input exceeds local size bound.",
                    "kind": "input_too_large",
                    "residual_id": stable_id("residual", "claim-input-too-large", path.name),
                }
            ],
            "schema_version": "ccr.claim_extract.v1",
            "source": path.name,
        }
    return extract_claims_from_text(path.read_text(encoding="utf-8"), source=path.name)


def extract_claims_from_text(text: str, *, source: str) -> dict[str, Any]:
    """Extract candidate claims from text using deterministic heuristics."""

    claims: list[dict[str, Any]] = []
    for line_number, kind, candidate in _iter_candidates_without_fences(text):
        normalized = _normalize_claim(candidate)
        if not _looks_like_claim(normalized):
            continue
        evidence_refs = _extract_evidence_refs(normalized)
        claim_id = stable_id("claim", source, line_number, normalized)
        claims.append(
            {
                "claim_id": claim_id,
                "evidence_mapped": bool(evidence_refs),
                "evidence_refs": evidence_refs,
                "line": line_number,
                "must_not_be_read_as": _must_not_be_read_as(normalized),
                "source": source,
                "source_kind": kind,
                "status": "evidence_mapped" if evidence_refs else "candidate",
                "supported": bool(evidence_refs),
                "text": normalized,
            }
        )
        if len(claims) >= MAX_CLAIMS:
            break
    return {
        "claim_count": len(claims),
        "claims": claims,
        "created_at": FIXED_CREATED_AT,
        "ok": True,
        "schema_version": "ccr.claim_extract.v1",
        "source": source,
    }


def write_claim_extract(input_path: Path, out: Path) -> dict[str, Any]:
    """Extract claims and write them to JSON."""

    report = extract_claim_file(input_path)
    write_json_atomic(out, report, overwrite=True)
    return {
        "claim_count": report.get("claim_count", 0),
        "external_execution": False,
        "ok": bool(report.get("ok", False)),
        "out": str(out),
        "schema_version": "ccr.claim_extract_write.v1",
        "settled": False,
        "source": input_path.name,
    }


def _iter_candidates_without_fences(text: str) -> list[tuple[int, str, str]]:
    candidates: list[tuple[int, str, str]] = []
    in_fence = False
    paragraph: list[tuple[int, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            paragraph.clear()
            continue
        if in_fence:
            continue
        if not stripped:
            candidates.extend(_paragraph_candidates(paragraph))
            paragraph.clear()
            continue
        if stripped.startswith("#"):
            candidates.extend(_paragraph_candidates(paragraph))
            paragraph.clear()
            candidates.append((line_number, "heading", stripped.lstrip("#").strip()))
            continue
        bullet = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", stripped)
        if bullet:
            candidates.extend(_paragraph_candidates(paragraph))
            paragraph.clear()
            candidates.append((line_number, "bullet", bullet.group(1).strip()))
            continue
        paragraph.append((line_number, stripped))
    candidates.extend(_paragraph_candidates(paragraph))
    return candidates


def _paragraph_candidates(paragraph: list[tuple[int, str]]) -> list[tuple[int, str, str]]:
    if not paragraph:
        return []
    start_line = paragraph[0][0]
    text = " ".join(line for _, line in paragraph)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [
        (start_line, "sentence", sentence.strip()) for sentence in sentences if sentence.strip()
    ]


def _normalize_claim(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    return normalized.strip("` ")


def _looks_like_claim(text: str) -> bool:
    if len(text) < 12 or text.endswith("?"):
        return False
    words = text.split()
    if len(words) < 3:
        return False
    if text.endswith(":"):
        return len(words) >= 4
    return bool(DECLARATIVE_START.search(text) or any(verb in words for verb in _claim_verbs()))


def _claim_verbs() -> set[str]:
    return {
        "accepts",
        "adds",
        "builds",
        "can",
        "creates",
        "detects",
        "does",
        "enforces",
        "generates",
        "grants",
        "initializes",
        "is",
        "keeps",
        "preserves",
        "prevents",
        "reports",
        "requires",
        "returns",
        "supports",
        "validates",
        "writes",
    }


def _extract_evidence_refs(text: str) -> list[str]:
    refs: list[str] = []
    match = re.search(r"(?i)\b(?:evidence|source|ref)\s*:\s*([A-Za-z0-9_./:@+-]+)", text)
    if match:
        refs.append(match.group(1))
    return refs


def _must_not_be_read_as(text: str) -> list[str]:
    lowered = text.lower()
    sensitive = []
    if "asi" in lowered:
        sensitive.append("real_asi_proof")
    if "execute" in lowered or "authority" in lowered:
        sensitive.append("execution_authority")
    if "physical" in lowered or "operation" in lowered:
        sensitive.append("physical_outcome_proof")
    if "provider" in lowered or "pic" in lowered:
        sensitive.append("settlement_oracle")
    return sorted(set(sensitive))
