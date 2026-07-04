# SPDX-License-Identifier: Apache-2.0
"""Read-only A2A card and handoff gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

READ_ONLY_SCOPES = {"read", "read_only", "read-only", "diagnostic", "none"}


def inspect_agent_card(path: Path) -> dict[str, Any]:
    """Inspect an A2A agent card without contacting the agent."""

    read = read_json_bounded(path, source="ccr.a2a.inspect_card")
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _card_report({}, [residual], source=str(read.get("display", path.name)))
    card = read["data"]
    residuals = _card_residuals(card, source=str(read["display"]))
    return _card_report(card, residuals, source=str(read["display"]))


def preflight_handoff(handoff_path: Path, *, card_path: Path | None = None) -> dict[str, Any]:
    """Preflight an A2A task handoff without delegating execution."""

    residuals: list[dict[str, Any]] = []
    agent_id = ""
    if card_path is not None:
        card_report = inspect_agent_card(card_path)
        residuals.extend(card_report.get("residuals", []))
        agent_id = str(card_report.get("agent_id", ""))
    read = read_json_bounded(handoff_path, source="ccr.a2a.preflight_handoff")
    handoff: dict[str, Any] = {}
    source = str(read.get("display", handoff_path.name))
    if not read.get("ok"):
        residuals.append(read["residual_ready"])
    else:
        handoff = read["data"]
        residuals.extend(_handoff_residuals(handoff, source=source))
        agent_id = agent_id or str(handoff.get("agent_card_ref", ""))
    blockers = _blocker_kinds(residuals)
    accepted = not blockers
    return {
        "accepted": accepted,
        "agent_id": agent_id,
        "blockers": blockers,
        "delegated_tool_execution": False,
        "executed": False,
        "handoff_hash": _hash_json(handoff) if handoff else "",
        "handoff_id": str(handoff.get("handoff_id", "")) if handoff else "",
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "residuals": residuals,
        "schema_version": "ccr.a2a_task_handoff_report.v1",
        "settled": False,
    }


def _card_report(
    card: dict[str, Any],
    residuals: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    agent_id = _agent_id(card)
    accepted = not blockers
    return {
        "accepted": accepted,
        "agent_card_hash": _hash_json(card) if card else "",
        "agent_id": agent_id,
        "blockers": blockers,
        "external_execution": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "residuals": residuals,
        "schema_version": "ccr.a2a_agent_card_report.v1",
        "settled": False,
        "source": source,
    }


def _card_residuals(card: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    if not _agent_id(card):
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "A2A agent card is missing agent_id/id.",
                "ccr.a2a.inspect_card",
            )
        )
    authority = card.get("declared_authority")
    authority_text = canonical_dumps(authority).lower() if isinstance(authority, dict) else ""
    if authority_text and not any(scope in authority_text for scope in READ_ONLY_SCOPES):
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A agent card authority is not read-only.",
                "ccr.a2a.inspect_card",
            )
        )
    if "execute" in authority_text or "write" in authority_text or "external" in authority_text:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A agent card declares execution/write/external authority.",
                "ccr.a2a.inspect_card",
            )
        )
    return residuals


def _handoff_residuals(handoff: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    for key in ("handoff_id", "idempotency_key", "replay_nonce"):
        if not handoff.get(key):
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    source,
                    f"A2A handoff is missing {key}.",
                    "ccr.a2a.preflight_handoff",
                )
            )
    scope = str(handoff.get("handoff_scope", "")).lower()
    if scope and scope not in READ_ONLY_SCOPES:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"A2A handoff scope is not read-only: {scope}",
                "ccr.a2a.preflight_handoff",
            )
        )
    authority = handoff.get("declared_authority")
    authority_text = canonical_dumps(authority).lower() if isinstance(authority, dict) else ""
    if "execute" in authority_text or "write" in authority_text or "external" in authority_text:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A handoff declares execution/write/external authority.",
                "ccr.a2a.preflight_handoff",
            )
        )
    return residuals


def _agent_id(card: dict[str, Any]) -> str:
    value = card.get("agent_id") or card.get("id") or card.get("agent_card_ref")
    return str(value) if value else ""


def _blocker_kinds(residuals: list[dict[str, Any]]) -> list[str]:
    kinds = []
    for residual in residuals:
        if residual.get("blocking"):
            extensions = residual.get("extensions")
            if isinstance(extensions, dict) and extensions.get("finding_kind"):
                kinds.append(str(extensions["finding_kind"]))
            else:
                kinds.append(str(residual.get("kind", "validation_error")))
    return sorted(set(kinds))


def _hash_json(value: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
