# SPDX-License-Identifier: Apache-2.0
"""Task lease operations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.io import read_json, write_json_atomic
from ccr.residuals.model import build_residual
from ccr.storage.sqlite import immediate_transaction
from ccr.tasks.model import task_path
from ccr.time import is_expired, now_iso, parse_ttl_minutes


def lease_task(root: Path, task_id_value: str, *, ttl: str, agent: str) -> dict[str, Any]:
    """Lease an open task or reclaim an expired lease."""

    ttl_minutes = parse_ttl_minutes(ttl)
    with immediate_transaction(root) as connection:
        open_path = task_path(root, task_id_value, "open")
        leased_path = task_path(root, task_id_value, "leased")
        if open_path.exists():
            task = read_json(open_path)
            if not isinstance(task, dict):
                raise ValueError(f"task {task_id_value} is not a JSON object")
            status_before = str(task.get("status", "open"))
            task["status"] = "leased"
            task["updated_at"] = now_iso()
            task["lease"] = dict(task.get("lease", {}))
            lease_required = task["lease"].get("lease_required", True)
            if not isinstance(lease_required, bool):
                raise ValueError("task lease_required must be a JSON boolean")
            fencing_token = _next_fencing_token(connection, task_id_value)
            leased_at = now_iso()
            task["lease"].update(
                {
                    "lease_required": lease_required,
                    "leased_at": leased_at,
                    "leased_by": agent,
                    "fencing_token": fencing_token,
                    "heartbeat_at": leased_at,
                    "ttl_minutes": ttl_minutes,
                }
            )
            write_json_atomic(leased_path, task, overwrite=True)
            open_path.unlink()
            _record_lease(connection, task_id_value, task["lease"], status="leased")
            _record_outbox(connection, "task.leased", task_id_value, task)
            return {
                "ok": True,
                "reclaimed": False,
                "status_after": "leased",
                "status_before": status_before,
                "task": task,
            }
        if leased_path.exists():
            task = read_json(leased_path)
            if not isinstance(task, dict):
                raise ValueError(f"task {task_id_value} is not a JSON object")
            lease = task.get("lease", {})
            if not isinstance(lease, dict):
                lease = {}
            expired = is_expired(
                str(lease.get("leased_at") or ""),
                int(lease.get("ttl_minutes") or ttl_minutes),
            )
            if not expired and lease.get("leased_by") != agent:
                return {
                    "ok": False,
                    "error": "task lease is active",
                    "leased_by": lease.get("leased_by"),
                    "status_after": "leased",
                    "status_before": "leased",
                    "task": task,
                }
            task["status"] = "leased"
            task["updated_at"] = now_iso()
            task["lease"] = dict(lease)
            fencing_token = _next_fencing_token(connection, task_id_value)
            leased_at = now_iso()
            task["lease"].update(
                {
                    "fencing_token": fencing_token,
                    "heartbeat_at": leased_at,
                    "leased_at": leased_at,
                    "leased_by": agent,
                    "ttl_minutes": ttl_minutes,
                }
            )
            write_json_atomic(leased_path, task, overwrite=True)
            _record_lease(connection, task_id_value, task["lease"], status="leased")
            _record_outbox(connection, "task.reclaimed", task_id_value, task)
            return {
                "ok": True,
                "reclaimed": expired,
                "status_after": "leased",
                "status_before": "leased",
                "task": task,
            }
    raise FileNotFoundError(task_id_value)


def release_task(
    root: Path,
    task_id_value: str,
    *,
    reason: str,
    agent: str | None = None,
    fencing_token: int | None = None,
) -> dict[str, Any]:
    """Release a leased task to open or blocked according to the reason."""

    with immediate_transaction(root) as connection:
        leased_path = task_path(root, task_id_value, "leased")
        if not leased_path.exists():
            raise FileNotFoundError(task_id_value)
        task = read_json(leased_path)
        if not isinstance(task, dict):
            raise ValueError(f"task {task_id_value} is not a JSON object")
        raw_lease = task.get("lease")
        lease: dict[str, Any] = dict(raw_lease) if isinstance(raw_lease, dict) else {}
        expired = is_expired(str(lease.get("leased_at") or ""), int(lease.get("ttl_minutes") or 1))
        if not expired and (
            lease.get("leased_by") != agent
            or int(lease.get("fencing_token", 0) or 0) != fencing_token
        ):
            raise ValueError("active task release requires its owner and current fencing token")
        status_after = "blocked" if "block" in reason.lower() else "open"
        task["status"] = status_after
        task["updated_at"] = now_iso()
        task["lease"] = dict(task.get("lease", {}))
        task["lease"]["leased_by"] = None
        task["lease"]["leased_at"] = None
        destination = task_path(root, task_id_value, status_after)
        write_json_atomic(destination, task, overwrite=True)
        leased_path.unlink()
        _record_lease(connection, task_id_value, task["lease"], status=status_after)
        _record_outbox(connection, "task.released", task_id_value, task)
    residual = None
    if status_after == "blocked":
        residual = build_residual(
            kind="settlement_blocker",
            description=f"Task released as blocked: {reason}",
            blocking=True,
            object_type="task",
            object_id=task_id_value,
            refs=[task_id_value],
            source="ccr.task.release",
            repair_hint="Review the blocking reason and create a repair task or verifier action.",
        )
    return {
        "ok": True,
        "residual": residual,
        "status_after": status_after,
        "status_before": "leased",
        "task": task,
    }


def _next_fencing_token(connection: sqlite3.Connection, task_id_value: str) -> int:
    row = connection.execute(
        "SELECT fencing_token FROM leases WHERE task_id = ?", (task_id_value,)
    ).fetchone()
    return int(row[0]) + 1 if row is not None else 1


def _record_lease(
    connection: sqlite3.Connection,
    task_id_value: str,
    lease: dict[str, Any],
    *,
    status: str,
) -> None:
    connection.execute(
        """
        INSERT INTO leases(
          task_id, leased_by, leased_at, ttl_minutes, fencing_token,
          heartbeat_at, idempotency_key, status, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
          leased_by = excluded.leased_by,
          leased_at = excluded.leased_at,
          ttl_minutes = excluded.ttl_minutes,
          fencing_token = excluded.fencing_token,
          heartbeat_at = excluded.heartbeat_at,
          idempotency_key = excluded.idempotency_key,
          status = excluded.status,
          updated_at = excluded.updated_at
        """,
        (
            task_id_value,
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


def _record_outbox(
    connection: sqlite3.Connection,
    event_type: str,
    task_id_value: str,
    task: dict[str, Any],
) -> None:
    event_id = stable_id("outbox", event_type, task_id_value, task.get("updated_at"))
    connection.execute(
        """
        INSERT OR IGNORE INTO outbox(
          event_id, event_type, aggregate_type, aggregate_id, payload, created_at
        ) VALUES (?, ?, 'task', ?, ?, ?)
        """,
        (event_id, event_type, task_id_value, json.dumps(task, sort_keys=True), now_iso()),
    )
