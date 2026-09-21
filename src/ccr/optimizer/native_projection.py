# SPDX-License-Identifier: Apache-2.0
"""Explicit finite projections. The checker lives in native_projection_check."""

from __future__ import annotations

from typing import Any

from ccr.ids import sha256_json
from ccr.optimizer.native_checks import check


def project(raw: bytes, registration: dict[str, Any]) -> dict[str, Any]:
    source = check(raw)
    producer = source["producer"]
    docs = source["documents"]
    if producer == "alt":
        selected = docs["plan"]["selected"]
    elif producer == "vek":
        selected = list(docs["plan"]["schedule"])
    elif producer == "cpcf":
        policy = docs["plan"]["spec"]["policy"]
        selected = [policy["action_id"]] if policy else []
    else:
        selected = []
    bindings = [
        {"source_action": row["source_action"], "ccr_action": name}
        for name, row in registration["bindings"].items()
        if row["producer"] == producer
        and row["contract_sha256"] == source["document_sha256"].get("contract")
        and row["source_action"] in selected
    ]
    return {
        "schema_version": "ccr.native_projection.v1",
        "registration_sha256": sha256_json(registration),
        "source_sha256": source["source_sha256"],
        "document_sha256": source["document_sha256"],
        "producer": producer,
        "bindings": sorted(bindings, key=lambda b: b["ccr_action"]),
        "native_checker": source["native_checker"],
        "source_authentication": "unestablished",
        "service_credit": 0,
        "receiver_eligibility": False,
        "observed_capacity": None,
        "continuation_guarantee_transferred": False,
        "execution_authorization": False,
        "settled": False,
    }
