# SPDX-License-Identifier: Apache-2.0
"""Read-only A2A card and handoff gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

READ_ONLY_SCOPES = {"read", "read_only", "read-only", "diagnostic", "none"}
PROFILES = {"development", "research", "controlled", "federated", "production", "adversarial"}


def inspect_agent_card(
    path: Path,
    *,
    policy_path: Path | None = None,
    approved_hash: str | None = None,
    authority: str | None = None,
    profile: str = "development",
) -> dict[str, Any]:
    """Inspect an A2A agent card without contacting the agent."""

    policy = _read_optional_policy(policy_path)
    read = read_json_bounded(path, source="ccr.a2a.inspect_card")
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _card_report(
            {},
            [*policy["residuals"], residual],
            source=str(read.get("display", path.name)),
            authority=authority,
            profile=profile,
            policy=policy["data"],
        )
    card = read["data"]
    residuals = [
        *policy["residuals"],
        *_card_residuals(
            card,
            source=str(read["display"]),
            policy=policy["data"],
            approved_hash=approved_hash,
            authority=authority,
            profile=profile,
        ),
    ]
    return _card_report(
        card,
        residuals,
        source=str(read["display"]),
        authority=authority,
        profile=profile,
        policy=policy["data"],
    )


def preflight_handoff(
    handoff_path: Path,
    *,
    card_path: Path | None = None,
    policy_path: Path | None = None,
    approved_hash: str | None = None,
    authority: str | None = None,
    profile: str = "development",
) -> dict[str, Any]:
    """Preflight an A2A task handoff without delegating execution."""

    policy = _read_optional_policy(policy_path)
    residuals: list[dict[str, Any]] = []
    residuals.extend(policy["residuals"])
    agent_id = ""
    card: dict[str, Any] = {}
    card_hash = ""
    if card_path is not None:
        card_report = inspect_agent_card(
            card_path,
            policy_path=policy_path,
            approved_hash=approved_hash,
            authority=authority,
            profile=profile,
        )
        residuals.extend(card_report.get("residuals", []))
        agent_id = str(card_report.get("agent_id", ""))
        card_hash = str(card_report.get("agent_card_hash", ""))
        card = _read_json_data(card_path, source="ccr.a2a.preflight.card")
    read = read_json_bounded(handoff_path, source="ccr.a2a.preflight_handoff")
    handoff: dict[str, Any] = {}
    source = str(read.get("display", handoff_path.name))
    if not read.get("ok"):
        residuals.append(read["residual_ready"])
    else:
        handoff = read["data"]
        residuals.extend(
            _handoff_residuals(
                handoff,
                source=source,
                card=card,
                agent_id=agent_id,
                profile=profile,
                policy=policy["data"],
                authority=authority,
            )
        )
        agent_id = agent_id or str(handoff.get("agent_card_ref", ""))
    blockers = _blocker_kinds(residuals)
    accepted = not blockers
    return {
        "accepted": accepted,
        "agent_id": agent_id,
        "agent_card_hash": card_hash,
        "authority_decision": _authority_decision(residuals, authority=authority),
        "blockers": blockers,
        "delegated_tool_execution": False,
        "executed": False,
        "external_execution": False,
        "handoff_hash": _hash_json(handoff) if handoff else "",
        "handoff_id": str(handoff.get("handoff_id", "")) if handoff else "",
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "profile": profile,
        "residuals": residuals,
        "schema_version": "ccr.a2a_task_handoff_report.v1",
        "settled": False,
    }


def _card_report(
    card: dict[str, Any],
    residuals: list[dict[str, Any]],
    *,
    source: str,
    authority: str | None,
    profile: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    agent_id = _agent_id(card)
    accepted = not blockers
    return {
        "accepted": accepted,
        "agent_card_hash": _hash_json(card) if card else "",
        "agent_id": agent_id,
        "authority_decision": _authority_decision(residuals, authority=authority),
        "blockers": blockers,
        "external_execution": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "policy_id": str(policy.get("policy_id", "")) if policy else "",
        "profile": profile,
        "residuals": residuals,
        "schema_version": "ccr.a2a_agent_card_report.v1",
        "settled": False,
        "source": source,
    }


def _card_residuals(
    card: dict[str, Any],
    *,
    source: str,
    policy: dict[str, Any],
    approved_hash: str | None,
    authority: str | None,
    profile: str,
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    if profile not in PROFILES:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                f"A2A profile is unknown: {profile}",
                "ccr.a2a.inspect_card",
            )
        )
    card_hash = _hash_json(card)
    expected_hash = approved_hash or _policy_string(policy, "approved_hash", "agent_card_hash")
    if expected_hash and expected_hash != card_hash:
        residuals.append(
            residual_ready(
                "stale_source",
                source,
                "A2A agent card hash does not match the approved card hash.",
                "ccr.a2a.inspect_card",
                extensions={"approved_hash": expected_hash, "agent_card_hash": card_hash},
            )
        )
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
    if not authority_text and not authority:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A agent card is missing declared authority.",
                "ccr.a2a.inspect_card",
            )
        )
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
    if _has_endpoint(card) and not _has_endpoint_provenance(card):
        allow_fixture = bool(policy.get("allow_fixture_endpoint_provenance"))
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "A2A agent card endpoint is missing endpoint provenance.",
                "ccr.a2a.inspect_card",
                blocking=not (profile == "development" and allow_fixture),
                severity="low" if profile == "development" and allow_fixture else "high",
            )
        )
    return residuals


def _handoff_residuals(
    handoff: dict[str, Any],
    *,
    source: str,
    card: dict[str, Any],
    agent_id: str,
    profile: str,
    policy: dict[str, Any],
    authority: str | None,
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    for key in ("handoff_id",):
        if not handoff.get(key):
            residuals.append(
                residual_ready(
                    "missing_evidence",
                    source,
                    f"A2A handoff is missing {key}.",
                    "ccr.a2a.preflight_handoff",
                )
            )
    for key in ("idempotency_key", "replay_nonce"):
        if handoff.get(key):
            continue
        strict = profile in {"production", "adversarial"}
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                f"A2A handoff is missing {key}.",
                "ccr.a2a.preflight_handoff",
                blocking=strict,
                severity="high" if strict else "low",
            )
        )
    handoff_agent = str(handoff.get("agent_card_ref", ""))
    if agent_id and handoff_agent and handoff_agent != agent_id:
        residuals.append(
            residual_ready(
                "identity_gap",
                source,
                "A2A handoff agent_card_ref does not match the inspected agent card.",
                "ccr.a2a.preflight_handoff",
                extensions={"agent_id": agent_id, "handoff_agent_card_ref": handoff_agent},
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
    card_scopes = _card_scopes(card)
    if scope and card_scopes and scope not in card_scopes:
        residuals.append(
            residual_ready(
                "scope_gap",
                source,
                "A2A handoff scope is not present in the agent card authority/capabilities.",
                "ccr.a2a.preflight_handoff",
                extensions={"agent_card_scopes": sorted(card_scopes), "handoff_scope": scope},
            )
        )
    authority = handoff.get("declared_authority")
    authority_text = canonical_dumps(authority).lower() if isinstance(authority, dict) else ""
    if not authority_text and not authority:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A handoff is missing declared authority.",
                "ccr.a2a.preflight_handoff",
            )
        )
    if "execute" in authority_text or "write" in authority_text or "external" in authority_text:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A handoff declares execution/write/external authority.",
                "ccr.a2a.preflight_handoff",
            )
        )
    if handoff.get("delegate_execution") is True or handoff.get("execute") is True:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "A2A handoff preflight must not request delegated execution.",
                "ccr.a2a.preflight_handoff",
            )
        )
    if _has_endpoint(handoff) and not _has_endpoint_provenance(handoff):
        allow_fixture = bool(policy.get("allow_fixture_endpoint_provenance"))
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "A2A handoff endpoint is missing endpoint provenance.",
                "ccr.a2a.preflight_handoff",
                blocking=not (profile == "development" and allow_fixture),
                severity="low" if profile == "development" and allow_fixture else "high",
            )
        )
    return residuals


def _agent_id(card: dict[str, Any]) -> str:
    value = card.get("agent_id") or card.get("id") or card.get("agent_card_ref")
    return str(value) if value else ""


def _authority_decision(
    residuals: list[dict[str, Any]], *, authority: str | None
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    return {
        "authority": authority or "",
        "blockers": blockers,
        "decision": "approved" if not blockers else "blocked",
    }


def _has_endpoint(value: dict[str, Any]) -> bool:
    return any(key in value for key in ("endpoint", "endpoint_url", "url", "base_url"))


def _has_endpoint_provenance(value: dict[str, Any]) -> bool:
    provenance = value.get("endpoint_provenance") or value.get("provenance")
    if not isinstance(provenance, dict):
        return False
    return bool(provenance.get("source") or provenance.get("ref") or provenance.get("hash"))


def _card_scopes(card: dict[str, Any]) -> set[str]:
    scopes: set[str] = set()
    authority = card.get("declared_authority")
    if isinstance(authority, dict):
        raw_scope = authority.get("scope") or authority.get("scopes")
        if isinstance(raw_scope, str):
            scopes.add(raw_scope.lower())
        elif isinstance(raw_scope, list):
            scopes.update(str(item).lower() for item in raw_scope if isinstance(item, str))
    capabilities = card.get("capabilities")
    if isinstance(capabilities, list):
        text = " ".join(str(item).lower() for item in capabilities)
        for scope in READ_ONLY_SCOPES:
            if scope in text:
                scopes.add(scope)
    return scopes


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


def _read_optional_policy(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"data": {}, "residuals": []}
    read = read_json_bounded(path, source="ccr.a2a.policy")
    if not read.get("ok"):
        return {"data": {}, "residuals": [read["residual_ready"]]}
    return {"data": read["data"], "residuals": []}


def _read_json_data(path: Path, *, source: str) -> dict[str, Any]:
    read = read_json_bounded(path, source=source)
    if read.get("ok") and isinstance(read.get("data"), dict):
        return cast(dict[str, Any], read["data"])
    return {}


def _policy_string(policy: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = policy.get(key)
        if isinstance(value, str) and value:
            return value
    return ""
