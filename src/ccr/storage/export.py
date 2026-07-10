# SPDX-License-Identifier: Apache-2.0
"""Content-addressed JSON exports from authoritative storage profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.ids import sha256_json, validate_identifier
from ccr.io import write_json_atomic
from ccr.safe_io import require_path_within_root


def export_content_addressed(
    root: Path,
    *,
    object_type: str,
    object_id: str,
    content: dict[str, Any],
) -> dict[str, Any]:
    validate_identifier(object_type, field="object_type")
    digest = sha256_json(content)
    path = require_path_within_root(
        root / "exports" / object_type / f"sha256-{digest}.json",
        root,
        field="content-addressed export path",
    )
    payload = {
        "content": content,
        "content_sha256": digest,
        "object_id": object_id,
        "object_type": object_type,
        "schema_version": "ccr.content_addressed_export.v1",
    }
    write_json_atomic(path, payload)
    return {"content_sha256": digest, "path": str(path)}
