# SPDX-License-Identifier: Apache-2.0
"""Storage diagnostics, migration previews, and reconciliation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import sha256_json
from ccr.io import read_json
from ccr.safe_io import is_path_within_root
from ccr.storage.sqlite import connect, database_path, index_runtime, init_database


def storage_doctor(root: Path) -> dict[str, Any]:
    init_database(root)
    with connect(root) as connection:
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = list(connection.execute("PRAGMA foreign_key_check"))
        outbox_pending = int(
            connection.execute("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL").fetchone()[
                0
            ]
        )
    reconcile = storage_reconcile(root)
    blockers = []
    if integrity != "ok":
        blockers.append("sqlite_integrity_failed")
    if foreign_keys:
        blockers.append("sqlite_foreign_key_failed")
    if reconcile["mismatches"]:
        blockers.append("artifact_index_mismatch")
    return {
        "backend": "sqlite",
        "blockers": blockers,
        "database": str(database_path(root)),
        "foreign_key_errors": len(foreign_keys),
        "integrity": integrity,
        "ok": not blockers,
        "outbox_pending": outbox_pending,
        "reconcile": reconcile,
        "schema_version": "ccr.storage_doctor.v1",
    }


def storage_migrate(root: Path, *, apply: bool = False) -> dict[str, Any]:
    """Preview or apply additive SQLite indexing without rewriting source JSON."""

    artifacts = _artifacts(root)
    invalid_paths = [str(path) for path in artifacts if not is_path_within_root(path, root)]
    preview = [
        {
            "content_sha256": sha256_json(data),
            "path": str(path.relative_to(root)).replace("\\", "/"),
            "schema_version": data.get("schema_version"),
            "status": data.get("status"),
        }
        for path in artifacts
        if is_path_within_root(path, root)
        for data in [read_json(path)]
        if isinstance(data, dict)
    ]
    result: dict[str, Any] = {
        "applied": False,
        "artifact_count": len(preview),
        "artifacts": preview,
        "invalid_paths": invalid_paths,
        "ok": not invalid_paths,
        "schema_version": "ccr.storage_migration.v1",
    }
    if apply and not invalid_paths:
        result["index"] = index_runtime(root)
        result["applied"] = True
    return result


def storage_reconcile(root: Path) -> dict[str, Any]:
    """Report index/file disagreement without silently repairing either side."""

    init_database(root)
    mismatches: list[dict[str, str]] = []
    with connect(root) as connection:
        rows = connection.execute(
            "SELECT object_type, object_id, path, content_sha256 "
            "FROM objects ORDER BY object_type, object_id"
        ).fetchall()
    for row in rows:
        path = Path(str(row[2]))
        if not is_path_within_root(path, root):
            mismatches.append(
                {"kind": "indexed_path_escape", "object_id": str(row[1]), "path": str(path)}
            )
            continue
        if not path.exists():
            mismatches.append(
                {"kind": "indexed_file_missing", "object_id": str(row[1]), "path": str(path)}
            )
            continue
        data = read_json(path)
        if sha256_json(data) != str(row[3]):
            mismatches.append(
                {"kind": "content_digest_mismatch", "object_id": str(row[1]), "path": str(path)}
            )
    return {
        "checked_index_rows": len(rows),
        "mismatches": mismatches,
        "mutated": False,
        "ok": not mismatches,
        "schema_version": "ccr.storage_reconcile.v1",
    }


def _artifacts(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in ("packets", "tasks", "residuals", "reports", "phase"):
        base = root / directory
        if base.exists():
            paths.extend(base.rglob("*.json"))
    return sorted(paths, key=lambda item: str(item))
