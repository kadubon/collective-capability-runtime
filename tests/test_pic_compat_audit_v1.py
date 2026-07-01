from __future__ import annotations

import json
from pathlib import Path

from ccr.audit.pic import audit_pic_compatibility
from ccr.cli import main
from ccr.providers.pic import PicProvider
from tests.conftest import REPO_ROOT


def test_audit_pic_with_source_root_preserves_missing_provider_as_residual(tmp_path, monkeypatch):
    pic_root = _fake_pic_root(tmp_path)
    monkeypatch.setattr("ccr.audit.pic.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "ccr.audit.pic._installed_distribution_version",
        lambda name: None,
    )

    report = audit_pic_compatibility(REPO_ROOT, pic_root=pic_root)

    assert report["ok"] is True
    assert report["pic_repo_version"] == "0.6.0"
    assert report["installed_package_version"] is None
    provider_missing = [
        finding for finding in report["findings"] if finding["kind"] == "provider_missing"
    ]
    assert provider_missing
    assert all(not finding["blocking"] for finding in provider_missing)
    assert all(
        finding["residual_ready"]["kind"] == "provider_missing" for finding in provider_missing
    )


def test_audit_pic_missing_root_returns_exit_code_2(tmp_path, capsys):
    missing = tmp_path / "missing-pic"

    exit_code = main(["audit", "pic", "--pic-root", str(missing), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["error"] == "pic root missing"
    assert payload["pic_root"] == str(missing)


def test_pic_provider_capabilities_expose_v060_commands_and_report_fields():
    capabilities = PicProvider().capabilities()

    for command in [
        "pic agent check --compact",
        "pic packet inspect",
        "pic phase plan --compact",
        "pic runtime collective-certify",
        "pic trc trace-normalize",
        "pic trc trace-check",
        "pic trc trace-to-packet",
    ]:
        assert command in capabilities["expected_pic_commands"]
    for field in [
        "accepted",
        "workflow_usable",
        "settled",
        "candidate_only_reasons",
        "settled_blockers",
        "safe_commands",
        "phase_gap_vector",
        "bottlenecks",
        "missing_obligations",
        "residuals",
        "cannot_promote_because",
        "execution_blockers",
        "real_world_operation_gate",
    ]:
        assert field in capabilities["supported_import_fields"]


def _fake_pic_root(tmp_path: Path) -> Path:
    root = tmp_path / "percolation-inversion-compiler"
    (root / "docs").mkdir(parents=True)
    (root / "examples" / "portability_conformance").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        """
[project]
name = "percolation-inversion-compiler"
version = "0.6.0"

[project.scripts]
pic = "percolation_inversion_compiler.cli:app"
""".strip(),
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        """
percolation-inversion-compiler supports pic agent check --compact and
pic phase plan --compact. Reports keep safe_commands and settled=false while
documenting accepted=true and workflow_usable.
""".strip(),
        encoding="utf-8",
    )
    (root / "docs" / "porting.md").write_text(
        "accepted=true workflow_usable settled candidate-only settled=false",
        encoding="utf-8",
    )
    (root / "docs" / "phase-acceleration.md").write_text(
        """
phase_gap_vector bottlenecks cannot_promote_because settled_blockers
safe_commands workflow_usable accepted=true settled=false
""".strip(),
        encoding="utf-8",
    )
    (root / "docs" / "v060-audit.md").write_text(
        "Package version: `0.6.0`; operation-readiness; "
        "safe_commands; accepted=true; settled=false",
        encoding="utf-8",
    )
    (root / "docs" / "ccr-pic-roundtrip.md").write_text(
        "CCR JSONL residual task interop",
        encoding="utf-8",
    )
    (root / "docs" / "asi-proxy-acceleration.md").write_text(
        "ASI-proxy TRC CCR acceleration guide",
        encoding="utf-8",
    )
    (root / "examples" / "asi_proxy_benchmark_bundle").mkdir(parents=True)
    (root / "examples" / "asi_proxy_benchmark_bundle" / "trc_agent_trace.json").write_text(
        """
{
  "authority_envelope": {},
  "resource_ledger": {},
  "tolerance_ledger": {}
}
""".strip(),
        encoding="utf-8",
    )
    (root / "examples" / "portability_conformance" / "phase_acceleration_plan.json").write_text(
        """
{
  "report_type": "PhaseAccelerationPlan",
  "candidate_only_reasons": [],
  "cannot_promote_because": [],
  "settled": false,
  "settled_blockers": [],
  "safe_commands": []
}
""".strip(),
        encoding="utf-8",
    )
    return root
