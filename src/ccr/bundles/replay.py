# SPDX-License-Identifier: Apache-2.0
"""Non-executing bundle replay diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def replay_plan(bundle: Path) -> dict[str, Any]:
    """Return a non-executing replay plan for a bundle."""

    return {
        "bundle": str(bundle),
        "executed": False,
        "external_execution": False,
        "ok": True,
        "schema_version": "ccr.bundle_replay_plan.v1",
        "settled": False,
        "steps": [],
    }
