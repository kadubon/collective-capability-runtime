from __future__ import annotations

import json
import shutil
import subprocess
import sys

from tests.conftest import REPO_ROOT, cli_env


def run_module(*args: str, cwd=REPO_ROOT):
    return subprocess.run(
        [sys.executable, "-m", "ccr", *args],
        capture_output=True,
        check=False,
        cwd=cwd,
        env=cli_env(),
        text=True,
    )


def test_audit_repo_cli_detects_no_blocking_findings():
    result = run_module("--root", str(REPO_ROOT), "audit", "repo", "--json")

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["blocking_finding_count"] == 0


def test_phase_form_cli_on_example_never_claims_real_asi(tmp_path):
    runtime = tmp_path / "phase_formation"
    shutil.copytree(REPO_ROOT / "examples" / "phase_formation", runtime)

    result = run_module(
        "--root",
        str(runtime),
        "phase",
        "form",
        "--profile",
        "development",
        "--json",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    certificate = payload["certificate"]
    assert certificate["proves_real_asi"] is False
    assert certificate["settled"] is False
    assert payload["observation"]["executed_path_count"] == 0


def test_phase_form_creates_repair_tasks_deterministically(tmp_path):
    result = run_module("--root", str(tmp_path), "init")
    assert result.returncode == 0, result.stdout + result.stderr

    first = run_module(
        "--root",
        str(tmp_path),
        "phase",
        "form",
        "--profile",
        "development",
        "--json",
    )
    second = run_module(
        "--root",
        str(tmp_path),
        "phase",
        "form",
        "--profile",
        "development",
        "--json",
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["repair_tasks"]
    assert first_payload["repair_tasks"] == second_payload["repair_tasks"]
