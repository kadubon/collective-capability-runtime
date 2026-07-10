# SPDX-License-Identifier: Apache-2.0
"""PIC 1.0 report negotiation and candidate-only contract checks."""

from __future__ import annotations

from typing import Any

from ccr.ids import sha256_json
from ccr.strict import strict_bool

SUPPORTED_PIC_MAJOR_MINOR = {(0, minor) for minor in range(5, 10)} | {(1, 0)}


def validate_pic_contract(report: dict[str, Any], *, pic_version: str) -> dict[str, Any]:
    """Validate strict scalars, residual parity, digest, and non-executed hints."""

    blockers: list[str] = []
    version = _major_minor(pic_version)
    if version not in SUPPORTED_PIC_MAJOR_MINOR:
        blockers.append("unsupported_pic_version")
    try:
        accepted = strict_bool(report.get("accepted"), field="accepted", default=False)
        settled = strict_bool(report.get("settled"), field="settled", default=False)
    except ValueError as exc:
        accepted = False
        settled = False
        blockers.append(str(exc))
    residuals = report.get("residuals")
    residual_items = (
        [item for item in residuals if isinstance(item, dict)]
        if isinstance(residuals, list)
        else []
    )
    declared_kinds = {
        str(item.get("kind")) for item in residual_items if isinstance(item.get("kind"), str)
    }
    blocking_kinds = {
        str(item.get("kind")) for item in residual_items if item.get("blocking") is True
    }
    reported_blockers = {
        str(item) for item in report.get("settled_blockers", []) if isinstance(item, str)
    }
    if settled and (blocking_kinds or reported_blockers):
        blockers.append("settled_with_blockers")
    safe_commands = report.get("safe_commands")
    if safe_commands is not None and not isinstance(safe_commands, list):
        blockers.append("safe_commands_not_list")
        safe_commands = []
    if any(not isinstance(item, str) or not item.strip() for item in safe_commands or []):
        blockers.append("invalid_safe_command_hint")
    claimed_digest = report.get("report_digest")
    digest_input = {key: value for key, value in report.items() if key != "report_digest"}
    computed_digest = sha256_json(digest_input)
    if claimed_digest is not None and claimed_digest != computed_digest:
        blockers.append("report_digest_mismatch")
    return {
        "accepted": accepted and not blockers,
        "blockers": sorted(set(blockers)),
        "candidate_only": True,
        "computed_report_digest": computed_digest,
        "pic_version": pic_version,
        "residual_kind_set": sorted(declared_kinds),
        "safe_command_hints_executed": False,
        "schema_version": "ccr.pic_contract_report.v1",
        "settled": False,
        "source_report_settled": settled,
    }


def _major_minor(version: str) -> tuple[int, int] | None:
    try:
        parts = version.split(".")
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None
