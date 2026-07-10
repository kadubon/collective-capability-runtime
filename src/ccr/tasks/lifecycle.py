# SPDX-License-Identifier: Apache-2.0
"""Fenced task lifecycle transitions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ccr.ids import stable_id, validate_identifier
from ccr.io import write_json_atomic
from ccr.residuals.model import build_residual
from ccr.storage.sqlite import immediate_transaction
from ccr.tasks.model import task_path
from ccr.tasks.store import load_task
from ccr.time import now_iso, parse_ttl_minutes


def heartbeat_task(
    root: Path,
    task_id: str,
    *,
    agent: str,
    fencing_token: int,
    ttl: str | None = None,
) -> dict[str, Any]:
    """Renew a lease only for its current fenced owner."""

    validate_identifier(task_id, field="task_id")
    with immediate_transaction(root) as connection:
        task, path, status = load_task(root, task_id)
        _require_lease(task, status=status, agent=agent, fencing_token=fencing_token)
        lease = _lease(task)
        if lease.get("renewal_allowed") is not True:
            raise ValueError("task lease does not permit renewal")
        timestamp = now_iso()
        lease["heartbeat_at"] = timestamp
        lease["leased_at"] = timestamp
        if ttl is not None:
            lease["ttl_minutes"] = parse_ttl_minutes(ttl)
        task["updated_at"] = timestamp
        write_json_atomic(path, task)
        _upsert_lease(connection, task, status="leased")
        _outbox(connection, "task.heartbeat", task_id, task)
    return {"ok": True, "status_after": "leased", "task": task}


def complete_task(
    root: Path,
    task_id: str,
    *,
    agent: str,
    fencing_token: int,
    output_refs: list[str],
    summary: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Submit completed work exactly once per idempotency key."""

    validate_identifier(task_id, field="task_id")
    validate_identifier(idempotency_key, field="idempotency_key")
    with immediate_transaction(root) as connection:
        task, old_path, status = load_task(root, task_id)
        raw_completion = task.get("completion")
        completion: dict[str, Any] = (
            dict(raw_completion) if isinstance(raw_completion, dict) else {}
        )
        if status == "submitted" and completion.get("idempotency_key") == idempotency_key:
            return {"idempotent": True, "ok": True, "status_after": status, "task": task}
        _require_lease(task, status=status, agent=agent, fencing_token=fencing_token)
        timestamp = now_iso()
        task["completion"] = {
            **completion,
            "idempotency_key": idempotency_key,
            "output_refs": sorted(set(output_refs)),
            "submitted_at": timestamp,
            "submitted_by": agent,
            "summary": summary,
        }
        task["status"] = "submitted"
        task["updated_at"] = timestamp
        destination = task_path(root, task_id, "submitted")
        write_json_atomic(destination, task)
        if old_path != destination and old_path.exists():
            old_path.unlink()
        lease = _lease(task)
        lease["idempotency_key"] = idempotency_key
        _upsert_lease(connection, task, status="submitted")
        _outbox(connection, "task.complete", task_id, task)
    return {"idempotent": False, "ok": True, "status_after": "submitted", "task": task}


def fail_task(
    root: Path,
    task_id: str,
    *,
    agent: str,
    fencing_token: int,
    reason: str,
) -> dict[str, Any]:
    """Block a leased task and return a residual-ready failure record."""

    task = _transition_from_lease(
        root,
        task_id,
        agent=agent,
        fencing_token=fencing_token,
        status_after="blocked",
        action="task.fail",
        note=reason,
    )
    residual = build_residual(
        kind="settlement_blocker",
        description=f"Task failed and requires repair: {reason}",
        blocking=True,
        object_type="task",
        object_id=task_id,
        refs=[task_id],
        source="ccr.task.fail",
    )
    return {"ok": True, "residual_ready": residual, "status_after": "blocked", "task": task}


def cancel_task(
    root: Path,
    task_id: str,
    *,
    agent: str,
    reason: str,
    fencing_token: int | None = None,
) -> dict[str, Any]:
    """Cancel open work, requiring its fence when currently leased."""

    validate_identifier(task_id, field="task_id")
    with immediate_transaction(root) as connection:
        task, old_path, status = load_task(root, task_id)
        if status == "leased":
            if fencing_token is None:
                raise ValueError("leased task cancellation requires a fencing token")
            _require_lease(task, status=status, agent=agent, fencing_token=fencing_token)
        elif status != "open":
            raise ValueError(f"cannot cancel task in status {status}")
        task["status"] = "rejected"
        task["updated_at"] = now_iso()
        extensions = _extensions(task)
        extensions["x_lifecycle"] = {"cancelled_by": agent, "reason": reason}
        destination = task_path(root, task_id, "rejected")
        write_json_atomic(destination, task)
        if old_path != destination and old_path.exists():
            old_path.unlink()
        _upsert_lease(connection, task, status="rejected")
        _outbox(connection, "task.cancel", task_id, task)
    return {"ok": True, "status_after": "rejected", "task": task}


def retry_task(root: Path, task_id: str, *, reason: str) -> dict[str, Any]:
    """Return blocked or rejected work to the open queue."""

    validate_identifier(task_id, field="task_id")
    with immediate_transaction(root) as connection:
        task, old_path, status = load_task(root, task_id)
        if status not in {"blocked", "rejected"}:
            raise ValueError(f"cannot retry task in status {status}")
        task["status"] = "open"
        task["updated_at"] = now_iso()
        lease = _lease(task)
        lease["leased_at"] = None
        lease["leased_by"] = None
        extensions = _extensions(task)
        lifecycle = extensions.get("x_lifecycle", {})
        if not isinstance(lifecycle, dict):
            lifecycle = {}
        lifecycle["retry_count"] = int(lifecycle.get("retry_count", 0)) + 1
        lifecycle["retry_reason"] = reason
        extensions["x_lifecycle"] = lifecycle
        destination = task_path(root, task_id, "open")
        write_json_atomic(destination, task)
        if old_path != destination and old_path.exists():
            old_path.unlink()
        _upsert_lease(connection, task, status="open")
        _outbox(connection, "task.retry", task_id, task)
    return {"ok": True, "status_after": "open", "task": task}


def _transition_from_lease(
    root: Path,
    task_id: str,
    *,
    agent: str,
    fencing_token: int,
    status_after: str,
    action: str,
    note: str,
) -> dict[str, Any]:
    validate_identifier(task_id, field="task_id")
    with immediate_transaction(root) as connection:
        task, old_path, status = load_task(root, task_id)
        _require_lease(task, status=status, agent=agent, fencing_token=fencing_token)
        task["status"] = status_after
        task["updated_at"] = now_iso()
        extensions = _extensions(task)
        extensions["x_lifecycle"] = {"actor": agent, "action": action, "note": note}
        destination = task_path(root, task_id, status_after)
        write_json_atomic(destination, task)
        if old_path != destination and old_path.exists():
            old_path.unlink()
        _upsert_lease(connection, task, status=status_after)
        _outbox(connection, action, task_id, task)
    return task


def _require_lease(task: dict[str, Any], *, status: str, agent: str, fencing_token: int) -> None:
    lease = _lease(task)
    if status != "leased":
        raise ValueError(f"task is not leased: {status}")
    if lease.get("leased_by") != agent:
        raise ValueError("task lease owner does not match agent")
    if int(lease.get("fencing_token", 0) or 0) != fencing_token:
        raise ValueError("stale task fencing token")


def _lease(task: dict[str, Any]) -> dict[str, Any]:
    lease = task.get("lease")
    if not isinstance(lease, dict):
        lease = {}
        task["lease"] = lease
    return lease


def _extensions(task: dict[str, Any]) -> dict[str, Any]:
    extensions = task.get("extensions")
    if not isinstance(extensions, dict):
        extensions = {}
        task["extensions"] = extensions
    return extensions


def _upsert_lease(connection: sqlite3.Connection, task: dict[str, Any], *, status: str) -> None:
    lease = _lease(task)
    connection.execute(
        """
        INSERT INTO leases(
          task_id, leased_by, leased_at, ttl_minutes, fencing_token,
          heartbeat_at, idempotency_key, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
          leased_by=excluded.leased_by, leased_at=excluded.leased_at,
          ttl_minutes=excluded.ttl_minutes, fencing_token=excluded.fencing_token,
          heartbeat_at=excluded.heartbeat_at, idempotency_key=excluded.idempotency_key,
          status=excluded.status, updated_at=excluded.updated_at
        """,
        (
            task["task_id"],
            lease.get("leased_by"),
            lease.get("leased_at"),
            lease.get("ttl_minutes"),
            int(lease.get("fencing_token", 0) or 0),
            lease.get("heartbeat_at"),
            lease.get("idempotency_key"),
            status,
            now_iso(),
        ),
    )


def _outbox(
    connection: sqlite3.Connection, event_type: str, task_id: str, task: dict[str, Any]
) -> None:
    event_id = stable_id("outbox", event_type, task_id, task.get("updated_at"))
    connection.execute(
        """
        INSERT OR IGNORE INTO outbox(
          event_id, event_type, aggregate_type, aggregate_id, payload, created_at
        ) VALUES (?, ?, 'task', ?, ?, ?)
        """,
        (event_id, event_type, task_id, json.dumps(task, sort_keys=True), now_iso()),
    )
