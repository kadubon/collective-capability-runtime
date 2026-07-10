# SPDX-License-Identifier: Apache-2.0
"""Generate or check the deterministic public schema registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ccr.ids import sha256_json
from ccr.schemas.loader import SCHEMA_FILENAMES
from ccr.schemas.registry import audit_schema_registry, source_report_versions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.write:
        _write_registry(root)
    report = audit_schema_registry(root)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def _write_registry(root: Path) -> None:
    specific = _specific_schema_versions(root)
    entries = []
    for version in sorted(source_report_versions(root)):
        kind = specific.get(version, "generic-report")
        schema_file = SCHEMA_FILENAMES[kind]
        schema = json.loads((root / "schemas" / schema_file).read_text(encoding="utf-8"))
        entries.append(
            {
                "origin": "external-candidate" if version.startswith("pic.") else "ccr-public",
                "schema_file": schema_file,
                "schema_kind": kind,
                "schema_sha256": sha256_json(schema),
                "schema_version": version,
            }
        )
    payload = {
        "entries": entries,
        "registry_digest": sha256_json(entries),
        "schema_version": "ccr.schema_registry.v1",
    }
    path = root / "schemas" / "schema-registry.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _specific_schema_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for kind, filename in SCHEMA_FILENAMES.items():
        path = root / "schemas" / filename
        if not path.exists() or kind == "generic-report":
            continue
        value: Any = json.loads(path.read_text(encoding="utf-8"))
        properties = value.get("properties", {}) if isinstance(value, dict) else {}
        version = properties.get("schema_version", {})
        if isinstance(version, dict) and isinstance(version.get("const"), str):
            versions[str(version["const"])] = kind
    return versions


if __name__ == "__main__":
    raise SystemExit(main())
