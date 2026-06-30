# SPDX-License-Identifier: Apache-2.0
"""Portable JSON and filesystem IO helpers."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any


def canonical_dumps(value: Any) -> str:
    """Return compact deterministic JSON."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_dumps(value: Any) -> str:
    """Return stable human-readable JSON."""

    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)


def read_json(path: Path) -> Any:
    """Read JSON from disk."""

    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def read_jsonl(path: Path) -> list[Any]:
    """Read JSON Lines, ignoring empty lines."""

    if not path.exists():
        return []
    records: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def json_file_name(object_id: str) -> str:
    """Return a portable JSON filename for a schema-safe id."""

    unsafe = '<>:"/\\|?*'
    translated = "".join("_" if char in unsafe or ord(char) < 32 else char for char in object_id)
    return translated + ".json"
