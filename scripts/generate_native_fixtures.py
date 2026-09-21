# SPDX-License-Identifier: Apache-2.0
"""Developer setup only: generate inert fixtures with installed pinned producers.

CPCF inputs must first be emitted by its public CLI:
cpcf growth example .tmp/cpcf-native --scenario epistemic-probe --output .tmp/cpcf-result.json
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from ccr.optimizer.native_checks import PACKAGES, check

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "examples/native_interchange"


def encoded(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> None:
    examples = importlib.import_module("alt_foundry_kernel.reuse.examples")
    planning = importlib.import_module("alt_foundry_kernel.reuse.planning")
    interchange = importlib.import_module("alt_foundry_kernel.reuse.interchange")
    contract = examples.contract_example()
    plan = planning.select(contract)
    bundles = {
        "alt": {
            "contract": contract.model_dump(),
            "plan": plan.model_dump(),
            "tasks": interchange.ccr_tasks(contract, plan, "2026-09-21T00:00:00Z", "0"),
        }
    }
    demand = interchange.vek_demand(contract, plan)
    model = importlib.import_module("verification_ecology_kit.capacity.model")
    checker = importlib.import_module("verification_ecology_kit.capacity.checker")
    reports = importlib.import_module("verification_ecology_kit.capacity.report")
    native_contract = model.Contract.from_dict(demand["native_contract"])
    snapshot = checker.Snapshot(spent=[0, 0])
    native_plan = {
        "contract_digest": native_contract.contract_digest,
        "source_digest": snapshot.source_digest,
        "revision": 0,
        "schedule": demand["schedule"],
        "checked": checker.check_schedule(native_contract, snapshot, demand["schedule"]).to_dict(),
        "search": {
            "complete": False,
            "candidates": 1,
            "examined": 1,
            "valid": 1,
            "budget": 10000,
            "checker_calls": 1,
            "rejections": {},
            "status": "feasible",
            "optimality": "checked-incumbent",
        },
    }
    bundles["vek"] = {
        "contract": native_contract.to_dict(),
        "history": {"events": []},
        "plan": native_plan,
        "report": reports.capacity_report(native_contract, snapshot, native_plan),
    }
    converter = importlib.import_module("alt_foundry_kernel.reuse.cait_export")
    analyzer = importlib.import_module("cait_schema.accounting.report")
    source = converter.export_cait(
        examples.history_example(), 20, "synthetic-tick", {"resource": "100"}
    )["native_bundle"]
    bundles["cait"] = {"bundle": source, "report": analyzer.analyze(source)}
    cpcf = ROOT / ".tmp/cpcf-native"
    bundles["cpcf"] = {
        "contract": json.loads((cpcf / "contract.json").read_bytes()),
        "objects": {
            "sha256:" + p.stem: json.loads(p.read_bytes())
            for p in (cpcf / "objects").glob("*.json")
        },
        "epistemic": json.loads((cpcf / "epistemic.json").read_bytes()),
        "frontier": {
            "document": json.loads((cpcf / "frontier.json").read_bytes())
            if (cpcf / "frontier.json").exists()
            else None
        },
        "plan": json.loads((ROOT / ".tmp/cpcf-result.json").read_bytes())["plan"],
    }
    DEST.mkdir(exist_ok=True)
    for producer, documents in bundles.items():
        raw = encoded(
            {
                "producer": producer,
                "version": PACKAGES[producer][1],
                "documents": {key: encoded(value) for key, value in documents.items()},
            }
        ).encode()
        result = check(raw)
        (DEST / (producer + ".json")).write_bytes(raw + b"\n")
        print(producer, result["native_checker"]["version"], "native_checked")


if __name__ == "__main__":
    main()
