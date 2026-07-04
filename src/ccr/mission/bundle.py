# SPDX-License-Identifier: Apache-2.0
"""Mission bundle helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import read_json


def read_mission_bundle(root: Path) -> list[dict[str, Any]]:
    """Read JSON objects from a mission bundle directory."""

    objects: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json"), key=lambda item: str(item)):
        data = read_json(path)
        if isinstance(data, dict):
            objects.append(data)
    return objects
