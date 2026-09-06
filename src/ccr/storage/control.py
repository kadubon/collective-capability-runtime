# SPDX-License-Identifier: Apache-2.0
"""Transactional control aggregates, shared by optimizer and operation approvals.

Reads never initialize storage. PostgreSQL uses database time and a per-aggregate
advisory transaction lock (also covering first insertion); SQLite uses IMMEDIATE.
The immutable outbox snapshot is committed with every state transition.
"""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json, stable_id
from ccr.storage.sqlite import database_path


class ControlStore:
    def __init__(self, root: Path, database_url: str | None = None, *, pool: Any = None) -> None:
        self.root = root
        self.database_url = (
            database_url if database_url is not None else os.getenv("CCR_DATABASE_URL")
        )
        self.pool = pool

    @contextmanager
    def connection(self, *, write: bool = False) -> Iterator[Any]:
        if self.pool is not None:
            with self.pool.connection() as connection, connection.transaction():
                if not write:
                    connection.execute("SET TRANSACTION READ ONLY")
                yield connection
        elif self.database_url:
            pg = importlib.import_module("psycopg")
            with pg.connect(self.database_url) as connection:
                if not write:
                    connection.execute("SET TRANSACTION READ ONLY")
                yield connection
        else:
            path = database_path(self.root)
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(path, timeout=30)
            else:
                connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                yield connection
                if write:
                    connection.commit()
            except BaseException:
                if write:
                    connection.rollback()
                raise
            finally:
                connection.close()

    def sql(self, connection: Any, query: str, values: tuple[Any, ...] = ()) -> Any:
        return connection.execute(query.replace("?", "%s") if self.database_url else query, values)

    def initialize(self) -> None:
        with self.connection(write=True) as connection:
            if self.database_url:
                connection.execute("SELECT pg_advisory_xact_lock(192837465)")
            for statement in (
                "CREATE TABLE IF NOT EXISTS ccr_control (object_key TEXT PRIMARY KEY, "
                "payload TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS ccr_control_outbox (event_id TEXT PRIMARY KEY, "
                "object_key TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL)",
                "CREATE TABLE IF NOT EXISTS ccr_control_migrations (version INTEGER PRIMARY KEY)",
                "INSERT INTO ccr_control_migrations(version) VALUES (1) ON CONFLICT DO NOTHING",
            ):
                connection.execute(statement)

    def exists(self) -> bool:
        if not self.database_url and not database_path(self.root).exists():
            return False
        with self.connection() as connection:
            if self.database_url:
                return (
                    connection.execute("SELECT to_regclass('ccr_control')").fetchone()[0]
                    is not None
                )
            return (
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ccr_control'"
                ).fetchone()
                is not None
            )

    def now(self) -> str:
        with self.connection() as connection:
            if self.database_url:
                value = connection.execute("SELECT clock_timestamp()").fetchone()[0]
                return str(value.replace(microsecond=0).isoformat())
            return str(
                connection.execute("SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')").fetchone()[0]
            )

    def read(self, key: str) -> dict[str, Any] | None:
        if not self.exists():
            return None
        with self.connection() as connection:
            row = self.sql(
                connection, "SELECT payload FROM ccr_control WHERE object_key=?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def list_objects(self, prefix: str) -> list[dict[str, Any]]:
        if not self.exists():
            return []
        with self.connection() as connection:
            rows = self.sql(
                connection, "SELECT object_key,payload FROM ccr_control ORDER BY object_key"
            ).fetchall()
            return [json.loads(row[1]) for row in rows if row[0].startswith(prefix)]

    def export(self, key: str) -> list[dict[str, Any]]:
        """Export committed snapshots; an interrupted export can safely be retried."""
        from ccr.storage.export import export_content_addressed

        with self.connection() as connection:
            rows = self.sql(
                connection,
                "SELECT event_id,payload FROM ccr_control_outbox WHERE object_key=? "
                "ORDER BY created_at,event_id",
                (key,),
            ).fetchall()
        return [
            export_content_addressed(
                self.root, object_type="optimizer", object_id=row[0], content=json.loads(row[1])
            )
            for row in rows
        ]

    @contextmanager
    def edit(self, key: str, *, create: bool = False) -> Iterator[tuple[dict[str, Any], str]]:
        if create:
            self.initialize()
        with self.connection(write=True) as connection:
            if self.database_url:
                self.sql(connection, "SELECT pg_advisory_xact_lock(hashtextextended(?,0))", (key,))
                current = connection.execute(
                    "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC', "
                    '\'YYYY-MM-DD"T"HH24:MI:SS"Z"\')'
                ).fetchone()[0]
            else:
                current = connection.execute(
                    "SELECT strftime('%Y-%m-%dT%H:%M:%SZ','now')"
                ).fetchone()[0]
            row = self.sql(
                connection, "SELECT payload FROM ccr_control WHERE object_key=?", (key,)
            ).fetchone()
            if create and row:
                raise FileExistsError(key)
            if not create and not row:
                raise FileNotFoundError(key)
            data = json.loads(row[0]) if row else {}
            before = sha256_json(data)
            yield data, current
            if sha256_json(data) == before:
                return
            payload = json.dumps(data, sort_keys=True, allow_nan=False)
            self.sql(
                connection,
                "INSERT INTO ccr_control(object_key,payload) VALUES (?,?) "
                "ON CONFLICT(object_key) DO UPDATE SET payload=excluded.payload",
                (key, payload),
            )
            self.sql(
                connection,
                "INSERT INTO ccr_control_outbox(event_id,object_key,payload,created_at) "
                "VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
                (stable_id("event:control", key, data), key, payload, current),
            )


def control_for_store(store: Any, root: Path) -> ControlStore:
    """Use the server's selected backend, never an unrelated worker-local database."""
    return ControlStore(root, getattr(store, "database_url", ""), pool=getattr(store, "pool", None))
