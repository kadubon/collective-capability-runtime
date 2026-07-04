# SPDX-License-Identifier: Apache-2.0
"""Bundle export placeholders for future additive surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def bundle_export_manifest(output_dir: Path, files: list[Path]) -> dict[str, Any]:
    """Return a deterministic manifest for an explicit bundle export."""

    return {
        "file_count": len(files),
        "files": [str(path) for path in sorted(files, key=lambda item: str(item))],
        "output_dir": str(output_dir),
        "schema_version": "ccr.bundle_export_manifest.v1",
        "settled": False,
    }
