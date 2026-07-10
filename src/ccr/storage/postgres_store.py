# SPDX-License-Identifier: Apache-2.0
"""PostgreSQL 16+ authoritative distributed RuntimeStore profile."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json, stable_id, validate_identifier
from ccr.storage.export import export_content_addressed
from ccr.telemetry import emit_event_span


class PostgresRuntimeStore:
    """At-least-once task delivery with fenced, idempotent commits."""

    def __init__(self, dsn: str, *, export_root: Path | None = None) -> None:
        try:
            module = importlib.import_module("psycopg_pool")
            json_module = importlib.import_module("psycopg.types.json")
        except ImportError as exc:
            raise RuntimeError("PostgreSQL profile requires the 'distributed' extra") from exc
        self.pool: Any = module.ConnectionPool(conninfo=dsn, min_size=1, max_size=20)
        self._jsonb: Any = json_module.Jsonb
        self.export_root = export_root

    def initialize(self) -> dict[str, Any]:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ccr_tasks (
                  task_id TEXT PRIMARY KEY,
                  role TEXT NOT NULL,
                  priority INTEGER NOT NULL,
                  status TEXT NOT NULL,
                  payload JSONB NOT NULL,
                  leased_by TEXT,
                  leased_at TIMESTAMPTZ,
                  heartbeat_at TIMESTAMPTZ,
                  lease_expires_at TIMESTAMPTZ,
                  fencing_token BIGINT NOT NULL DEFAULT 0,
                  idempotency_key TEXT,
                  result JSONB,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ccr_dpop_replay (
                  jti TEXT PRIMARY KEY,
                  expires_at TIMESTAMPTZ NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS ccr_outbox (
                  event_id TEXT PRIMARY KEY,
                  event_type TEXT NOT NULL,
                  aggregate_id TEXT NOT NULL,
                  payload JSONB NOT NULL,
                  traceparent TEXT,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
                  published_at TIMESTAMPTZ
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ccr_tasks_claim_idx "
                "ON ccr_tasks(status, role, priority DESC, created_at)"
            )
        return {"backend": "postgresql", "ok": True, "schema_version": 1}

    def append_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = validate_identifier(str(task["task_id"]), field="task_id")
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                INSERT INTO ccr_tasks(task_id, role, priority, status, payload)
                VALUES (%s, %s, %s, 'open', %s)
                ON CONFLICT(task_id) DO NOTHING
                RETURNING task_id
                """,
                (task_id, str(task["role"]), int(task.get("priority", 50)), self._jsonb(task)),
            ).fetchone()
        export = (
            export_content_addressed(
                self.export_root,
                object_type="task",
                object_id=task_id,
                content=task,
            )
            if row is not None and self.export_root is not None
            else None
        )
        if row is not None:
            emit_event_span("ccr.task.submitted", {"task_id": task_id})
        return {"export": export, "inserted": row is not None, "ok": True, "task_id": task_id}

    def claim_task(self, *, role: str, worker_id: str, ttl_minutes: int) -> dict[str, Any] | None:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                SELECT task_id FROM ccr_tasks
                WHERE role = %s
                  AND (
                    status = 'open'
                    OR (status = 'leased' AND lease_expires_at <= clock_timestamp())
                  )
                ORDER BY priority DESC, created_at, task_id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (role,),
            ).fetchone()
            if row is None:
                return None
            claimed = connection.execute(
                """
                UPDATE ccr_tasks
                SET status='leased', leased_by=%s, leased_at=clock_timestamp(),
                    heartbeat_at=clock_timestamp(),
                    lease_expires_at=clock_timestamp() + (%s * interval '1 minute'),
                    fencing_token=fencing_token + 1, updated_at=clock_timestamp()
                WHERE task_id=%s
                RETURNING task_id, payload, fencing_token, lease_expires_at
                """,
                (worker_id, ttl_minutes, row[0]),
            ).fetchone()
            payload = {
                "fencing_token": int(claimed[2]),
                "lease_expires_at": claimed[3].isoformat(),
                "task": claimed[1],
                "task_id": claimed[0],
            }
            self._outbox(connection, "task.leased", str(claimed[0]), payload)
            emit_event_span(
                "ccr.task.leased",
                {"task_id": str(claimed[0]), "worker_id": worker_id},
            )
            return payload

    def heartbeat(self, *, task_id: str, worker_id: str, fencing_token: int) -> dict[str, Any]:
        with self.pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE ccr_tasks
                SET heartbeat_at=clock_timestamp(), updated_at=clock_timestamp()
                WHERE task_id=%s AND status='leased' AND leased_by=%s AND fencing_token=%s
                  AND lease_expires_at > clock_timestamp()
                RETURNING lease_expires_at
                """,
                (task_id, worker_id, fencing_token),
            ).fetchone()
            if row is None:
                raise ValueError("stale or unowned PostgreSQL lease")
            emit_event_span("ccr.task.heartbeat", {"task_id": task_id, "worker_id": worker_id})
            return {"lease_expires_at": row[0].isoformat(), "ok": True, "task_id": task_id}

    def complete(
        self,
        *,
        task_id: str,
        worker_id: str,
        fencing_token: int,
        idempotency_key: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        validate_identifier(idempotency_key, field="idempotency_key")
        with self.pool.connection() as connection, connection.transaction():
            existing = connection.execute(
                "SELECT idempotency_key, result FROM ccr_tasks WHERE task_id=%s FOR UPDATE",
                (task_id,),
            ).fetchone()
            if existing is None:
                raise FileNotFoundError(task_id)
            if existing[0] == idempotency_key:
                return {"idempotent": True, "ok": True, "result": existing[1]}
            row = connection.execute(
                """
                UPDATE ccr_tasks
                SET status='submitted', idempotency_key=%s, result=%s,
                    updated_at=clock_timestamp()
                WHERE task_id=%s AND status='leased' AND leased_by=%s AND fencing_token=%s
                  AND lease_expires_at > clock_timestamp()
                RETURNING task_id
                """,
                (idempotency_key, self._jsonb(result), task_id, worker_id, fencing_token),
            ).fetchone()
            if row is None:
                raise ValueError("stale or unowned PostgreSQL lease")
            self._outbox(connection, "task.completed", task_id, result)
        export = (
            export_content_addressed(
                self.export_root,
                object_type="task-result",
                object_id=task_id,
                content=result,
            )
            if self.export_root is not None
            else None
        )
        emit_event_span("ccr.task.completed", {"task_id": task_id, "worker_id": worker_id})
        return {
            "export": export,
            "idempotent": False,
            "ok": True,
            "result": result,
            "task_id": task_id,
        }

    def consume_dpop_jti(self, *, jti: str, expires_at: str) -> bool:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute("DELETE FROM ccr_dpop_replay WHERE expires_at <= clock_timestamp()")
            row = connection.execute(
                """
                INSERT INTO ccr_dpop_replay(jti, expires_at)
                VALUES (%s, %s::timestamptz)
                ON CONFLICT(jti) DO NOTHING
                RETURNING jti
                """,
                (jti, expires_at),
            ).fetchone()
            return row is not None

    def _outbox(self, connection: Any, event_type: str, aggregate_id: str, payload: Any) -> None:
        event_id = stable_id("event", event_type, aggregate_id, sha256_json(payload))
        connection.execute(
            """
            INSERT INTO ccr_outbox(event_id, event_type, aggregate_id, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (event_id, event_type, aggregate_id, self._jsonb(payload)),
        )
