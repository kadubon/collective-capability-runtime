# SPDX-License-Identifier: Apache-2.0
"""Pinned local JSON evidence adapters. No imported code, commands or authority."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from ccr.ids import sha256_json
from ccr.optimizer.growth_model import closed
from ccr.storage.control import ControlStore

VERSION = "ccr.growth_interchange.v1"


def read_fixture(name: str) -> bytes:
    path = Path(__file__).resolve().parents[3] / "examples/verified_growth/interchange" / name
    if path.is_file():
        return path.read_bytes()
    return (
        resources.files("ccr.data")
        .joinpath("examples/verified_growth/interchange/" + name)
        .read_bytes()
    )


def import_evidence(envelope: dict[str, Any]) -> dict[str, Any]:
    closed(envelope, "tool source_commit schema_sha256 payload")
    sources = json.loads(read_fixture("sources.json"))
    tool = envelope["tool"]
    if tool not in {"vek", "alt"}:
        raise ValueError("only pinned VEK verifier packets and ALT tokens are importable")
    source = sources[tool]
    schema_bytes = read_fixture(tool + ".schema.json")
    if (
        envelope["source_commit"] != source["commit"]
        or envelope["schema_sha256"] != hashlib.sha256(schema_bytes).hexdigest()
    ):
        raise ValueError("unknown interchange version or schema digest")
    schema = json.loads(schema_bytes)
    dependency = json.loads(read_fixture("residual-record.schema.json"))
    registry: Registry[Any] = Registry().with_resource(
        dependency["$id"], Resource.from_contents(dependency)
    )
    errors = list(Draft202012Validator(schema, registry=registry).iter_errors(envelope["payload"]))
    if errors:
        raise ValueError("invalid companion schema: " + errors[0].message)
    p = envelope["payload"]
    mapped = (
        {
            "scope": p["scope"],
            "origin": p["origin"],
            "verifier_procedure": p["verifier_procedure"],
            "residuals": p["residual_obligations"],
            "exposure": p["anti_overclosure"],
            "dependence": "unknown",
        }
        if tool == "vek"
        else {
            "token_id": p["token_id"],
            "version": p["version"],
            "dependencies": p["dependencies"],
            "costs": p["cost_risk_model"],
            "guard": p["guard"],
            "provenance": p["provenance"],
        }
    )
    return {
        "schema_version": VERSION,
        "ok": True,
        "source": source,
        "source_digest": sha256_json(p),
        "mapped": mapped,
        "original": p,
        "evidence_only": True,
        "settled": False,
        "service_credit": 0,
        "receiver_qualified": False,
        "execution_authorized": False,
        "unsupported": [
            "causal surplus",
            "finality",
            "external truth",
            "service capacity",
            "execution permission",
        ],
    }


def export_cait(report: dict[str, Any]) -> dict[str, Any]:
    if "ledgers" not in report:
        raise ValueError("growth ledger report required")
    return {
        "schema_version": VERSION,
        "ok": True,
        "tool": "cait",
        "source": json.loads(read_fixture("sources.json"))["cait"],
        "mapped": {
            "window_balances": report["ledgers"],
            "costs": report["accounts"],
            "defeaters": report["residuals"],
            "unresolved_attribution": True,
        },
        "cait_conformant_certificate": False,
        "arrival_certificate": None,
        "settled": False,
        "unsupported": ["endogenous production intervals", "capital balance", "arrival"],
        "reason": "Service counts and typed costs cannot honestly fill CAIT capital intervals.",
    }


def attach(store: ControlStore, run_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
    """Append evidence and unresolved review work; never admit service or resolve debt."""
    from ccr.optimizer.engine import edit_run, response
    from ccr.optimizer.growth_ledger import append

    report = import_evidence(envelope)
    with edit_run(store, run_id) as (run, current):
        if "growth" not in run["config"]:
            raise ValueError("growth profile required")
        if any(
            row["kind"] == "interchange" and row["payload"] == report
            for row in run["growth_events"]
        ):
            return response(idempotent=True)
        append(run, "interchange", report, current)
        residual = {
            "residual_id": "residual:interchange:" + report["source_digest"],
            "kind": "companion_evidence_review",
            "blocking": False,
            "status": "open",
            "object_id": run["mission_id"],
            "source": report["source"],
            "original_residuals": report["mapped"].get("residuals"),
            "reason": "Imported evidence requires scoped independent CCR evaluation.",
        }
        run["residuals"].append(residual)
        run["revision"] += 1
        return response(mutated_runtime=True, evidence=report, residuals=[residual])
