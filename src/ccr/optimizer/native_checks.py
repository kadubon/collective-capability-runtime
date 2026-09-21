# SPDX-License-Identifier: Apache-2.0
"""Fresh checks using fixed, optional released companion APIs.

These checks run before storage transactions. They neither install dependencies
nor load caller-named modules. Native acceptance never supplies CCR authority.
"""

from __future__ import annotations

import importlib
from typing import Any

from ccr.optimizer.growth_model import closed
from ccr.optimizer.native_artifacts import verify
from ccr.optimizer.native_schemas import validate
from ccr.optimizer.native_wire import loads, raw_digest

PACKAGES = {
    "alt": ("alt-foundry-kernel", "0.5.0"),
    "vek": ("verification-ecology-kit", "1.3.0"),
    "cait": ("cait-certificate-schema", "0.2.0"),
    "cpcf": ("collective-phase-control-fabric", "1.0.1"),
}


def inspect(raw: bytes) -> dict[str, Any]:
    source = loads(raw)
    validate("native-source", source)
    closed(source, "schema_version producer version documents")
    producer = source["producer"]
    names = {
        "alt": "contract plan tasks",
        "vek": "contract history plan report",
        "cait": "bundle report",
        "cpcf": "contract objects epistemic frontier plan",
    }
    closed(source["documents"], names[producer])
    documents = {}
    identities = {}
    for name, content in source["documents"].items():
        encoded = content.encode("utf-8")
        documents[name] = loads(encoded)
        identities[name] = raw_digest(encoded)
    return {
        "producer": producer,
        "version": source["version"],
        "source_sha256": raw_digest(raw),
        "document_sha256": identities,
        "documents": documents,
    }


def check(raw: bytes) -> dict[str, Any]:
    inspected = inspect(raw)
    producer = inspected["producer"]
    package, expected = PACKAGES[producer]
    artifact_pin = verify(producer)
    d = inspected["documents"]
    # Imports below are all fixed host code, never input-selected module paths.
    if producer == "alt":
        models = importlib.import_module("alt_foundry_kernel.reuse.contracts")
        checker = importlib.import_module("alt_foundry_kernel.reuse.checker")
        interchange = importlib.import_module("alt_foundry_kernel.reuse.interchange")
        contract = models.Contract.model_validate(d["contract"])
        plan = models.Plan.model_validate(d["plan"])
        result = checker.check_plan(contract, plan)
        exported = d["tasks"]
        if not exported.get("tasks"):
            raise ValueError("native ALT task sidecars required")
        first = exported["tasks"][0]
        revision = first["extensions"]["x_alt_reuse"]["original_revision"]
        reconstructed = interchange.ccr_tasks(contract, plan, first["created_at"], revision)
        if exported != reconstructed:
            raise ValueError("ALT native task/sidecar binding mismatch")
    elif producer == "vek":
        model = importlib.import_module("verification_ecology_kit.capacity.model")
        reducer = importlib.import_module("verification_ecology_kit.capacity.reducer")
        checker = importlib.import_module("verification_ecology_kit.capacity.checker")
        reports = importlib.import_module("verification_ecology_kit.capacity.report")
        closed(d["history"], "events")
        contract = model.Contract.from_dict(d["contract"])
        snapshot = reducer.replay(contract, d["history"]["events"])
        result = checker.check_plan(contract, snapshot, d["plan"]).to_dict()
        if d["report"] != reports.capacity_report(contract, snapshot, d["plan"]):
            raise ValueError("VEK report differs from replayed native sources")
    elif producer == "cait":
        checker = importlib.import_module("cait_schema.accounting.checker")
        result = checker.check_report(d["bundle"], d["report"])
        if result["status"] != "checked":
            raise ValueError("CAIT report not independently checked: " + str(result))
    else:
        facade = importlib.import_module("collective_phase_control_fabric.growth_control")
        closed(d["frontier"], "document")
        frontier = d["frontier"]["document"]
        domain = facade.Domain(
            facade.parse_document(d["contract"]),
            {key: facade.parse_document(value) for key, value in d["objects"].items()},
            facade.parse_document(d["epistemic"]),
            facade.parse_document(frontier) if frontier is not None else None,
        )
        plan = facade.parse_document(d["plan"])
        result = facade.check_epistemic_plan(domain, plan)
        if not result["policy_feasible"]:
            raise ValueError("CPCF policy is not feasible")
    return {
        **inspected,
        "native_checker": {
            "package": package,
            "version": expected,
            "artifact_pin_sha256": artifact_pin,
            "result": result,
        },
        "source_authentication": "unestablished",
        "ccr_admission": False,
        "receiver_eligibility": False,
        "service_observation": None,
        "causal_attribution": None,
        "execution_authorization": False,
    }
