# SPDX-License-Identifier: Apache-2.0
"""Transactional SQLite RuntimeStore profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.storage.sqlite import immediate_transaction, init_database
from ccr.tasks.lease import lease_task
from ccr.tasks.lifecycle import complete_task, heartbeat_task
from ccr.tasks.scheduler import next_task
from ccr.tasks.store import submit_task
from ccr.telemetry import emit_event_span


class SQLiteRuntimeStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def initialize(self) -> dict[str, Any]:
        return init_database(self.root)

    def claim_task(self, *, role: str, worker_id: str, ttl_minutes: int) -> dict[str, Any] | None:
        while True:
            task = next_task(self.root, role=role)
            if task is None:
                return None
            try:
                result = lease_task(
                    self.root,
                    str(task["task_id"]),
                    ttl=f"{ttl_minutes}m",
                    agent=worker_id,
                )
            except FileNotFoundError:
                continue
            if result.get("ok"):
                emit_event_span(
                    "ccr.task.leased",
                    {
                        "role": role,
                        "task_id": str(task["task_id"]),
                        "worker_id": worker_id,
                    },
                )
                return result
            if result.get("error") != "task lease is active":
                return None

    def heartbeat(self, *, task_id: str, worker_id: str, fencing_token: int) -> dict[str, Any]:
        result = heartbeat_task(
            self.root,
            task_id,
            agent=worker_id,
            fencing_token=fencing_token,
        )
        emit_event_span("ccr.task.heartbeat", {"task_id": task_id, "worker_id": worker_id})
        return result

    def complete(
        self,
        *,
        task_id: str,
        worker_id: str,
        fencing_token: int,
        idempotency_key: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        completed = complete_task(
            self.root,
            task_id,
            agent=worker_id,
            fencing_token=fencing_token,
            output_refs=[str(item) for item in result.get("output_refs", [])],
            summary=str(result.get("summary", "completed")),
            idempotency_key=idempotency_key,
        )
        emit_event_span("ccr.task.completed", {"task_id": task_id, "worker_id": worker_id})
        return completed

    def append_task(self, task: dict[str, Any]) -> dict[str, Any]:
        path = submit_task(self.root, task)
        emit_event_span("ccr.task.submitted", {"task_id": str(task["task_id"])})
        return {"ok": True, "path": str(path), "task_id": task["task_id"]}

    def consume_dpop_jti(self, *, jti: str, expires_at: str) -> bool:
        with immediate_transaction(self.root) as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO dpop_replay(jti, expires_at, created_at) "
                "VALUES (?, ?, datetime('now'))",
                (jti, expires_at),
            )
            connection.execute("DELETE FROM dpop_replay WHERE expires_at <= datetime('now')")
            return cursor.rowcount == 1
