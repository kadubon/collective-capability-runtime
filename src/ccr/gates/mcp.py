# SPDX-License-Identifier: Apache-2.0
"""Read-only MCP descriptor and invocation gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

READ_ONLY_SIDE_EFFECTS = {"none", "read_only", "read-only", "idempotent_read"}
KNOWN_SIDE_EFFECTS = {
    *READ_ONLY_SIDE_EFFECTS,
    "dry_run_only",
    "dry-run-only",
    "local_write",
    "write",
    "external_side_effect",
}
NETWORK_FREE_POLICIES = {"none", "disabled", "local_only", "local-only"}
KNOWN_EGRESS_POLICIES = {*NETWORK_FREE_POLICIES, "explicit_source_only", "network", "unknown"}


def inspect_descriptor(
    path: Path,
    *,
    policy_path: Path | None = None,
    approved_hash: str | None = None,
    authority: str | None = None,
) -> dict[str, Any]:
    """Inspect an MCP tool descriptor without connecting to the server."""

    policy = _read_optional_policy(policy_path)
    read = read_json_bounded(path, source="ccr.mcp.inspect_descriptor")
    if not read.get("ok"):
        residual = read["residual_ready"]
        residuals = [*policy["residuals"], residual]
        return _descriptor_report(
            {},
            residuals,
            source=str(read.get("display", path.name)),
            authority=authority,
            policy=policy["data"],
        )
    descriptor = read["data"]
    residuals = [
        *policy["residuals"],
        *_descriptor_residuals(
            descriptor,
            source=str(read["display"]),
            policy=policy["data"],
            approved_hash=approved_hash,
            authority=authority,
        ),
    ]
    return _descriptor_report(
        descriptor,
        residuals,
        source=str(read["display"]),
        authority=authority,
        policy=policy["data"],
    )


def preflight_invocation(
    descriptor_path: Path,
    invocation_path: Path,
    *,
    policy_path: Path | None = None,
    approved_hash: str | None = None,
    authority: str | None = None,
    descriptor_report_path: Path | None = None,
) -> dict[str, Any]:
    """Preflight an MCP invocation without dispatching it."""

    descriptor_report = inspect_descriptor(
        descriptor_path,
        policy_path=policy_path,
        approved_hash=approved_hash,
        authority=authority,
    )
    residuals = list(descriptor_report.get("residuals", []))
    descriptor = _read_json_data(descriptor_path, source="ccr.mcp.preflight.descriptor")
    policy = _read_optional_policy(policy_path)
    residuals.extend(policy["residuals"])
    if descriptor_report_path is not None:
        residuals.extend(
            _descriptor_report_residuals(
                descriptor_report_path,
                current_hash=str(descriptor_report.get("descriptor_hash", "")),
            )
        )
    read = read_json_bounded(invocation_path, source="ccr.mcp.preflight")
    invocation: dict[str, Any] = {}
    source = str(read.get("display", invocation_path.name))
    if not read.get("ok"):
        residuals.append(read["residual_ready"])
    else:
        invocation = read["data"]
        residuals.extend(
            _invocation_residuals(
                invocation,
                descriptor=descriptor,
                descriptor_report=descriptor_report,
                source=source,
                policy=policy["data"],
            )
        )
    blockers = _blocker_kinds(residuals)
    invocation_ready = not blockers
    authority_decision = _authority_decision(residuals, authority=authority)
    return {
        "accepted": invocation_ready,
        "authority_decision": authority_decision,
        "blockers": blockers,
        "canonical_tool_name": descriptor_report.get("canonical_tool_name", ""),
        "descriptor_hash": descriptor_report.get("descriptor_hash", ""),
        "executed": False,
        "external_execution": False,
        "invocation_hash": _hash_json(invocation) if invocation else "",
        "invocation_ready": invocation_ready,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": invocation_ready,
        "provider_dispatch_ready": invocation_ready,
        "residuals": residuals,
        "schema_version": "ccr.mcp_tool_invocation_preflight.v1",
        "settled": False,
    }


def _descriptor_report(
    descriptor: dict[str, Any],
    residuals: list[dict[str, Any]],
    *,
    source: str,
    authority: str | None,
    policy: dict[str, Any],
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    accepted = not blockers
    return {
        "accepted": accepted,
        "authority_decision": _authority_decision(residuals, authority=authority),
        "blockers": blockers,
        "canonical_tool_name": _canonical_tool_name(descriptor),
        "descriptor_hash": _hash_json(descriptor) if descriptor else "",
        "executed": False,
        "external_execution": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "policy_id": str(policy.get("policy_id", "")) if policy else "",
        "provider_dispatch_ready": False,
        "residuals": residuals,
        "schema_version": "ccr.mcp_tool_descriptor_report.v1",
        "settled": False,
        "source": source,
    }


def _descriptor_residuals(
    descriptor: dict[str, Any],
    *,
    source: str,
    policy: dict[str, Any],
    approved_hash: str | None,
    authority: str | None,
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    descriptor_hash = _hash_json(descriptor)
    policy_approved_hash = _policy_string(policy, "approved_hash", "descriptor_hash")
    expected_hash = approved_hash or policy_approved_hash
    if expected_hash and expected_hash != descriptor_hash:
        residuals.append(
            residual_ready(
                "stale_source",
                source,
                "MCP descriptor hash does not match the approved descriptor hash.",
                "ccr.mcp.inspect_descriptor",
                extensions={"approved_hash": expected_hash, "descriptor_hash": descriptor_hash},
            )
        )
    if not _canonical_tool_name(descriptor):
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "MCP descriptor is missing tool_name/name.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    if not descriptor.get("server_id"):
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "MCP descriptor is missing server_id.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    allowed_side_effects = _policy_string_set(policy, "allowed_side_effect_classes")
    if not allowed_side_effects:
        allowed_side_effects = set(READ_ONLY_SIDE_EFFECTS)
    side_effect = str(descriptor.get("side_effect_class", "unknown")).lower()
    if side_effect not in KNOWN_SIDE_EFFECTS:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor side_effect_class is unknown: {side_effect}",
                "ccr.mcp.inspect_descriptor",
            )
        )
    elif side_effect not in allowed_side_effects:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor side_effect_class is outside policy: {side_effect}",
                "ccr.mcp.inspect_descriptor",
            )
        )
    if side_effect not in READ_ONLY_SIDE_EFFECTS and not authority:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "MCP descriptor requires explicit authority for non-read side effects.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    allowed_egress = _policy_string_set(policy, "allowed_egress_policies")
    if not allowed_egress:
        allowed_egress = set(NETWORK_FREE_POLICIES)
    egress = str(descriptor.get("egress_policy", "unknown")).lower()
    if egress not in KNOWN_EGRESS_POLICIES:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor egress_policy is unknown: {egress}",
                "ccr.mcp.inspect_descriptor",
            )
        )
    elif egress not in allowed_egress:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor egress_policy is outside policy: {egress}",
                "ccr.mcp.inspect_descriptor",
            )
        )
    if egress not in NETWORK_FREE_POLICIES and not authority:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "MCP descriptor requires explicit authority for network egress.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    if descriptor.get("descriptor_changed_after_approval") is True:
        residuals.append(
            residual_ready(
                "stale_source",
                source,
                "MCP descriptor changed after approval.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    text = canonical_dumps(descriptor).lower()
    if "ignore previous instructions" in text or "rug pull" in text:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                "MCP descriptor contains instruction-injection risk text.",
                "ccr.mcp.inspect_descriptor",
            )
        )
    return residuals


def _invocation_residuals(
    invocation: dict[str, Any],
    *,
    descriptor: dict[str, Any],
    descriptor_report: dict[str, Any],
    source: str,
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    tool_name = str(invocation.get("tool_name") or invocation.get("name") or "")
    descriptor_tool = str(descriptor_report.get("canonical_tool_name", ""))
    if not tool_name:
        residuals.append(
            residual_ready(
                "missing_evidence",
                source,
                "MCP invocation is missing tool_name/name.",
                "ccr.mcp.preflight",
            )
        )
    elif descriptor_tool and tool_name != descriptor_tool:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                "MCP invocation tool_name does not match the descriptor tool.",
                "ccr.mcp.preflight",
                extensions={
                    "descriptor_tool_name": descriptor_tool,
                    "invocation_tool_name": tool_name,
                },
            )
        )
    residuals.extend(_schema_binding_residuals(invocation, descriptor, policy, source=source))
    residuals.extend(_boolean_disagreement_residuals(invocation, source=source))
    if invocation.get("execute") is True or invocation.get("dispatch") is True:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "MCP invocation preflight must not request execution or dispatch.",
                "ccr.mcp.preflight",
            )
        )
    if invocation.get("network_call_performed") is True:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                "MCP invocation preflight input claims a network call was performed.",
                "ccr.mcp.preflight",
            )
        )
    return residuals


def _schema_binding_residuals(
    invocation: dict[str, Any],
    descriptor: dict[str, Any],
    policy: dict[str, Any],
    *,
    source: str,
) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    descriptor_hash = _first_string(descriptor, "input_schema_hash", "schema_hash")
    invocation_hash = _first_string(invocation, "input_schema_hash", "schema_hash")
    policy_hash = _policy_string(policy, "input_schema_hash", "schema_hash")
    expected_hash = policy_hash or descriptor_hash
    if expected_hash and invocation_hash and expected_hash != invocation_hash:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                "MCP invocation schema hash does not match descriptor/policy.",
                "ccr.mcp.preflight",
                extensions={
                    "expected_schema_hash": expected_hash,
                    "invocation_schema_hash": invocation_hash,
                },
            )
        )
    descriptor_ref = _first_string(descriptor, "input_schema_ref", "schema_ref")
    invocation_ref = _first_string(invocation, "input_schema_ref", "schema_ref")
    policy_ref = _policy_string(policy, "input_schema_ref", "schema_ref")
    expected_ref = policy_ref or descriptor_ref
    if expected_ref and invocation_ref and expected_ref != invocation_ref:
        residuals.append(
            residual_ready(
                "validation_error",
                source,
                "MCP invocation schema ref does not match descriptor/policy.",
                "ccr.mcp.preflight",
                extensions={
                    "expected_schema_ref": expected_ref,
                    "invocation_schema_ref": invocation_ref,
                },
            )
        )
    return residuals


def _boolean_disagreement_residuals(value: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    keys = ("ok", "accepted", "invocation_ready", "ready")
    booleans = {key: value[key] for key in keys if isinstance(value.get(key), bool)}
    if len(set(booleans.values())) <= 1:
        return []
    return [
        residual_ready(
            "validation_error",
            source,
            "MCP invocation contains disagreeing legacy/structured boolean fields.",
            "ccr.mcp.preflight",
            extensions={"boolean_fields": booleans},
        )
    ]


def _descriptor_report_residuals(path: Path, *, current_hash: str) -> list[dict[str, Any]]:
    read = read_json_bounded(path, source="ccr.mcp.descriptor_report")
    source = str(read.get("display", path.name))
    if not read.get("ok"):
        return [read["residual_ready"]]
    report = read["data"]
    residuals = _boolean_disagreement_residuals(report, source=source)
    approved = str(report.get("descriptor_hash", ""))
    if approved and approved != current_hash:
        residuals.append(
            residual_ready(
                "stale_source",
                source,
                "MCP descriptor report hash does not match the current descriptor.",
                "ccr.mcp.descriptor_report",
                extensions={"approved_hash": approved, "descriptor_hash": current_hash},
            )
        )
    return residuals


def _canonical_tool_name(descriptor: dict[str, Any]) -> str:
    value = descriptor.get("tool_name") or descriptor.get("name")
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
    read = read_json_bounded(path, source="ccr.mcp.policy")
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


def _policy_string_set(policy: dict[str, Any], key: str) -> set[str]:
    value = policy.get(key)
    if not isinstance(value, list):
        return set()
    return {str(item).lower() for item in value if isinstance(item, str) and item}


def _first_string(value: dict[str, Any], *keys: str) -> str:
    for key in keys:
        item = value.get(key)
        if isinstance(item, str) and item:
            return item
    return ""
