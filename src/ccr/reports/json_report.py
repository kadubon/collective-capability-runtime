# SPDX-License-Identifier: Apache-2.0
"""JSON reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.constants import NON_CLAIMS
from ccr.residuals.store import iter_residuals
from ccr.runtime.config import load_config
from ccr.runtime.state import packet_counts, residual_counts, task_counts


def phase_report(root: Path) -> dict[str, Any]:
    """Build a deterministic phase summary."""

    config = load_config(root)
    residuals = list(iter_residuals(root))
    open_residuals = [item for item in residuals if item.get("status") == "open"]
    candidate_only_reasons = [
        item
        for item in residuals
        if item.get("kind") == "candidate_only_reason"
        or item.get("extensions", {}).get("source_pic_field") == "candidate_only_reasons"
    ]
    pic_report_count = 0
    pic_dir = root / "reports" / "pic"
    if pic_dir.exists():
        pic_report_count = sum(1 for item in pic_dir.glob("*.json") if item.is_file())
    return {
        "blocking_residual_count": sum(1 for item in open_residuals if item.get("blocking")),
        "candidate_only_reasons_count": len(candidate_only_reasons),
        "generated_at": str(config.get("created_at", "1970-01-01T00:00:00Z")),
        "non_claims": list(NON_CLAIMS),
        "open_residual_count": len(open_residuals),
        "packet_counts": packet_counts(root),
        "pic_report_count": pic_report_count,
        "residual_counts": residual_counts(root),
        "schema_version": "ccr.phase_report.v0.1",
        "task_counts": task_counts(root),
    }
