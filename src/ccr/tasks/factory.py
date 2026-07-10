# SPDX-License-Identifier: Apache-2.0
"""Schema-compatible task construction."""

from __future__ import annotations

from typing import Any

from ccr.ids import stable_id

FIXED_CREATED_AT = "1970-01-01T00:00:00Z"


def build_task(
    *,
    kind: str,
    title: str,
    objective: str,
    role: str,
    source: str,
    priority: int = 50,
    inputs: list[dict[str, Any]] | None = None,
    extensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a conservative, dry-run CCR task."""

    task_id = stable_id("task", kind, role, source, objective)
    return {
        "blackboard_refs": [],
        "completion": {},
        "constraints": {
            "allowed_commands": [],
            "authority_policy": "read_only",
            "forbidden_actions": ["automatic_execution", "shell_expansion"],
            "max_runtime_minutes": 30,
            "network_policy": "none",
            "side_effect_policy": "dry_run_only",
        },
        "created_at": FIXED_CREATED_AT,
        "dependencies": [],
        "expected_outputs": [
            {
                "acceptance_criteria": ["Residuals must be preserved."],
                "destination": "tasks/open",
                "kind": "json",
                "schema_ref": "schemas/task.schema.json",
            }
        ],
        "extensions": {"x_ccr_task_kind": kind, **(extensions or {})},
        "inputs": inputs or [],
        "lease": {
            "lease_required": True,
            "leased_at": None,
            "leased_by": None,
            "renewal_allowed": True,
            "ttl_minutes": 30,
        },
        "objective": objective,
        "pic_interop": {
            "candidate_only_until_checked": True,
            "enabled": True,
            "identity_context_required": False,
            "input_mapping": "none",
            "output_mapping": "none",
            "pic_profile": "development",
            "recommended_pic_commands": [],
        },
        "priority": max(0, min(100, priority)),
        "residual_policy": {
            "blocking_residuals_prevent_settlement": True,
            "minimum_residual_fields": ["residual_id", "kind", "description", "blocking"],
            "preserve_residuals": True,
            "residual_destination": "residuals/open",
        },
        "role": role,
        "schema_version": "ccr.task.v0.1",
        "status": "open",
        "task_id": task_id,
        "title": title,
        "verifier_plan": {
            "failure_route": "residual",
            "optional_verifiers": ["pic"],
            "promotion_gate": "none",
            "required_verifiers": [],
        },
    }
