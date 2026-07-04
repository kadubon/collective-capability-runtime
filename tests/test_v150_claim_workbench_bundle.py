from __future__ import annotations

from pathlib import Path

from ccr.bundles.validate import validate_bundle
from ccr.claims.audit import audit_claim_file
from ccr.claims.extract import write_claim_extract
from ccr.claims.passport import write_claim_passport
from ccr.io import read_json, write_json_atomic
from tests.conftest import REPO_ROOT


def test_claim_audit_blocks_real_asi_overclaim_but_not_explicit_non_claim(
    tmp_path: Path,
) -> None:
    source = tmp_path / "claims.md"
    source.write_text(
        "CCR detects real ASI.\n\nCCR does not detect real ASI.\n",
        encoding="utf-8",
    )

    report = audit_claim_file(source)

    assert report["ok"] is False
    assert report["overclaim_count"] == 1
    assert any(item["blocking"] for item in report["residual_ready"])
    assert "CCR does not detect real ASI." in report["non_claims"]


def test_claim_extract_and_passport_write_json(tmp_path: Path) -> None:
    source = tmp_path / "claims.md"
    source.write_text("CCR preserves residuals. Evidence: README.md\n", encoding="utf-8")
    claims = tmp_path / "claims.json"
    passport = tmp_path / "claim-passport.json"

    extract_report = write_claim_extract(source, claims)
    passport_report = write_claim_passport(claims, passport)
    passport_json = read_json(passport)

    assert extract_report["ok"] is True
    assert passport_report["ok"] is True
    assert passport_json["schema_version"] == "ccr.claim_passport.v1"
    assert passport_json["claim_count"] == 1
    assert passport_json["settled"] is False


def test_bundle_validate_accepts_quickstart_fixture() -> None:
    report = validate_bundle(
        REPO_ROOT / "examples" / "asi_proxy_mission_bundle",
        profile="development",
    )

    assert report["schema_version"] == "ccr.bundle_validate.v1"
    assert report["ok"] is True
    assert report["settled"] is False
    assert report["executed"] is False


def test_bundle_validate_blocks_missing_target_and_baseline(tmp_path: Path) -> None:
    write_json_atomic(
        tmp_path / "mission.json",
        {
            "mission_id": "mission:broken",
            "non_claims": ["not_real_asi_proof"],
            "schema_version": "ccr.mission.v1",
            "settled": False,
        },
    )

    report = validate_bundle(tmp_path, profile="development")

    assert report["ok"] is False
    assert "missing_target" in report["blockers"]
    assert "missing_baseline" in report["blockers"]
