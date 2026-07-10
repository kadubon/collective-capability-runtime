# SPDX-License-Identifier: Apache-2.0
"""Residual-preserving, staged collective workcells."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.ids import sha256_json, stable_id, validate_identifier
from ccr.io import json_file_name, read_json, write_json_atomic
from ccr.residuals.model import build_residual
from ccr.residuals.store import iter_residuals, save_residual
from ccr.runtime.init import init_runtime
from ccr.safe_io import require_path_within_root
from ccr.tasks.factory import build_task
from ccr.tasks.store import submit_task
from ccr.time import now_iso

WORKCELL_STAGES = (
    "independent_proposal",
    "reveal",
    "critique",
    "revision",
    "verification",
    "integration",
)
WORKCELL_ROLES = (
    "generator",
    "skeptic",
    "formalizer",
    "implementer",
    "verifier",
    "integrator",
    "scheduler",
)
ROLE_STAGE = {
    "generator": "independent_proposal",
    "scheduler": "reveal",
    "skeptic": "critique",
    "formalizer": "revision",
    "implementer": "revision",
    "verifier": "verification",
    "integrator": "integration",
}


def advance_workcell(root: Path, *, workcell: str, target_stage: str) -> dict[str, Any]:
    """Advance exactly one workcell stage and reveal proposals at the reveal gate."""

    validate_identifier(workcell, field="workcell")
    if target_stage not in WORKCELL_STAGES:
        raise ValueError(f"unknown workcell stage: {target_stage}")
    metadata, metadata_path = _load_metadata(root, workcell)
    current = str(metadata.get("current_stage", "independent_proposal"))
    if current not in WORKCELL_STAGES:
        raise ValueError("workcell has an invalid current stage")
    current_index = WORKCELL_STAGES.index(current)
    if (
        current_index + 1 >= len(WORKCELL_STAGES)
        or WORKCELL_STAGES[current_index + 1] != target_stage
    ):
        raise ValueError("workcell can advance only to the next protocol stage")
    stage_root = require_path_within_root(
        root / "workcells" / workcell / "stages" / current,
        root,
        field="workcell stage path",
    )
    submissions = sorted(stage_root.glob("submissions/*.json"))
    if current == "independent_proposal" and not submissions:
        raise ValueError("reveal requires at least one independent proposal")
    reveal_path: Path | None = None
    if target_stage == "reveal":
        reveal_path = require_path_within_root(
            root / "workcells" / workcell / "reveal.json",
            root,
            field="workcell reveal path",
        )
        revealed_submission_ids: list[str] = []
        for submission_path in submissions:
            submission = read_json(submission_path)
            if isinstance(submission, dict) and submission.get("submission_id"):
                revealed_submission_ids.append(str(submission["submission_id"]))
        write_json_atomic(
            reveal_path,
            {
                "revealed_submission_ids": revealed_submission_ids,
                "schema_version": "ccr.workcell_reveal.v1",
                "workcell": workcell,
            },
        )
    history = metadata.get("stage_history")
    if not isinstance(history, list):
        history = [current]
    metadata["current_stage"] = target_stage
    metadata["stage_history"] = [*history, target_stage]
    metadata["updated_at"] = now_iso()
    write_json_atomic(metadata_path, metadata)
    return {
        "from_stage": current,
        "ok": True,
        "reveal_manifest": str(reveal_path) if reveal_path is not None else None,
        "schema_version": "ccr.workcell_transition.v1",
        "to_stage": target_stage,
        "workcell": workcell,
    }


def create_workcell(root: Path, *, template: str, name: str) -> dict[str, Any]:
    validate_identifier(name, field="workcell")
    init_runtime(root)
    directory = require_path_within_root(root / "workcells" / name, root, field="workcell path")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "workcell.json"
    created_tasks: list[str] = []
    existing_tasks: list[str] = []
    for role in WORKCELL_ROLES:
        task = build_task(
            kind=template.replace("-", "_"),
            title=f"{name} {role} work",
            objective=f"{role} contribution for {template} workcell {name}.",
            role=role,
            source=f"workcell:{name}:{role}",
            extensions={
                "x_workcell": name,
                "x_workcell_stage": ROLE_STAGE[role],
                "x_workcell_template": template,
            },
        )
        with suppress(FileExistsError):
            submit_task(root, task)
            created_tasks.append(str(task["task_id"]))
            continue
        existing_tasks.append(str(task["task_id"]))
    if not path.exists():
        write_json_atomic(
            path,
            {
                "created_at": now_iso(),
                "current_stage": "independent_proposal",
                "name": name,
                "roles": list(WORKCELL_ROLES),
                "schema_version": "ccr.workcell.v2",
                "stage_history": ["independent_proposal"],
                "stages": list(WORKCELL_STAGES),
                "template": template,
            },
            overwrite=False,
        )
    append_event(
        root,
        make_event(
            action="workcell.create",
            object_type="task",
            object_id=name,
            status_after="open",
            refs=[str(path)],
        ),
    )
    return {
        "created_tasks": sorted(created_tasks),
        "existing_tasks": sorted(existing_tasks),
        "name": name,
        "ok": True,
        "path": str(path),
        "schema_version": "ccr.workcell_create.v2",
        "stage": "independent_proposal",
        "template": template,
    }


def submit_workcell(root: Path, *, workcell: str, file: Path) -> dict[str, Any]:
    validate_identifier(workcell, field="workcell")
    metadata, metadata_path = _load_metadata(root, workcell)
    data = read_json(file)
    if not isinstance(data, dict):
        raise ValueError("workcell output must be a JSON object")
    stage = str(metadata.get("current_stage", "independent_proposal"))
    if stage not in WORKCELL_STAGES:
        raise ValueError("workcell has an invalid current stage")
    raw_provenance = data.get("provenance")
    provenance: dict[str, Any] = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
    correlation_group = sha256_json(
        {
            "model": provenance.get("model"),
            "source": provenance.get("source"),
            "tool": provenance.get("tool"),
        }
    )
    submission_id = stable_id("workcell-submission", workcell, stage, data)
    destination = require_path_within_root(
        root
        / "workcells"
        / workcell
        / "stages"
        / stage
        / "submissions"
        / json_file_name(submission_id),
        root,
        field="workcell submission path",
    )
    envelope = {
        "correlation_group": correlation_group,
        "payload": data,
        "provenance": provenance,
        "schema_version": "ccr.workcell_submission.v2",
        "stage": stage,
        "submission_id": submission_id,
        "visibility": "hidden_until_reveal" if stage == "independent_proposal" else "stage",
        "workcell": workcell,
    }
    write_json_atomic(destination, envelope, overwrite=True)
    residual_ids = _materialize_submission_residuals(root, workcell, data, destination)
    metadata["updated_at"] = now_iso()
    write_json_atomic(metadata_path, metadata)
    append_event(
        root,
        make_event(
            action="workcell.submit",
            object_type="task",
            object_id=workcell,
            status_after="submitted",
            refs=[str(destination)],
            residuals=residual_ids,
        ),
    )
    return {
        "ok": True,
        "path": str(destination),
        "residuals": residual_ids,
        "stage": stage,
        "submission_id": submission_id,
        "visibility": envelope["visibility"],
        "workcell": workcell,
    }


def integrate_workcell(root: Path, *, workcell: str, strategy: str) -> dict[str, Any]:
    validate_identifier(workcell, field="workcell")
    if strategy != "residual-preserving":
        raise ValueError("only residual-preserving strategy is supported")
    metadata, metadata_path = _load_metadata(root, workcell)
    current_stage = str(metadata.get("current_stage", "independent_proposal"))
    stages_root = require_path_within_root(
        root / "workcells" / workcell / "stages", root, field="workcell stages path"
    )
    paths = [
        require_path_within_root(path, root, field="workcell submission path")
        for path in sorted(stages_root.glob("*/submissions/*.json"))
    ]
    submissions = [read_json(path) for path in paths]
    envelopes = [item for item in submissions if isinstance(item, dict)]
    claims = _integrate_claims(envelopes)
    conflict_residuals: list[str] = []
    if current_stage not in {"verification", "integration"}:
        residual = build_residual(
            kind="settlement_blocker",
            description=(
                "Workcell integration was requested before critique, revision, and verification "
                "completed."
            ),
            blocking=True,
            object_type="task",
            object_id=workcell,
            refs=[workcell],
            source="ccr.workcell.integration",
        )
        save_residual(root, residual)
        conflict_residuals.append(str(residual["residual_id"]))
    for claim in claims:
        if claim["contradictions"]:
            residual = build_residual(
                kind="unverified_claim",
                description=f"Unresolved workcell contradiction for claim {claim['claim_id']}.",
                blocking=True,
                object_type="task",
                object_id=workcell,
                refs=[str(item) for item in claim["contradictions"]],
                source="ccr.workcell.integration",
            )
            save_residual(root, residual)
            conflict_residuals.append(str(residual["residual_id"]))
    open_residuals = [
        item for item in iter_residuals(root, status="open") if item.get("object_id") == workcell
    ]
    metadata["current_stage"] = "integration"
    history = metadata.get("stage_history")
    metadata["stage_history"] = [*(history if isinstance(history, list) else []), "integration"]
    metadata["updated_at"] = now_iso()
    write_json_atomic(metadata_path, metadata)
    report = {
        "claims": claims,
        "correlated_support_discounted": True,
        "integrated_submissions": [str(path) for path in paths],
        "minority_reports": [claim for claim in claims if claim["effective_support_count"] <= 1],
        "ok": True,
        "open_residuals_preserved": sorted(
            {str(item["residual_id"]) for item in open_residuals} | set(conflict_residuals)
        ),
        "protocol_complete": current_stage in {"verification", "integration"},
        "schema_version": "ccr.workcell_integrate.v2",
        "settled": False,
        "stage": "integration",
        "strategy": strategy,
        "workcell": workcell,
    }
    integration_path = require_path_within_root(
        root / "workcells" / workcell / "integration.json",
        root,
        field="workcell integration path",
    )
    write_json_atomic(integration_path, report)
    return report


def _integrate_claims(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        raw_payload = envelope.get("payload")
        payload: dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}
        for claim in _claims(payload):
            text = str(claim.get("claim_text") or claim.get("text") or "").strip()
            if not text:
                continue
            key = " ".join(text.casefold().split())
            integrated = grouped.setdefault(
                key,
                {
                    "claim_id": stable_id("workcell-claim", key),
                    "claim_text": text,
                    "contradictions": [],
                    "dependencies": [],
                    "evidence": [],
                    "support_correlation_groups": set(),
                    "support_submission_ids": [],
                },
            )
            integrated["support_correlation_groups"].add(envelope.get("correlation_group"))
            integrated["support_submission_ids"].append(envelope.get("submission_id"))
            integrated["evidence"].extend(_list(claim.get("evidence")))
            integrated["dependencies"].extend(_list(claim.get("dependencies")))
            integrated["contradictions"].extend(_list(claim.get("contradictions")))
    results: list[dict[str, Any]] = []
    for value in grouped.values():
        correlation_groups = sorted(str(item) for item in value.pop("support_correlation_groups"))
        value["effective_support_count"] = len(correlation_groups)
        value["support_correlation_groups"] = correlation_groups
        for key in ("contradictions", "dependencies", "evidence", "support_submission_ids"):
            value[key] = sorted({str(item) for item in value[key] if item})
        results.append(value)
    return sorted(results, key=lambda item: str(item["claim_id"]))


def _claims(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("claims")
    if isinstance(raw, list):
        return [item if isinstance(item, dict) else {"claim_text": str(item)} for item in raw]
    text = payload.get("claim_text") or payload.get("summary")
    return [{"claim_text": str(text), "evidence": payload.get("evidence", [])}] if text else []


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _load_metadata(root: Path, workcell: str) -> tuple[dict[str, Any], Path]:
    path = require_path_within_root(
        root / "workcells" / workcell / "workcell.json", root, field="workcell path"
    )
    if not path.exists():
        raise FileNotFoundError(workcell)
    metadata = read_json(path)
    if not isinstance(metadata, dict):
        raise ValueError("workcell metadata must be a JSON object")
    return metadata, path


def _materialize_submission_residuals(
    root: Path, workcell: str, data: dict[str, Any], destination: Path
) -> list[str]:
    residual_ids: list[str] = []
    for raw in data.get("residuals", []):
        if not isinstance(raw, dict):
            continue
        residual = build_residual(
            kind=str(raw.get("kind", "other")),
            description=str(raw.get("description", "workcell residual")),
            blocking=raw.get("blocking") is True,
            object_type="task",
            object_id=workcell,
            refs=[str(destination)],
            source="ccr.workcell",
            extensions={"raw": raw},
        )
        save_residual(root, residual)
        residual_ids.append(str(residual["residual_id"]))
    return residual_ids
