# SPDX-License-Identifier: Apache-2.0
"""Deterministic public report schema registry."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

from ccr.ids import sha256_json
from ccr.schemas.loader import load_schema

VERSION_RE = re.compile(r'["\']((?:ccr|pic)\.[A-Za-z0-9_.-]+\.v\d+(?:\.\d+)?)["\']')


def source_report_versions(root: Path) -> set[str]:
    versions: set[str] = set()
    for path in sorted((root / "src" / "ccr").rglob("*.py")):
        versions.update(VERSION_RE.findall(path.read_text(encoding="utf-8")))
    return versions


def load_registry(*, root: Path | None = None) -> dict[str, Any]:
    if root is not None:
        path = root / "schemas" / "schema-registry.json"
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return cast(dict[str, Any], value)
    text = (
        resources.files("ccr.data")
        .joinpath("schemas/schema-registry.json")
        .read_text(encoding="utf-8")
    )
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("schema registry must be a JSON object")
    return cast(dict[str, Any], value)


def audit_schema_registry(root: Path) -> dict[str, Any]:
    registry = load_registry(root=root)
    entries = registry.get("entries")
    if not isinstance(entries, list):
        return {"digest_valid": False, "missing": ["registry_entries"], "ok": False}
    registered = {str(item.get("schema_version")) for item in entries if isinstance(item, dict)}
    source = source_report_versions(root)
    expected_digest = sha256_json(entries)
    digest_mismatches = []
    for entry in entries:
        if not isinstance(entry, dict):
            digest_mismatches.append("invalid_registry_entry")
            continue
        schema_file = entry.get("schema_file")
        path = root / "schemas" / str(schema_file)
        if not path.exists():
            digest_mismatches.append(str(schema_file))
            continue
        schema = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("schema_sha256") != sha256_json(schema):
            digest_mismatches.append(str(schema_file))
    return {
        "digest_valid": registry.get("registry_digest") == expected_digest,
        "schema_digest_mismatches": sorted(set(digest_mismatches)),
        "extra": sorted(registered - source),
        "missing": sorted(source - registered),
        "ok": not (source - registered)
        and not digest_mismatches
        and registry.get("registry_digest") == expected_digest,
        "registered_count": len(registered),
        "source_version_count": len(source),
    }


def validate_registered_report(report: dict[str, Any], *, root: Path | None = None) -> list[str]:
    version = report.get("schema_version")
    if not isinstance(version, str):
        return ["schema_version is required"]
    registry = load_registry(root=root)
    entries = registry.get("entries", [])
    entry = next(
        (
            item
            for item in entries
            if isinstance(item, dict) and item.get("schema_version") == version
        ),
        None,
    )
    if entry is None:
        return [f"unregistered schema_version: {version}"]
    kind = str(entry.get("schema_kind", "generic-report"))
    schema = load_schema(kind, root=root)
    if entry.get("schema_sha256") != sha256_json(schema):
        return [f"registered schema digest mismatch: {version}"]
    validator = Draft202012Validator(schema)
    return sorted(error.message for error in validator.iter_errors(report))
