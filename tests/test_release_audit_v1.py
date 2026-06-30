from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path

from ccr.audit.release import audit_release
from ccr.cli import main


def test_release_audit_accepts_clean_source_and_dist(tmp_path):
    root = _clean_release_root(tmp_path)

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is True
    assert report["findings"] == []


def test_release_audit_fails_on_local_home_path(tmp_path):
    root = _clean_release_root(tmp_path)
    (root / "README.md").write_text("leak " + "C:" + "\\Users\\local\\file", encoding="utf-8")

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is False
    assert any(finding["kind"] == "release-local-path" for finding in report["findings"])


def test_release_audit_fails_on_generated_artifacts(tmp_path):
    root = _clean_release_root(tmp_path)
    (root / "examples" / "phase_formation" / "blackboard").mkdir(parents=True)
    (root / "examples" / "phase_formation" / "blackboard" / "events.jsonl").write_text(
        "{}", encoding="utf-8"
    )
    (root / "ccr.sqlite").write_bytes(b"sqlite")

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is False
    assert any(finding["kind"] == "release-generated-artifact" for finding in report["findings"])


def test_release_audit_fails_on_secret_assignment_and_pem(tmp_path):
    root = _clean_release_root(tmp_path)
    (root / "credentials.txt").write_text(
        "api_key = " + '"abcdefghijklmnopqrstuvwxyz"\n',
        encoding="utf-8",
    )
    (root / "private.pem").write_text(
        "-----BEGIN " + "PRIVATE KEY" + "-----\nabc\n-----END " + "PRIVATE KEY" + "-----\n",
        encoding="utf-8",
    )

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is False
    kinds = {finding["kind"] for finding in report["findings"]}
    assert "release-secret-assignment" in kinds
    assert "release-pem-secret" in kinds


def test_release_audit_allows_harmless_secret_policy_text(tmp_path):
    root = _clean_release_root(tmp_path)
    (root / "SECURITY.md").write_text(
        "Do not use PyPI username/password/API-token secrets.", encoding="utf-8"
    )

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is True


def test_release_audit_scans_distribution_archives(tmp_path):
    root = _clean_release_root(tmp_path)
    _write_wheel(
        root / "dist" / "bad-1.0.0-py3-none-any.whl",
        {"bad/METADATA": "leak " + "C:" + "\\Users\\local\\file"},
    )
    _write_sdist(
        root / "dist" / "bad-1.0.0.tar.gz",
        {"bad-1.0.0/examples/phase_formation/phase/result.json": "{}"},
    )

    report = audit_release(root, dist=root / "dist")

    assert report["ok"] is False
    kinds = {finding["kind"] for finding in report["findings"]}
    assert "release-local-path" in kinds
    assert "release-archive-artifact" in kinds


def test_release_audit_cli_returns_policy_failure_for_blockers(tmp_path, capsys):
    root = _clean_release_root(tmp_path)
    (root / "README.md").write_text(
        "password = " + '"abcdefghijklmnopqrstuvwxyz"', encoding="utf-8"
    )

    exit_code = main(["--root", str(root), "audit", "release", "--dist", "dist", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["blocking_finding_count"] > 0


def _clean_release_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("clean release text", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "module.py").write_text(
        "# SPDX-License-Identifier: Apache-2.0\n", encoding="utf-8"
    )
    dist = root / "dist"
    dist.mkdir()
    _write_wheel(
        dist / "clean-1.0.0-py3-none-any.whl",
        {"clean-1.0.0.dist-info/METADATA": "Name: clean\nVersion: 1.0.0\n"},
    )
    _write_sdist(
        dist / "clean-1.0.0.tar.gz",
        {"clean-1.0.0/PKG-INFO": "Name: clean\nVersion: 1.0.0\n"},
    )
    return root


def _write_wheel(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)


def _write_sdist(path: Path, members: dict[str, str]) -> None:
    with tarfile.open(path, "w:gz") as archive:
        for name, text in members.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
