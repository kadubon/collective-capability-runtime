# SPDX-License-Identifier: Apache-2.0
"""Runtime configuration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.io import read_json
from ccr.paths import config_path


def load_config(root: Path) -> dict[str, Any]:
    """Load runtime config or return a conservative default."""

    path = config_path(root)
    if path.exists():
        data = read_json(path)
        if isinstance(data, dict):
            return data
    return {
        "schema_version": "ccr.config.v0.1",
        "default_mode": "dry_run",
        "external_side_effects_default": "none",
    }
