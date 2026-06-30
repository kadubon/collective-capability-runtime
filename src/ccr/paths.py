# SPDX-License-Identifier: Apache-2.0
"""Runtime path helpers."""

from __future__ import annotations

import os
from pathlib import Path

from ccr.constants import CONFIG_FILENAME, MANIFEST_FILENAME


def runtime_root(value: str | None = None) -> Path:
    """Resolve the CCR runtime root from an argument, env var, or current directory."""

    raw = value or os.environ.get("CCR_ROOT") or "."
    return Path(raw).expanduser().resolve()


def config_path(root: Path) -> Path:
    """Return the runtime config path."""

    return root / CONFIG_FILENAME


def manifest_path(root: Path) -> Path:
    """Return the local agent manifest path."""

    return root / MANIFEST_FILENAME


def schemas_dir(root: Path) -> Path:
    """Return local schema directory."""

    return root / "schemas"


def blackboard_events_path(root: Path) -> Path:
    """Return blackboard event log path."""

    return root / "blackboard" / "events.jsonl"
