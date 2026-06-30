# SPDX-License-Identifier: Apache-2.0
"""JSON Schema validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from ccr.schemas.loader import expected_schema_version, load_schema


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable schema validation issue."""

    path: str
    schema_path: str
    message: str
    validator: str

    def to_json(self) -> dict[str, str]:
        """Return JSON-compatible issue data."""

        return {
            "message": self.message,
            "path": self.path,
            "schema_path": self.schema_path,
            "validator": self.validator,
        }


@dataclass(frozen=True)
class ValidationResult:
    """Stable validation result."""

    ok: bool
    schema_version: str | None
    errors: tuple[ValidationIssue, ...]

    def to_json(self) -> dict[str, Any]:
        """Return JSON-compatible result."""

        return {
            "errors": [issue.to_json() for issue in self.errors],
            "ok": self.ok,
            "schema_version": self.schema_version,
        }


def _format_path(parts: list[Any]) -> str:
    if not parts:
        return "$"
    rendered = "$"
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}"
    return rendered


def validate_instance(kind: str, instance: Any, *, root: Path | None = None) -> ValidationResult:
    """Validate an instance and return sorted machine-readable errors."""

    schema = load_schema(kind, root=root)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = [
        ValidationIssue(
            path=_format_path(list(error.path)),
            schema_path=_format_path(list(error.schema_path)),
            message=error.message,
            validator=error.validator,
        )
        for error in validator.iter_errors(instance)
    ]
    issues.sort(key=lambda issue: (issue.path, issue.schema_path, issue.message))
    return ValidationResult(
        ok=not issues,
        schema_version=expected_schema_version(kind, root=root),
        errors=tuple(issues),
    )
