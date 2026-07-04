from __future__ import annotations

import json
import shutil
from pathlib import Path

from ccr.bundles.validate import validate_bundle
from tests.conftest import REPO_ROOT


def _copy_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    shutil.copytree(REPO_ROOT / "examples" / "asi_proxy_mission_bundle", bundle)
    return bundle


def test_bundle_validate_blocks_missing_unhashed_path_ref(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    state_path = bundle / "mission_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["target_path"] = "missing-target.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    report = validate_bundle(bundle)

    assert report["ok"] is False
    assert "path_ref_missing" in report["blockers"]


def test_bundle_validate_requires_all_mission_non_claims(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    for path in ("bundle.json", "mission.json", "target.json"):
        data = json.loads((bundle / path).read_text(encoding="utf-8"))
        data["non_claims"] = [
            "not_real_asi_proof",
            "not_execution_authority",
            "not_physical_outcome_proof",
        ]
        (bundle / path).write_text(json.dumps(data), encoding="utf-8")

    report = validate_bundle(bundle)

    assert report["ok"] is False
    assert "missing_non_claims" in report["blockers"]


def test_bundle_validate_blocks_target_baseline_mismatch(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    target_path = bundle / "target.json"
    target = json.loads(target_path.read_text(encoding="utf-8"))
    target["baseline_upper_envelope_ref"] = "baseline:other"
    target_path.write_text(json.dumps(target), encoding="utf-8")

    report = validate_bundle(bundle)

    assert report["ok"] is False
    assert "target_baseline_ref_mismatch" in report["blockers"]


def test_bundle_validate_keeps_path_law_refs_conceptual(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)

    report = validate_bundle(bundle)

    assert "unresolved_reference" not in report["blockers"]
    assert report["ok"] is True
