# SPDX-License-Identifier: Apache-2.0
"""RuntimeStore profile selection."""

from __future__ import annotations

from pathlib import Path

from ccr.storage.base import RuntimeStore
from ccr.storage.local_store import SQLiteRuntimeStore
from ccr.storage.postgres_store import PostgresRuntimeStore


def create_store(*, root: Path, database_url: str | None = None) -> RuntimeStore:
    if database_url:
        return PostgresRuntimeStore(database_url, export_root=root)
    return SQLiteRuntimeStore(root)
