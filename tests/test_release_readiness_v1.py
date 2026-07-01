from __future__ import annotations

import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

from ccr.audit.repo import (
    CCR_PIP_INSTALL,
    CI_WORKFLOW,
    FIRST_TIME_AGENT_MARKERS,
    PIC_COMPAT_EXAMPLES,
    PIC_PIP_INSTALL,
    PUBLISH_WORKFLOW,
    audit_repository,
)
from tests.conftest import REPO_ROOT, cli_env


def test_audit_fails_when_pic_route_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(PIC_PIP_INSTALL, ""),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(
        finding["blocking"] and finding["location"] == "README.md" for finding in report["findings"]
    )


def test_audit_fails_when_trusted_publishing_id_token_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / PUBLISH_WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("id-token: write", "id-token: read"),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["location"] == PUBLISH_WORKFLOW for finding in report["findings"])


def test_audit_fails_when_ci_static_gate_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / CI_WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("uv run mypy src", "uv run pytest -q"),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["location"] == CI_WORKFLOW for finding in report["findings"])


def test_audit_fails_when_release_audit_workflow_gate_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / CI_WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "uv run ccr audit release --dist dist --json",
            "uvx twine check dist/*",
        ),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["location"] == CI_WORKFLOW for finding in report["findings"])


def test_audit_fails_when_ci_pic_compatibility_gate_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / CI_WORKFLOW
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("kadubon/percolation-inversion-compiler", ""),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["location"] == CI_WORKFLOW for finding in report["findings"])


def test_audit_fails_when_publish_workflow_uses_pypi_secret(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / PUBLISH_WORKFLOW
    forbidden_secret_ref = "${{ " + "secrets" + "." + "PYPI" + "_API" + "_TOKEN" + " }}"
    workflow.write_text(
        workflow.read_text(encoding="utf-8")
        + f"\n# invalid token path for audit coverage\npassword: {forbidden_secret_ref}\n",
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["kind"] == "publish-secret-required" for finding in report["findings"])


def test_audit_fails_when_publish_workflow_checks_out_pic_before_release_audit(tmp_path):
    repo = _copy_repo(tmp_path)
    workflow = repo / PUBLISH_WORKFLOW
    early_pic_checkout = (
        "      - run: uv sync --all-extras\n"
        "      - uses: actions/checkout@v4\n"
        "        with:\n"
        "          repository: kadubon/percolation-inversion-compiler\n"
        "          path: .tmp/pic-root\n"
    )
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace(
            "      - run: uv sync --all-extras\n",
            early_pic_checkout,
            1,
        ),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(
        finding["kind"] == "publish-pic-checkout-before-release-audit"
        for finding in report["findings"]
    )


def test_audit_fails_when_generated_phase_artifacts_are_present(tmp_path):
    repo = _copy_repo(tmp_path)
    generated = repo / "examples" / "phase_formation" / "ccr.sqlite"
    generated.write_bytes(b"generated")

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["kind"] == "generated-example-artifact" for finding in report["findings"])


def test_audit_fails_when_pic_compat_example_is_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    (repo / PIC_COMPAT_EXAMPLES[0]).unlink()

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(
        finding["blocking"] and finding["location"] == PIC_COMPAT_EXAMPLES[0]
        for finding in report["findings"]
    )


def test_audit_fails_when_pic_audit_docs_are_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    interop = repo / "INTEROP_PIC.md"
    interop.write_text(
        interop.read_text(encoding="utf-8").replace("ccr audit pic", "ccr audit provider"),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(
        finding["blocking"] and finding["location"] == "INTEROP_PIC.md"
        for finding in report["findings"]
    )


def test_audit_fails_when_first_time_agent_docs_are_missing(tmp_path):
    repo = _copy_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(FIRST_TIME_AGENT_MARKERS[0], ""),
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(
        finding["blocking"] and finding["location"] == "README.md" for finding in report["findings"]
    )


def test_audit_fails_when_public_docs_contain_local_path(tmp_path):
    repo = _copy_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n" + "C:" + "\\Users\\local\\private\n",
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["kind"] == "public-local-path-leak" for finding in report["findings"])


def test_audit_fails_when_public_docs_contain_local_username(tmp_path):
    repo = _copy_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n" + "199" + "1m" + "\n",
        encoding="utf-8",
    )

    report = audit_repository(repo)

    assert report["ok"] is False
    assert any(finding["kind"] == "public-local-path-leak" for finding in report["findings"])


def test_package_build_metadata_is_v1_distribution_ready(tmp_path):
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(dist_dir)],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=cli_env(),
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    audit = subprocess.run(
        ["uv", "run", "ccr", "audit", "release", "--dist", str(dist_dir), "--json"],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=cli_env(),
        text=True,
    )
    assert audit.returncode == 0, audit.stdout + audit.stderr
    wheel = next(dist_dir.glob("collective_capability_runtime-1.4.0-*.whl"))
    sdist = next(dist_dir.glob("collective_capability_runtime-1.4.0.tar.gz"))
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(name for name in archive.namelist() if name.endswith("METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
    with tarfile.open(sdist, "r:gz") as archive:
        pkg_info_name = next(name for name in archive.getnames() if name.endswith("PKG-INFO"))
        pkg_info_file = archive.extractfile(pkg_info_name)
        assert pkg_info_file is not None
        pkg_info = pkg_info_file.read().decode("utf-8")

    for text in [metadata, pkg_info]:
        assert "Name: collective-capability-runtime" in text
        assert "Version: 1.4.0" in text
        assert CCR_PIP_INSTALL in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _copy_repo(tmp_path: Path) -> Path:
    destination = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT,
        destination,
        ignore=shutil.ignore_patterns(
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "__pycache__",
            "dist",
            "build",
            "*.egg-info",
            "*.pyc",
            "*.sqlite",
            "*.sqlite-shm",
            "*.sqlite-wal",
        ),
    )
    return destination
