# SPDX-License-Identifier: Apache-2.0
"""Mission-scoped residual work market surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.mission.model import MISSION_NON_CLAIMS, mission_scope
from ccr.residuals.store import iter_residuals
from ccr.safe_io import read_json_bounded, residual_ready
from ccr.tasks.store import submit_task, validate_task
from ccr.time import now_iso

SEVERITY_SCORE = {"critical": 100, "high": 80, "medium": 50, "low": 20, "info": 5}
ROLE_BY_KIND = {
    "authority_gap": "security_reviewer",
    "dependency_gap": "integrator",
    "hazard": "security_reviewer",
    "identity_gap": "verifier",
    "missing_evidence": "librarian",
    "provider_missing": "pic_adapter",
    "queue_overload": "scheduler",
    "safe_command_hint": "implementer",
    "settlement_blocker": "verifier",
    "stale_source": "librarian",
    "unverified_claim": "skeptic",
    "validation_error": "verifier",
}


def residual_market(root: Path, *, mission_id: str) -> dict[str, Any]:
    """Rank mission-scoped residual work without changing runtime state."""

    residuals = _mission_residuals(root, mission_id)
    ranked = [_market_item(residual) for residual in residuals]
    return {
        "blockers": [],
        "external_execution": False,
        "market": ranked,
        "mission_id": mission_id,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": True,
        "residual_count": len(ranked),
        "schema_version": "ccr.residual_market.v1",
        "settled": False,
    }


def residual_bounty(
    root: Path,
    *,
    residual_id: str,
    mission_id: str,
    emit_task: bool = False,
) -> dict[str, Any]:
    """Create a static bounty report and optionally emit one local task."""

    residual = _find_residual(root, mission_id=mission_id, residual_id=residual_id)
    if residual is None:
        ready = residual_ready(
            "missing_evidence",
            residual_id,
            f"Residual not found in mission scope: {residual_id}",
            "ccr.residual.bounty",
        )
        return {
            "blockers": ["missing_evidence"],
            "emitted_task_id": "",
            "external_execution": False,
            "mission_id": mission_id,
            "mutated_runtime": False,
            "network_call_performed": False,
            "non_claims": list(MISSION_NON_CLAIMS),
            "ok": False,
            "residual_id": residual_id,
            "residual_ready": [ready],
            "schema_version": "ccr.residual_bounty.v1",
            "settled": False,
        }
    item = _market_item(residual)
    task = _task_for_residual(residual, mission_id=mission_id, item=item)
    task_id = ""
    residuals: list[dict[str, Any]] = []
    mutated = False
    if emit_task:
        validation = validate_task(task, root=root)
        if validation.ok:
            try:
                submit_task(root, task)
                mutated = True
            except FileExistsError:
                pass
            task_id = str(task["task_id"])
        else:
            residuals.append(
                residual_ready(
                    "validation_error",
                    residual_id,
                    "Residual bounty task failed CCR task schema validation.",
                    "ccr.residual.bounty",
                    extensions={"schema_errors": [issue.to_json() for issue in validation.errors]},
                )
            )
    blockers = _blocker_kinds(residuals)
    return {
        "blockers": blockers,
        "bounty": item,
        "emitted_task_id": task_id,
        "external_execution": False,
        "mission_id": mission_id,
        "mutated_runtime": mutated,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "residual_id": residual_id,
        "residual_ready": residuals,
        "schema_version": "ccr.residual_bounty.v1",
        "settled": False,
        "task": task if emit_task else None,
    }


def residual_diff(before: Path, after: Path) -> dict[str, Any]:
    """Compare two residual market/report files without reading live runtime state."""

    before_report = _read_report(before, source="ccr.residual.diff.before")
    after_report = _read_report(after, source="ccr.residual.diff.after")
    residuals = [*before_report["residuals"], *after_report["residuals"]]
    before_ids = _residual_ids(before_report["data"])
    after_ids = _residual_ids(after_report["data"])
    blockers = _blocker_kinds(residuals)
    return {
        "added_residual_ids": sorted(after_ids - before_ids),
        "blockers": blockers,
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "removed_residual_ids": sorted(before_ids - after_ids),
        "residual_ready": residuals,
        "schema_version": "ccr.residual_diff.v1",
        "settled": False,
        "unchanged_residual_ids": sorted(before_ids & after_ids),
    }


def _mission_residuals(root: Path, mission_id: str) -> list[dict[str, Any]]:
    scope = mission_scope(root, mission_id)
    if scope.get("ok"):
        return [residual for residual in scope["residuals"] if isinstance(residual, dict)]
    return [
        residual
        for residual in iter_residuals(root, status="open")
        if _extensions(residual).get("x_ccr_mission_id") == mission_id
    ]


def _find_residual(root: Path, *, mission_id: str, residual_id: str) -> dict[str, Any] | None:
    for residual in _mission_residuals(root, mission_id):
        if str(residual.get("residual_id", "")) == residual_id:
            return residual
    return None


def _market_item(residual: dict[str, Any]) -> dict[str, Any]:
    kind = str(residual.get("kind", "other"))
    severity = str(residual.get("severity", "medium"))
    score = SEVERITY_SCORE.get(severity, 50) + (25 if residual.get("blocking") else 0)
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
        "kind": kind,
        "priority": min(score, 100),
        "recommended_role": ROLE_BY_KIND.get(kind, "integrator"),
        "repair_hint": str(residual.get("repair_hint", "")),
        "residual_id": str(residual.get("residual_id", "")),
        "severity": severity,
    }


def _task_for_residual(
    residual: dict[str, Any], *, mission_id: str, item: dict[str, Any]
) -> dict[str, Any]:
    residual_id = str(residual.get("residual_id", "residual:unknown"))
    task_id = stable_id("task:residual-bounty", mission_id, residual_id)
    role = str(item["recommended_role"])
    return {
        "blackboard_refs": [],
        "constraints": {
            "authority_policy": "read_only",
            "forbidden_actions": ["provider_execute", "external_side_effect", "network_dispatch"],
            "max_runtime_minutes": 60,
            "network_policy": "none",
            "side_effect_policy": "dry_run_only",
        },
        "created_at": now_iso(),
        "expected_outputs": [
            {
                "acceptance_criteria": [
                    "Preserve residuals that remain unresolved.",
                    "Do not claim settlement or external execution.",
                ],
                "destination": "reports/residual-market",
                "kind": "json",
                "schema_ref": "ccr.residual_bounty.v1",
            }
        ],
        "extensions": {"x_ccr_mission_id": mission_id, "x_ccr_residual_bounty": True},
        "inputs": [{"kind": "residual", "ref": residual_id, "required": True}],
        "lease": {"lease_required": True, "renewal_allowed": True, "ttl_minutes": 60},
        "objective": str(item.get("repair_hint") or item.get("description") or "Repair residual."),
        "pic_interop": {
            "candidate_only_until_checked": True,
            "enabled": True,
            "input_mapping": "none",
            "output_mapping": "pic_residuals_to_residual_ledger",
            "pic_profile": "development",
            "recommended_pic_commands": [],
        },
        "priority": int(item["priority"]),
        "residual_policy": {
            "blocking_residuals_prevent_settlement": True,
            "preserve_residuals": True,
            "residual_destination": "residuals/open",
        },
        "role": role,
        "schema_version": "ccr.task.v0.1",
        "status": "open",
        "task_id": task_id,
        "title": f"Repair residual {residual_id}",
        "verifier_plan": {
            "failure_route": "residual",
            "promotion_gate": "schema_only",
            "required_verifiers": ["ccr-schema"],
        },
    }


def _read_report(path: Path, *, source: str) -> dict[str, Any]:
    read = read_json_bounded(path, source=source)
    if not read.get("ok"):
        return {"data": {}, "residuals": [read["residual_ready"]]}
    return {"data": read["data"], "residuals": []}


def _residual_ids(value: Any) -> set[str]:
    ids: set[str] = set()
    if isinstance(value, dict):
        for key in ("market", "residuals", "residual_ready"):
            item = value.get(key)
            if isinstance(item, list):
                ids.update(_residual_ids(item))
        residual_id = value.get("residual_id")
        if isinstance(residual_id, str) and residual_id:
            ids.add(residual_id)
    elif isinstance(value, list):
        for item in value:
            ids.update(_residual_ids(item))
    return ids


def _extensions(value: dict[str, Any]) -> dict[str, Any]:
    extensions = value.get("extensions")
    return extensions if isinstance(extensions, dict) else {}


def _blocker_kinds(residuals: list[dict[str, Any]]) -> list[str]:
    kinds: list[str] = []
    for residual in residuals:
        if residual.get("blocking"):
            extensions = residual.get("extensions")
            if isinstance(extensions, dict) and extensions.get("finding_kind"):
                kinds.append(str(extensions["finding_kind"]))
            else:
                kinds.append(str(residual.get("kind", "validation_error")))
    return sorted(set(kinds))
