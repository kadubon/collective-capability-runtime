"""Local fixture checklist for the CCR/PIC/PIC-TS v0.8 roundtrip."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples" / "asi_proxy_acceleration_bundle"
REQUIRED_FILES = [
    "target.json",
    "baseline_upper_envelope.json",
    "capital_witnesses.jsonl",
    "phase_acceleration_report.expected.json",
    "phase_response_control_step.accepted.json",
    "foundry_cuts.example.json",
    "foundry_budget.example.json",
    "trc_operation_gate.expired_authority.json",
    "trc_operation_gate.physical_missing.json",
    "trc_operation_gate.physical_ready_fixture.json",
    "preflight.denied.json",
    "preflight.ready_fixture.json",
    "foundry_dashboard.blocked_dependency.json",
    "mcp_descriptor.good.json",
    "mcp_descriptor.rug_pull.json",
    "a2a_handoff.good.json",
    "bit_mec_certificates.jsonl",
    "sqot_protocol_integrity.missing_root.json",
]


def read_json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((BUNDLE / name).read_text(encoding="utf-8")))


def main() -> int:
    missing = [name for name in REQUIRED_FILES if not (BUNDLE / name).is_file()]
    report = read_json("phase_acceleration_report.expected.json")
    required_report_keys = {
        "schema_version",
        "target_id",
        "target_validity_ok",
        "baseline_envelope_ok",
        "capital_witnesses",
        "k_alt_lower",
        "k_baseline_upper",
        "margin_delta",
        "certified_acceleration_candidate",
        "residuals",
        "blockers",
        "non_claims",
        "settled",
    }
    missing_keys = sorted(required_report_keys - set(report))
    failures = [f"missing fixture: {name}" for name in missing]
    failures.extend(f"missing report key: {key}" for key in missing_keys)
    if report.get("settled") is not False:
        failures.append("phase report must keep settled=false")
    non_claims = report.get("non_claims", [])
    if not isinstance(non_claims, list):
        non_claims = []
    if "real_asi_proof" not in " ".join(str(item) for item in non_claims):
        failures.append("phase report must keep real-ASI non-claim visible")
    if failures:
        print("\n".join(failures))
        return 1
    print("cross-repo fixture checklist passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
