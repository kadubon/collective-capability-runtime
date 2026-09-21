# SPDX-License-Identifier: Apache-2.0
"""Read-only CPCF replanning through its maintained public facade."""

from __future__ import annotations

import copy
import importlib
import json
from typing import Any

from ccr.optimizer.native_checks import check
from ccr.optimizer.native_history import cpcf_history
from ccr.optimizer.native_wire import loads


def cpcf(run: dict[str, Any], raw: bytes) -> bytes:
    source = check(raw)
    if source["producer"] != "cpcf":
        raise ValueError("CPCF source required for observation replanning")
    documents = source["documents"]
    history = cpcf_history(run, source["document_sha256"]["contract"])
    facade = importlib.import_module("collective_phase_control_fabric.growth_control")
    frontier = documents["frontier"]["document"]
    domain = facade.Domain(
        facade.parse_document(documents["contract"]),
        {key: facade.parse_document(value) for key, value in documents["objects"].items()},
        facade.parse_document(documents["epistemic"]),
        facade.parse_document(frontier) if frontier is not None else None,
    )
    # Obtain the public typed history by parsing the registered document surface;
    # no private model class or producer implementation helper is imported.
    candidate = copy.deepcopy(documents["plan"])
    candidate["spec"]["history"] = history
    typed = facade.parse_document(candidate)
    plan = facade.plan_epistemic(domain, typed.spec.history)
    output = loads(raw)
    output["documents"]["plan"] = plan.model_dump_json()
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":")).encode("utf-8")
    check(encoded)
    return encoded
