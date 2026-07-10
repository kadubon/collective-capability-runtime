# SPDX-License-Identifier: Apache-2.0
"""Portable JSON and filesystem IO helpers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.ids import validate_identifier

DEFAULT_MAX_JSON_BYTES = 10_000_000
DEFAULT_MAX_JSONL_LINES = 100_000
DEFAULT_MAX_JSON_DEPTH = 100


def canonical_dumps(value: Any) -> str:
    """Return compact deterministic JSON."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_dumps(value: Any) -> str:
    """Return stable human-readable JSON."""

    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)


def read_json(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_JSON_BYTES,
    max_depth: int = DEFAULT_MAX_JSON_DEPTH,
) -> Any:
    """Read bounded JSON from disk and reject excessively nested input."""

    size = path.stat().st_size
    if size > max_bytes:
        raise ValueError(f"JSON input exceeds {max_bytes} bytes: {path}")
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    validate_json_depth(value, max_depth=max_depth)
    return value


def write_json_atomic(path: Path, value: Any, *, overwrite: bool = True) -> None:
    """Write JSON atomically within the target directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(str(path))
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(pretty_dumps(value))
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def append_jsonl(path: Path, value: Any) -> None:
    """Append one deterministic JSON line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_dumps(value))
        handle.write("\n")


def read_jsonl(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_JSON_BYTES,
    max_lines: int = DEFAULT_MAX_JSONL_LINES,
    max_depth: int = DEFAULT_MAX_JSON_DEPTH,
) -> list[Any]:
    """Read bounded JSON Lines, ignoring empty lines."""

    if not path.exists():
        return []
    if path.stat().st_size > max_bytes:
        raise ValueError(f"JSONL input exceeds {max_bytes} bytes: {path}")
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number > max_lines:
                raise ValueError(f"JSONL input exceeds {max_lines} lines: {path}")
            stripped = line.strip()
            if stripped:
                value = json.loads(stripped)
                validate_json_depth(value, max_depth=max_depth)
                records.append(value)
    return records


def json_file_name(object_id: str) -> str:
    """Return a portable JSON filename for a schema-safe id."""

    validated = validate_identifier(object_id, field="object_id")
    return validated.replace(":", "_") + ".json"


def validate_json_depth(value: Any, *, max_depth: int = DEFAULT_MAX_JSON_DEPTH) -> None:
    """Reject a decoded JSON value that exceeds the nesting limit."""

    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > max_depth:
            raise ValueError(f"JSON input exceeds maximum depth {max_depth}")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
