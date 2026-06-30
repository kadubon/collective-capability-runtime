# SPDX-License-Identifier: Apache-2.0
"""SQLite index for JSON runtime artifacts.

SQLite is an index and transaction layer. JSON files remain the inspectable
source artifacts for packets, tasks, residuals, reports, and phase outputs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json
from ccr.io import read_json
from ccr.paths import blackboard_events_path
from ccr.time import now_iso

DB_FILENAME = "ccr.sqlite"
SCHEMA_VERSION = 1


def database_path(root: Path) -> Path:
    """Return the SQLite database path for a runtime root."""

    return root / DB_FILENAME


def connect(root: Path) -> sqlite3.Connection:
    """Open a SQLite connection with conservative local settings."""

    path = database_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_database(root: Path) -> dict[str, Any]:
    """Create or migrate the SQLite index."""

    with connect(root) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS objects (
              object_type TEXT NOT NULL,
              object_id TEXT NOT NULL,
              status TEXT,
              path TEXT NOT NULL,
              content_sha256 TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (object_type, object_id)
            );

            CREATE TABLE IF NOT EXISTS events (
              event_id TEXT PRIMARY KEY,
              timestamp TEXT NOT NULL,
              actor TEXT NOT NULL,
              action TEXT NOT NULL,
              object_type TEXT NOT NULL,
              object_id TEXT NOT NULL,
              status_before TEXT,
              status_after TEXT,
              dry_run INTEGER NOT NULL,
              note TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS leases (
              task_id TEXT PRIMARY KEY,
              leased_by TEXT,
              leased_at TEXT,
              ttl_minutes INTEGER,
              status TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS provider_runs (
              run_id TEXT PRIMARY KEY,
              provider TEXT NOT NULL,
              action TEXT NOT NULL,
              status TEXT NOT NULL,
              dry_run INTEGER NOT NULL,
              report_path TEXT,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phase_observations (
              observation_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              path TEXT NOT NULL,
              accepted_packet_count INTEGER NOT NULL,
              effective_edge_count INTEGER NOT NULL,
              threshold_distance REAL NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        applied = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?", (SCHEMA_VERSION,)
        ).fetchone()
        migrated = applied is None
        if migrated:
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, now_iso()),
            )
        connection.commit()
    return {
        "database": str(database_path(root)),
        "migrated": migrated,
        "schema_version": SCHEMA_VERSION,
    }


def record_object(
    root: Path,
    *,
    object_type: str,
    object_id: str,
    status: str | None,
    path: Path,
    content: dict[str, Any],
) -> None:
    """Upsert one object index row."""

    init_database(root)
    with connect(root) as connection:
        connection.execute(
            """
            INSERT INTO objects(object_type, object_id, status, path, content_sha256, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(object_type, object_id) DO UPDATE SET
              status = excluded.status,
              path = excluded.path,
              content_sha256 = excluded.content_sha256,
              updated_at = excluded.updated_at
            """,
            (object_type, object_id, status, str(path), sha256_json(content), now_iso()),
        )
        connection.commit()


def record_event(root: Path, event: dict[str, Any]) -> None:
    """Insert or replace one blackboard event row."""

    init_database(root)
    with connect(root) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO events(
              event_id, timestamp, actor, action, object_type, object_id,
              status_before, status_after, dry_run, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("event_id"),
                event.get("timestamp", ""),
                event.get("actor", ""),
                event.get("action", ""),
                event.get("object_type", ""),
                event.get("object_id", ""),
                event.get("status_before"),
                event.get("status_after"),
                1 if event.get("dry_run") else 0,
                event.get("note", ""),
            ),
        )
        connection.commit()


def record_provider_run(
    root: Path,
    *,
    run_id: str,
    provider: str,
    action: str,
    status: str,
    dry_run: bool,
    report_path: str | None = None,
) -> None:
    """Record one provider plan or execution."""

    init_database(root)
    with connect(root) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO provider_runs(
              run_id, provider, action, status, dry_run, report_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, provider, action, status, 1 if dry_run else 0, report_path, now_iso()),
        )
        connection.commit()


def record_phase_observation(
    root: Path,
    *,
    observation: dict[str, Any],
    path: Path,
) -> None:
    """Record one phase observation index row."""

    init_database(root)
    with connect(root) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO phase_observations(
              observation_id, status, path, accepted_packet_count,
              effective_edge_count, threshold_distance, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.get("observation_id"),
                "accepted" if observation.get("accepted") else "diagnostic",
                str(path),
                int(observation.get("accepted_packet_count", 0)),
                int(observation.get("effective_edge_count", 0)),
                float(observation.get("threshold_distance", 0.0)),
                now_iso(),
            ),
        )
        connection.commit()


def index_runtime(root: Path) -> dict[str, Any]:
    """Index existing JSON artifacts without modifying them."""

    init_database(root)
    indexed = 0
    patterns = [
        ("packet", root / "packets"),
        ("task", root / "tasks"),
        ("residual", root / "residuals"),
        ("report", root / "reports"),
        ("phase", root / "phase"),
    ]
    for object_type, base in patterns:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.json"), key=lambda item: str(item)):
            data = read_json(path)
            if not isinstance(data, dict):
                continue
            object_id = _object_id(object_type, data, path)
            status = data.get("status") or data.get("certificate_status")
            record_object(
                root,
                object_type=object_type,
                object_id=object_id,
                status=str(status) if status is not None else None,
                path=path,
                content=data,
            )
            indexed += 1
    events_path = blackboard_events_path(root)
    event_count = 0
    if events_path.exists():
        with events_path.open("r", encoding="utf-8") as handle:
            import json

            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                event = json.loads(stripped)
                if isinstance(event, dict):
                    record_event(root, event)
                    event_count += 1
    return {
        "database": str(database_path(root)),
        "events_indexed": event_count,
        "objects_indexed": indexed,
    }


def _object_id(object_type: str, data: dict[str, Any], path: Path) -> str:
    candidates = [
        f"{object_type}_id",
        "packet_id",
        "task_id",
        "residual_id",
        "report_id",
        "graph_id",
        "observation_id",
        "certificate_id",
        "comparison_id",
        "run_id",
        "import_id",
    ]
    for key in candidates:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return path.stem
