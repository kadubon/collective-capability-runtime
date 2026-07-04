# SPDX-License-Identifier: Apache-2.0
"""Read-only MCP descriptor and invocation gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ccr.io import canonical_dumps
from ccr.mission.model import MISSION_NON_CLAIMS
from ccr.safe_io import read_json_bounded, residual_ready

READ_ONLY_SIDE_EFFECTS = {"none", "read_only", "read-only", "idempotent_read"}
NETWORK_FREE_POLICIES = {"none", "disabled", "local_only", "local-only"}


def inspect_descriptor(path: Path) -> dict[str, Any]:
    """Inspect an MCP tool descriptor without connecting to the server."""

    read = read_json_bounded(path, source="ccr.mcp.inspect_descriptor")
    if not read.get("ok"):
        residual = read["residual_ready"]
        return _descriptor_report({}, [residual], source=str(read.get("display", path.name)))
    descriptor = read["data"]
    residuals = _descriptor_residuals(descriptor, source=str(read["display"]))
    return _descriptor_report(descriptor, residuals, source=str(read["display"]))


def preflight_invocation(descriptor_path: Path, invocation_path: Path) -> dict[str, Any]:
    """Preflight an MCP invocation without dispatching it."""

    descriptor_report = inspect_descriptor(descriptor_path)
    residuals = list(descriptor_report.get("residuals", []))
    read = read_json_bounded(invocation_path, source="ccr.mcp.preflight")
    invocation: dict[str, Any] = {}
    source = str(read.get("display", invocation_path.name))
    if not read.get("ok"):
        residuals.append(read["residual_ready"])
    else:
        invocation = read["data"]
        residuals.extend(_invocation_residuals(invocation, source=source))
    blockers = _blocker_kinds(residuals)
    invocation_ready = not blockers
    return {
        "accepted": invocation_ready,
        "blockers": blockers,
        "canonical_tool_name": descriptor_report.get("canonical_tool_name", ""),
        "descriptor_hash": descriptor_report.get("descriptor_hash", ""),
        "executed": False,
        "invocation_hash": _hash_json(invocation) if invocation else "",
        "invocation_ready": invocation_ready,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": invocation_ready,
        "residuals": residuals,
        "schema_version": "ccr.mcp_tool_invocation_preflight.v1",
        "settled": False,
    }


def _descriptor_report(
    descriptor: dict[str, Any],
    residuals: list[dict[str, Any]],
    *,
    source: str,
) -> dict[str, Any]:
    blockers = _blocker_kinds(residuals)
    accepted = not blockers
    return {
        "accepted": accepted,
        "blockers": blockers,
        "canonical_tool_name": _canonical_tool_name(descriptor),
        "descriptor_hash": _hash_json(descriptor) if descriptor else "",
        "external_execution": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": accepted,
        "residuals": residuals,
        "schema_version": "ccr.mcp_tool_descriptor_report.v1",
        "settled": False,
        "source": source,
    }


def _descriptor_residuals(descriptor: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
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
    side_effect = str(descriptor.get("side_effect_class", "unknown")).lower()
    if side_effect not in READ_ONLY_SIDE_EFFECTS:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor side_effect_class is not read-only: {side_effect}",
                "ccr.mcp.inspect_descriptor",
            )
        )
    egress = str(descriptor.get("egress_policy", "unknown")).lower()
    if egress not in NETWORK_FREE_POLICIES:
        residuals.append(
            residual_ready(
                "authority_gap",
                source,
                f"MCP descriptor egress_policy is not network-free: {egress}",
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


def _invocation_residuals(invocation: dict[str, Any], *, source: str) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
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


def _canonical_tool_name(descriptor: dict[str, Any]) -> str:
    value = descriptor.get("tool_name") or descriptor.get("name")
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
