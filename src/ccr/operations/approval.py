# SPDX-License-Identifier: Apache-2.0
"""Parameter-bound approvals for TRC operation dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json, stable_id, validate_identifier
from ccr.io import json_file_name, read_json, write_json_atomic
from ccr.safe_io import require_path_within_root
from ccr.schemas.validation import validate_instance
from ccr.storage.sqlite import immediate_transaction
from ccr.time import now_iso

APPROVAL_SCHEMA_VERSION = "ccr.operation_approval.v1"
_PHYSICAL_POLICIES = {"physical_provider_allowed", "irreversible_operation_allowed"}


def create_operation_approval(
    root: Path,
    *,
    plan: dict[str, Any],
    provider: str,
    config: dict[str, Any],
    approvers: list[str],
    expires_at: str,
    nonce: str,
    max_uses: int = 1,
) -> dict[str, Any]:
    """Create an immutable approval bound to one exact dispatch parameter set."""

    validate_identifier(provider, field="provider")
    validate_identifier(nonce, field="approval nonce")
    identities = sorted({item.strip() for item in approvers if item.strip()})
    required = _required_approver_count(config)
    if len(identities) < required:
        raise ValueError(f"operation requires {required} distinct approver identities")
    if max_uses < 1:
        raise ValueError("max_uses must be positive")
    expiry = _parse_time(expires_at)
    if expiry is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("expires_at must be a future timezone-aware timestamp")
    plan_digest = sha256_json(plan)
    config_digest = dispatch_config_digest(config)
    scope_digest = sha256_json(_plan_scope(plan))
    resource_limits_digest = sha256_json(_plan_resources(plan))
    approval_id = stable_id(
        "approval",
        plan_digest,
        provider,
        config_digest,
        scope_digest,
        resource_limits_digest,
        identities,
        expires_at,
        nonce,
        max_uses,
    )
    approval = {
        "approval_id": approval_id,
        "approvers": [{"identity": identity, "attested": True} for identity in identities],
        "config_digest": config_digest,
        "created_at": now_iso(),
        "expires_at": expires_at,
        "max_uses": max_uses,
        "nonce": nonce,
        "plan_digest": plan_digest,
        "plan_id": plan.get("plan_id"),
        "provider": provider,
        "resource_limits_digest": resource_limits_digest,
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "scope_digest": scope_digest,
        "side_effect_policy": config.get("side_effect_policy"),
    }
    validation = validate_instance("operation-approval", approval, root=root)
    if not validation.ok:
        messages = "; ".join(issue.message for issue in validation.errors)
        raise ValueError(f"invalid operation approval: {messages}")
    path = approval_path(root, approval_id)
    write_json_atomic(path, approval, overwrite=False)
    with immediate_transaction(root) as connection:
        connection.execute(
            """
            INSERT INTO operation_approvals(
              approval_id, approval_digest, plan_digest, provider, use_count,
              max_uses, expires_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                approval_id,
                sha256_json(approval),
                plan_digest,
                provider,
                max_uses,
                expires_at,
                now_iso(),
            ),
        )
    return {"approval": approval, "ok": True, "path": str(path)}


def validate_and_consume_approval(
    root: Path,
    *,
    plan: dict[str, Any],
    provider: str,
    config: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any] | None]:
    """Validate current dispatch parameters and atomically consume one use."""

    approval_ref = config.get("operator_approval_ref")
    if not isinstance(approval_ref, str) or not approval_ref:
        return False, "operator_approval_required", None
    try:
        approval = _load_approval(root, approval_ref)
    except (FileNotFoundError, ValueError):
        return False, "operator_approval_invalid", None
    checks = {
        "approval_schema_invalid": approval.get("schema_version") == APPROVAL_SCHEMA_VERSION,
        "approval_plan_mismatch": approval.get("plan_digest") == sha256_json(plan),
        "approval_provider_mismatch": approval.get("provider") == provider,
        "approval_config_mismatch": approval.get("config_digest") == dispatch_config_digest(config),
        "approval_scope_mismatch": approval.get("scope_digest") == sha256_json(_plan_scope(plan)),
        "approval_resource_mismatch": approval.get("resource_limits_digest")
        == sha256_json(_plan_resources(plan)),
        "approval_nonce_mismatch": approval.get("nonce") == config.get("approval_nonce"),
    }
    for failure, passed in checks.items():
        if not passed:
            return False, failure, approval
    expiry = _parse_time(approval.get("expires_at"))
    if expiry is None or expiry <= datetime.now(timezone.utc):
        return False, "approval_expired", approval
    identities = {
        str(item.get("identity"))
        for item in approval.get("approvers", [])
        if isinstance(item, dict) and item.get("attested") is True and item.get("identity")
    }
    if len(identities) < _required_approver_count(config):
        return False, "approval_separation_of_duties_failed", approval
    approval_id = str(approval.get("approval_id", ""))
    with immediate_transaction(root) as connection:
        row = connection.execute(
            """
            SELECT approval_digest, use_count, max_uses, expires_at
            FROM operation_approvals WHERE approval_id = ?
            """,
            (approval_id,),
        ).fetchone()
        if row is None or str(row[0]) != sha256_json(approval):
            return False, "approval_registry_mismatch", approval
        if int(row[1]) >= int(row[2]):
            return False, "approval_replayed", approval
        registry_expiry = _parse_time(row[3])
        if registry_expiry is None or registry_expiry <= datetime.now(timezone.utc):
            return False, "approval_expired", approval
        connection.execute(
            """
            UPDATE operation_approvals
            SET use_count = use_count + 1, updated_at = ?
            WHERE approval_id = ?
            """,
            (now_iso(), approval_id),
        )
    return True, None, approval


def dispatch_config_digest(config: dict[str, Any]) -> str:
    """Digest dispatch config without the approval locator and nonce echo."""

    bound = {
        key: value
        for key, value in config.items()
        if key not in {"operator_approval_ref", "approval_nonce"}
    }
    return sha256_json(bound)


def approval_path(root: Path, approval_id: str) -> Path:
    validate_identifier(approval_id, field="approval_id")
    path = root / "operations" / "approvals" / json_file_name(approval_id)
    return require_path_within_root(path, root, field="approval path")


def _load_approval(root: Path, approval_ref: str) -> dict[str, Any]:
    path = approval_path(root, approval_ref)
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("approval must be a JSON object")
    return value


def _required_approver_count(config: dict[str, Any]) -> int:
    return 2 if config.get("side_effect_policy") in _PHYSICAL_POLICIES else 1


def _plan_scope(plan: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action_type": operation.get("action_type"),
            "authority_envelope": operation.get("authority_envelope"),
            "input_ref": operation.get("input_ref"),
            "postcondition": operation.get("postcondition"),
            "precondition": operation.get("precondition"),
            "step_id": operation.get("step_id"),
            "tool_call": operation.get("tool_call"),
            "validity_domain": operation.get("validity_domain"),
        }
        for operation in plan.get("operations", [])
        if isinstance(operation, dict)
    ]


def _plan_resources(plan: dict[str, Any]) -> list[Any]:
    return [
        operation.get("resource_use")
        for operation in plan.get("operations", [])
        if isinstance(operation, dict)
    ]


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
