"""Local fixture checklist for the CCR/PIC/PIC-TS v0.9 loop roundtrip."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "examples" / "asi_proxy_loop_bundle"
REQUIRED_FILES = [
    "target.json",
    "baseline_upper_envelope.json",
    "capital_witnesses.jsonl",
    "ccr_loop_state.json",
    "foundry_active_cuts.json",
    "phase_acceleration_interval_report.expected.json",
    "pic_token_admissibility.example.json",
    "pic_extraction_pipeline.example.json",
    "mcp_gate_binding.example.json",
    "a2a_gate_binding.example.json",
    "observation_residuals.example.json",
    "performance_report.example.json",
]


def read_json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((BUNDLE / name).read_text(encoding="utf-8")))


def main() -> int:
    missing = [name for name in REQUIRED_FILES if not (BUNDLE / name).is_file()]
    report = read_json("phase_acceleration_interval_report.expected.json")
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
        "certified_acceleration_interval_candidate",
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
