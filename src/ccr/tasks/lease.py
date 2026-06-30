# SPDX-License-Identifier: Apache-2.0
"""Task lease operations."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from ccr.io import read_json, write_json_atomic
from ccr.residuals.model import build_residual
from ccr.tasks.model import task_path
from ccr.time import is_expired, now_iso, parse_ttl_minutes


@contextmanager
def lease_lock(root: Path) -> Iterator[None]:
    """Acquire a small cross-platform advisory lock using exclusive file creation."""

    lock_path = root / "tasks" / ".lease.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        yield
    finally:
        if fd is not None:
            os.close(fd)
        with suppress(FileNotFoundError):
            os.unlink(lock_path)


def lease_task(root: Path, task_id_value: str, *, ttl: str, agent: str) -> dict[str, Any]:
    """Lease an open task or reclaim an expired lease."""

    ttl_minutes = parse_ttl_minutes(ttl)
    with lease_lock(root):
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
            task["lease"].update(
                {
                    "lease_required": bool(task["lease"].get("lease_required", True)),
                    "leased_at": now_iso(),
                    "leased_by": agent,
                    "ttl_minutes": ttl_minutes,
                }
            )
            write_json_atomic(leased_path, task, overwrite=True)
            open_path.unlink()
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
            task["lease"].update(
                {"leased_at": now_iso(), "leased_by": agent, "ttl_minutes": ttl_minutes}
            )
            write_json_atomic(leased_path, task, overwrite=True)
            return {
                "ok": True,
                "reclaimed": expired,
                "status_after": "leased",
                "status_before": "leased",
                "task": task,
            }
    raise FileNotFoundError(task_id_value)


def release_task(root: Path, task_id_value: str, *, reason: str) -> dict[str, Any]:
    """Release a leased task to open or blocked according to the reason."""

    with lease_lock(root):
        leased_path = task_path(root, task_id_value, "leased")
        if not leased_path.exists():
            raise FileNotFoundError(task_id_value)
        task = read_json(leased_path)
        if not isinstance(task, dict):
            raise ValueError(f"task {task_id_value} is not a JSON object")
        status_after = "blocked" if "block" in reason.lower() else "open"
        task["status"] = status_after
        task["updated_at"] = now_iso()
        task["lease"] = dict(task.get("lease", {}))
        task["lease"]["leased_by"] = None
        task["lease"]["leased_at"] = None
        destination = task_path(root, task_id_value, status_after)
        write_json_atomic(destination, task, overwrite=True)
        leased_path.unlink()
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
