# SPDX-License-Identifier: Apache-2.0
"""Residual file store."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ccr.ids import validate_identifier
from ccr.io import json_file_name, read_json, write_json_atomic
from ccr.safe_io import require_path_within_root
from ccr.schemas.validation import validate_instance


def residual_path(root: Path, residual_id: str, status: str = "open") -> Path:
    """Return storage path for a residual."""

    validate_identifier(residual_id, field="residual_id")
    validate_identifier(status, field="residual_status")
    path = root / "residuals" / status / json_file_name(residual_id)
    return require_path_within_root(path, root, field="residual path")


def save_residual(root: Path, residual: dict[str, Any], *, overwrite: bool = True) -> Path:
    """Validate and save a residual."""

    result = validate_instance("residual", residual, root=root)
    if not result.ok:
        messages = "; ".join(issue.message for issue in result.errors)
        raise ValueError(f"invalid residual: {messages}")
    status = str(residual.get("status", "open"))
    path = residual_path(root, str(residual["residual_id"]), status)
    write_json_atomic(path, residual, overwrite=overwrite)
    return path


def iter_residuals(root: Path, *, status: str | None = None) -> Iterable[dict[str, Any]]:
    """Iterate residuals, optionally constrained by status."""

    statuses = [status] if status else ["open", "resolved", "quarantined"]
    for current in statuses:
        directory = root / "residuals" / current
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            data = read_json(path)
            if isinstance(data, dict):
                yield data


def linked_open_blocking_residuals(root: Path, object_id: str) -> list[dict[str, Any]]:
    """Return open blocking residuals linked to an object id."""

    matches: list[dict[str, Any]] = []
    for residual in iter_residuals(root, status="open"):
        refs = residual.get("refs", [])
        if not isinstance(refs, list):
            refs = []
        if residual.get("blocking") and (
            residual.get("object_id") == object_id or object_id in refs
        ):
            matches.append(residual)
    return matches
