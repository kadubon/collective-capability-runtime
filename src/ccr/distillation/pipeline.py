# SPDX-License-Identifier: Apache-2.0
"""Deterministic candidate claim segmentation and evidence binding."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccr.ids import sha256_bytes, stable_id

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_CONTAMINATION_MARKERS = (
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "exfiltrate",
    "bypass safety",
)


def analyze_seed(path: Path, text: str) -> dict[str, Any]:
    """Segment claims and bind explicit evidence without validating truth."""

    evidence: list[str] = []
    dependencies: list[str] = []
    claim_segments: list[str] = []
    for paragraph in (item.strip() for item in text.splitlines()):
        if not paragraph:
            continue
        lowered = paragraph.casefold()
        if lowered.startswith("evidence:"):
            evidence.append(paragraph.split(":", 1)[1].strip())
            continue
        if lowered.startswith(("depends on:", "dependency:")):
            dependencies.append(paragraph.split(":", 1)[1].strip())
            continue
        claim_segments.extend(
            segment.strip() for segment in _SENTENCE_BOUNDARY.split(paragraph) if segment.strip()
        )
    contamination = sorted(marker for marker in _CONTAMINATION_MARKERS if marker in text.casefold())
    candidates = [
        {
            "claim_id": stable_id("distilled-claim", segment),
            "claim_text": segment,
            "dependencies": sorted(set(dependencies)),
            "evidence": sorted(set(evidence)),
            "mechanism_ablation_plan": [
                "Remove each cited evidence item and rerun the verifier.",
                "Replace the proposed mechanism with a null mechanism and compare outcomes.",
            ],
            "provenance": {
                "source_name": path.name,
                "source_sha256": sha256_bytes(text.encode("utf-8")),
                "segment_index": index,
            },
            "status": "candidate",
        }
        for index, segment in enumerate(claim_segments)
    ]
    return {
        "candidates": candidates,
        "contamination_markers": contamination,
        "dependencies": sorted(set(dependencies)),
        "evidence": sorted(set(evidence)),
        "source_sha256": sha256_bytes(text.encode("utf-8")),
    }
