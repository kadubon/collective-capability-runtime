# SPDX-License-Identifier: Apache-2.0
"""CCR-owned wire schemas, separate from pinned producer schemas."""

from __future__ import annotations

from typing import Any

from ccr.schemas.validation import validate_instance

VERSIONS = {
    "native-source": "ccr.native_source.v1",
    "native-registration": "ccr.native_registration.v1",
    "native-projection": "ccr.native_projection.v1",
    "native-accounting-export": "ccr.native_accounting_export.v1",
}


def validate(kind: str, value: dict[str, Any]) -> None:
    if value.get("schema_version") != VERSIONS[kind] or not validate_instance(kind, value).ok:
        raise ValueError("invalid closed " + kind + " schema")
