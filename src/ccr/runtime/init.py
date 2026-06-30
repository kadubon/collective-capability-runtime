# SPDX-License-Identifier: Apache-2.0
"""Initialize a CCR runtime directory."""

from __future__ import annotations

from pathlib import Path

from ccr.constants import CONFIG_FILENAME, NON_CLAIMS, RUNTIME_DIRECTORIES
from ccr.io import write_json_atomic
from ccr.paths import blackboard_events_path
from ccr.storage.sqlite import index_runtime, init_database
from ccr.time import now_iso


def init_runtime(root: Path, *, force: bool = False) -> dict[str, object]:
    """Create the runtime directory layout idempotently."""

    root.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    existing: list[str] = []
    for relative in RUNTIME_DIRECTORIES:
        path = root / relative
        if path.exists():
            existing.append(relative)
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(relative)

    events_path = blackboard_events_path(root)
    if events_path.exists():
        existing.append("blackboard/events.jsonl")
    else:
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("", encoding="utf-8")
        created.append("blackboard/events.jsonl")

    config_path = root / CONFIG_FILENAME
    wrote_config = force or not config_path.exists()
    if wrote_config:
        write_json_atomic(
            config_path,
            {
                "created_at": now_iso(),
                "default_mode": "dry_run",
                "external_side_effects_default": "none",
                "non_claims": list(NON_CLAIMS),
                "runtime_directories": list(RUNTIME_DIRECTORIES),
                "schema_version": "ccr.config.v0.1",
            },
            overwrite=True,
        )
        if str(CONFIG_FILENAME) not in created:
            created.append(CONFIG_FILENAME)
    else:
        existing.append(CONFIG_FILENAME)

    database = init_database(root)
    index = index_runtime(root)

    return {
        "config_written": wrote_config,
        "created": sorted(set(created)),
        "database": database,
        "existing": sorted(set(existing)),
        "index": index,
        "ok": True,
        "root": str(root),
    }
