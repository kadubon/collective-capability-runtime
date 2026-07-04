# SPDX-License-Identifier: Apache-2.0
"""Residual work market surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.mission.model import MISSION_NON_CLAIMS, mission_scope
from ccr.residuals.store import iter_residuals
from ccr.safe_io import read_text_bounded, residual_ready
from ccr.tasks.store import submit_task, validate_task
from ccr.time import now_iso

SEVERITY_SCORE = {"critical": 100, "high": 80, "medium": 50, "low": 20, "info": 5}
KIND_PRIORITY = {
    "settlement_blocker": 95,
    "authority_gap": 90,
    "hazard": 85,
    "validation_error": 80,
    "missing_evidence": 75,
    "identity_gap": 70,
    "provider_missing": 65,
    "dependency_gap": 60,
    "stale_source": 55,
    "unverified_claim": 50,
    "scope_gap": 45,
    "queue_overload": 40,
    "negative_liquidity": 35,
    "candidate_only_reason": 30,
    "safe_command_hint": 25,
    "other": 10,
}
ROLE_BY_KIND = {
    "authority_gap": ["security_reviewer", "verifier"],
    "candidate_only_reason": ["verifier", "integrator"],
    "dependency_gap": ["integrator", "maintainer"],
    "hazard": ["safety_reviewer", "security_reviewer"],
    "identity_gap": ["verifier", "security_reviewer"],
    "missing_evidence": ["librarian", "verifier"],
    "negative_liquidity": ["optimizer", "scheduler"],
    "provider_missing": ["pic_adapter", "integrator"],
    "queue_overload": ["scheduler", "integrator"],
    "safe_command_hint": ["implementer", "reviewer"],
    "scope_gap": ["mission_scoper", "verifier"],
    "settlement_blocker": ["verifier", "skeptic"],
    "stale_source": ["librarian", "verifier"],
    "unverified_claim": ["skeptic", "verifier"],
    "validation_error": ["verifier", "implementer"],
}
DEFAULT_ROLES = ["integrator", "verifier"]


def residual_market(root: Path, *, mission_id: str | None = None) -> dict[str, Any]:
    """Rank residual work without changing runtime state.

    When ``mission_id`` is omitted the market is runtime-wide over open residuals. Mission-scoped
    output remains backward compatible by preserving the ``mission_id`` field.
    """

    residuals = _residuals_for_scope(root, mission_id=mission_id)
    object_counts = _object_counts(residuals)
    ranked = sorted(
        (_market_item(residual, object_counts=object_counts) for residual in residuals),
        key=_market_sort_key,
    )
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return {
        "blockers": [],
        "external_execution": False,
        "market": ranked,
        "mission_id": mission_id or "",
        "mutated_runtime": False,
        "network_call_performed": False,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": True,
        "residual_count": len(ranked),
        "scope": "mission" if mission_id else "runtime",
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
    item = _market_item(residual, object_counts=_object_counts([residual]))
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
    before_records = _residual_records(before_report["data"])
    after_records = _residual_records(after_report["data"])
    before_ids = set(before_records)
    after_ids = set(after_records)
    opened = sorted(after_ids - before_ids)
    resolved = sorted(before_ids - after_ids)
    unchanged = sorted(before_ids & after_ids)
    newly_blocking = sorted(
        residual_id
        for residual_id in after_ids
        if _is_blocking(after_records[residual_id])
        and not _is_blocking(before_records.get(residual_id, {}))
    )
    no_longer_blocking = sorted(
        residual_id
        for residual_id in before_ids
        if _is_blocking(before_records[residual_id])
        and not _is_blocking(after_records.get(residual_id, {}))
    )
    blockers = _blocker_kinds(residuals)
    by_kind_before = _kind_counts(before_records.values())
    by_kind_after = _kind_counts(after_records.values())
    return {
        "added_residual_ids": opened,
        "blockers": blockers,
        "by_kind_delta": _counter_delta(by_kind_before, by_kind_after),
        "external_execution": False,
        "mutated_runtime": False,
        "network_call_performed": False,
        "newly_blocking": newly_blocking,
        "no_longer_blocking": no_longer_blocking,
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": not blockers,
        "opened": opened,
        "removed_residual_ids": resolved,
        "resolved": resolved,
        "residual_debt_delta": _residual_debt(after_records.values())
        - _residual_debt(before_records.values()),
        "residual_ready": residuals,
        "schema_version": "ccr.residual_diff.v1",
        "severity_delta": _severity_delta(before_records, after_records),
        "settled": False,
        "unchanged": unchanged,
        "unchanged_residual_ids": unchanged,
    }


def _residuals_for_scope(root: Path, *, mission_id: str | None) -> list[dict[str, Any]]:
    if mission_id:
        return _mission_residuals(root, mission_id)
    return sorted(
        [
            residual
            for residual in iter_residuals(root, status="open")
            if isinstance(residual, dict)
        ],
        key=lambda item: str(item.get("residual_id", "")),
    )


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


def _market_item(
    residual: dict[str, Any], *, object_counts: dict[tuple[str, str], int]
) -> dict[str, Any]:
    kind = str(residual.get("kind", "other"))
    severity = str(residual.get("severity", "medium"))
    object_key = (str(residual.get("object_type", "")), str(residual.get("object_id", "")))
    object_centrality = object_counts.get(object_key, 1)
    repairability = _repairability(residual)
    kind_priority = KIND_PRIORITY.get(kind, KIND_PRIORITY["other"])
    score = (
        (100 if residual.get("blocking") else 0)
        + SEVERITY_SCORE.get(severity, 50)
        + kind_priority
        + min(object_centrality * 5, 25)
        + repairability
    )
    roles = ROLE_BY_KIND.get(kind, DEFAULT_ROLES)
    return {
        "blocking": bool(residual.get("blocking", False)),
        "description": str(residual.get("description", "")),
        "kind": kind,
        "object_centrality": object_centrality,
        "priority": min(score, 100),
        "rank_components": {
            "blocking": 1 if residual.get("blocking") else 0,
            "kind_priority": kind_priority,
            "object_centrality": object_centrality,
            "repairability": repairability,
            "severity": SEVERITY_SCORE.get(severity, 50),
        },
        "recommended_role": roles[0],
        "recommended_roles": roles,
        "repairability": repairability,
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
    read = read_text_bounded(path, source=source)
    if not read.get("ok"):
        return {"data": {}, "residuals": [read["residual_ready"]]}
    text = str(read["text"])
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as exc:
            return {
                "data": {},
                "residuals": [
                    residual_ready(
                        "malformed_json",
                        str(read.get("display", path.name)),
                        f"Residual diff input is malformed JSON/JSONL at line {exc.lineno}.",
                        source,
                    )
                ],
            }
    return {"data": data, "residuals": []}


def _residual_records(value: Any) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if isinstance(value, dict):
        residual_id = value.get("residual_id")
        if isinstance(residual_id, str) and residual_id:
            records[residual_id] = value
        for key in ("market", "residuals", "residual_ready", "top_residuals"):
            item = value.get(key)
            records.update(_residual_records(item))
    elif isinstance(value, list):
        for item in value:
            records.update(_residual_records(item))
    return records


def _market_sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, str]:
    components = item.get("rank_components")
    if not isinstance(components, dict):
        components = {}
    return (
        -int(components.get("blocking", 0)),
        -int(components.get("severity", 0)),
        -int(components.get("kind_priority", 0)),
        -int(components.get("object_centrality", 0)),
        -int(components.get("repairability", 0)),
        str(item.get("residual_id", "")),
    )


def _repairability(residual: dict[str, Any]) -> int:
    score = 0
    if residual.get("repair_hint"):
        score += 25
    refs = residual.get("refs")
    if isinstance(refs, list) and refs:
        score += 20
    if residual.get("object_id"):
        score += 15
    if residual.get("source"):
        score += 10
    return score


def _object_counts(residuals: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for residual in residuals:
        key = (str(residual.get("object_type", "")), str(residual.get("object_id", "")))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _is_blocking(record: dict[str, Any]) -> bool:
    return bool(record.get("blocking", False))


def _kind(record: dict[str, Any]) -> str:
    return str(record.get("kind", "other"))


def _kind_counts(records: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = _kind(record)
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def _counter_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    keys = sorted(set(before) | set(after))
    return {key: after.get(key, 0) - before.get(key, 0) for key in keys}


def _residual_debt(records: Any) -> int:
    debt = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        severity = str(record.get("severity", "medium"))
        debt += SEVERITY_SCORE.get(severity, 50)
        if record.get("blocking"):
            debt += 25
    return debt


def _severity_delta(
    before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
) -> list[dict[str, str]]:
    deltas: list[dict[str, str]] = []
    for residual_id in sorted(set(before) & set(after)):
        before_severity = str(before[residual_id].get("severity", "medium"))
        after_severity = str(after[residual_id].get("severity", "medium"))
        if before_severity != after_severity:
            deltas.append(
                {
                    "after": after_severity,
                    "before": before_severity,
                    "residual_id": residual_id,
                }
            )
    return deltas


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
