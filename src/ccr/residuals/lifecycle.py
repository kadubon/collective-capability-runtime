# SPDX-License-Identifier: Apache-2.0
"""Residual assignment, review, resolution, and reopening."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ccr.ids import sha256_bytes, validate_identifier
from ccr.io import read_json, write_json_atomic
from ccr.residuals.store import residual_path
from ccr.storage.sqlite import immediate_transaction
from ccr.telemetry import emit_event_span
from ccr.time import now_iso


def assign_residual(root: Path, residual_id: str, *, agent: str) -> dict[str, Any]:
    return _update_open_workflow(
        root, residual_id, state="assigned", actor_key="assignee", actor=agent
    )


def review_residual(root: Path, residual_id: str, *, reviewer: str) -> dict[str, Any]:
    return _update_open_workflow(
        root, residual_id, state="under_review", actor_key="reviewer", actor=reviewer
    )


def resolve_residual(
    root: Path,
    residual_id: str,
    *,
    artifact: Path,
    verifier: Path,
) -> dict[str, Any]:
    """Resolve only with a repair artifact and independent verifier evidence."""

    validate_identifier(residual_id, field="residual_id")
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    verifier_data = read_json(verifier)
    if not isinstance(verifier_data, dict):
        raise ValueError("verifier evidence must be a JSON object")
    if verifier_data.get("accepted") is not True:
        raise ValueError("verifier evidence must explicitly accept the repair")
    verifier_identity = verifier_data.get("verifier_id") or verifier_data.get("provider")
    if not isinstance(verifier_identity, str) or not verifier_identity:
        raise ValueError("verifier evidence requires verifier_id or provider")
    artifact_digest = sha256_bytes(artifact.read_bytes())
    if verifier_data.get("artifact_sha256") != artifact_digest:
        raise ValueError("verifier evidence artifact digest does not match repair artifact")
    with immediate_transaction(root) as connection:
        source = residual_path(root, residual_id, "open")
        if not source.exists():
            raise FileNotFoundError(residual_id)
        residual = read_json(source)
        if not isinstance(residual, dict):
            raise ValueError("residual must be a JSON object")
        workflow = _workflow(residual)
        if workflow.get("assignee") == verifier_identity:
            raise ValueError("residual verifier must be independent from the assignee")
        residual["resolution"] = {
            "artifact": str(artifact),
            "artifact_sha256": artifact_digest,
            "resolved_at": now_iso(),
            "verifier_evidence": str(verifier),
            "verifier_id": verifier_identity,
        }
        workflow["state"] = "resolved"
        residual["status"] = "resolved"
        residual["updated_at"] = now_iso()
        destination = residual_path(root, residual_id, "resolved")
        write_json_atomic(destination, residual)
        source.unlink()
        _index(connection, residual)
    emit_event_span(
        "ccr.residual.resolved",
        {"residual_id": residual_id, "verifier_id": str(verifier_identity)},
    )
    return {"ok": True, "residual": residual, "status_after": "resolved"}


def reopen_residual(root: Path, residual_id: str, *, reason: str) -> dict[str, Any]:
    validate_identifier(residual_id, field="residual_id")
    with immediate_transaction(root) as connection:
        source = residual_path(root, residual_id, "resolved")
        if not source.exists():
            raise FileNotFoundError(residual_id)
        residual = read_json(source)
        if not isinstance(residual, dict):
            raise ValueError("residual must be a JSON object")
        previous = residual.get("resolution")
        workflow = _workflow(residual)
        history = workflow.get("resolution_history")
        if not isinstance(history, list):
            history = []
        if isinstance(previous, dict):
            history.append(previous)
        workflow.update({"reopen_reason": reason, "resolution_history": history, "state": "open"})
        residual["resolution"] = {}
        residual["status"] = "open"
        residual["updated_at"] = now_iso()
        destination = residual_path(root, residual_id, "open")
        write_json_atomic(destination, residual)
        source.unlink()
        _index(connection, residual)
    emit_event_span("ccr.residual.reopened", {"residual_id": residual_id})
    return {"ok": True, "residual": residual, "status_after": "open"}


def _update_open_workflow(
    root: Path,
    residual_id: str,
    *,
    state: str,
    actor_key: str,
    actor: str,
) -> dict[str, Any]:
    validate_identifier(residual_id, field="residual_id")
    with immediate_transaction(root) as connection:
        path = residual_path(root, residual_id, "open")
        if not path.exists():
            raise FileNotFoundError(residual_id)
        residual = read_json(path)
        if not isinstance(residual, dict):
            raise ValueError("residual must be a JSON object")
        workflow = _workflow(residual)
        workflow.update({actor_key: actor, "state": state, "updated_at": now_iso()})
        residual["updated_at"] = now_iso()
        write_json_atomic(path, residual)
        _index(connection, residual)
    emit_event_span(f"ccr.residual.{state}", {"actor": actor, "residual_id": residual_id})
    return {"ok": True, "residual": residual, "workflow_state": state}


def _workflow(residual: dict[str, Any]) -> dict[str, Any]:
    extensions = residual.get("extensions")
    if not isinstance(extensions, dict):
        extensions = {}
        residual["extensions"] = extensions
    workflow = extensions.get("workflow")
    if not isinstance(workflow, dict):
        workflow = {}
        extensions["workflow"] = workflow
    return workflow


def _index(connection: sqlite3.Connection, residual: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO residuals(
          residual_id, status, blocking, kind, object_type, object_id, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(residual_id) DO UPDATE SET
          status=excluded.status, blocking=excluded.blocking, kind=excluded.kind,
          object_type=excluded.object_type, object_id=excluded.object_id,
          updated_at=excluded.updated_at
        """,
        (
            residual["residual_id"],
            residual["status"],
            1 if residual.get("blocking") else 0,
            residual.get("kind"),
            residual.get("object_type"),
            residual.get("object_id"),
            now_iso(),
        ),
    )
