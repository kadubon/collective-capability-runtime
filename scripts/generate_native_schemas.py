# SPDX-License-Identifier: Apache-2.0
"""Generate closed CCR-owned native source, registration and projection schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def record(properties: dict[str, Any], optional: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [k for k in properties if k not in optional],
    }


def mapping(value: dict[str, Any], maximum: int, minimum: int = 0) -> dict[str, Any]:
    return {
        "type": "object",
        "minProperties": minimum,
        "maxProperties": maximum,
        "propertyNames": {"type": "string", "minLength": 1, "maxLength": 256},
        "additionalProperties": value,
    }


def main() -> None:
    directory = Path(__file__).resolve().parents[1] / "schemas"
    text = {"type": "string", "minLength": 1, "maxLength": 256}
    digest = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
    timestamp = {"type": "string", "format": "date-time", "maxLength": 40}
    producer = {"enum": ["alt", "vek", "cait", "cpcf"]}
    documents = {
        "alt": ("0.5.0", "contract plan tasks"),
        "vek": ("1.3.0", "contract history plan report"),
        "cait": ("0.2.0", "bundle report"),
        "cpcf": ("1.0.1", "contract objects epistemic frontier plan"),
    }
    source = record(
        {
            "schema_version": {"const": "ccr.native_source.v1"},
            "producer": producer,
            "version": text,
            "documents": mapping({"type": "string", "minLength": 2, "maxLength": 131072}, 5, 2),
        }
    )
    source["allOf"] = [
        {
            "if": {"properties": {"producer": {"const": p}}},
            "then": {
                "properties": {
                    "version": {"const": version},
                    "documents": record(
                        {
                            name: {"type": "string", "minLength": 2, "maxLength": 131072}
                            for name in names.split()
                        }
                    ),
                }
            },
        }
        for p, (version, names) in documents.items()
    ]
    binding = record(
        {
            "producer": producer,
            "contract_sha256": digest,
            "source_action": text,
            "action_sha256": digest,
            "valid_from": timestamp,
            "valid_until": timestamp,
            "observations": {
                "type": "object",
                "additionalProperties": False,
                "minProperties": 1,
                "properties": {
                    s: text
                    for s in (
                        "success",
                        "failed",
                        "timeout",
                        "invalid",
                        "inconclusive",
                        "pending",
                        "censored",
                    )
                },
            },
        },
        ("observations",),
    )
    registration = record(
        {
            "schema_version": {"const": "ccr.native_registration.v1"},
            "run_id": text,
            "config_digest": digest,
            "study_id": text,
            "arm": {"const": "training"},
            "pool_id": text,
            "bindings": mapping(binding, 64, 1),
            "pools": mapping(text, 32),
            "units": mapping(
                record(
                    {
                        "target": text,
                        "rate": {
                            "type": "string",
                            "maxLength": 81,
                            "pattern": "^[1-9][0-9]*(/[1-9][0-9]*)?$",
                        },
                        "rounding": {"enum": ["exact", "upper"]},
                    }
                ),
                32,
            ),
        },
        ("pools",),
    )
    # Foreign checker result content is independently validated by the pinned
    # producer, then compared exactly during CCR checking. No fields are authority.
    projection = record(
        {
            "schema_version": {"const": "ccr.native_projection.v1"},
            "registration_sha256": digest,
            "source_sha256": digest,
            "document_sha256": mapping(digest, 5, 2),
            "producer": producer,
            "bindings": {
                "type": "array",
                "maxItems": 64,
                "uniqueItems": True,
                "items": record({"source_action": text, "ccr_action": text}),
            },
            "native_checker": record(
                {
                    "package": text,
                    "version": text,
                    "artifact_pin_sha256": digest,
                    "result": {"type": "object", "maxProperties": 512},
                }
            ),
            "source_authentication": {"const": "unestablished"},
            "service_credit": {"type": "integer", "const": 0},
            "observed_capacity": {"type": "null"},
            **{
                k: {"const": False}
                for k in (
                    "receiver_eligibility",
                    "continuation_guarantee_transferred",
                    "execution_authorization",
                    "settled",
                )
            },
        }
    )
    for name, schema in {
        "native-source": source,
        "native-registration": registration,
        "native-projection": projection,
    }.items():
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (directory / (name + ".schema.json")).write_text(
            json.dumps(schema, indent=2) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
