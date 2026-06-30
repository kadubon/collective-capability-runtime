from __future__ import annotations

import json
import subprocess
import sys

from tests.conftest import REPO_ROOT, cli_env


def run_cli(*args: str, root):
    return subprocess.run(
        [sys.executable, "-m", "ccr", "--root", str(root), *args],
        capture_output=True,
        check=False,
        cwd=REPO_ROOT,
        env=cli_env(),
        text=True,
    )


def test_cli_smoke_init_and_agent_explain(tmp_path):
    init = run_cli("init", root=tmp_path)
    assert init.returncode == 0, init.stderr + init.stdout
    explain = run_cli("agent", "explain", "--json", root=tmp_path)
    assert explain.returncode == 0
    payload = json.loads(explain.stdout)
    assert payload["ok"] is True
    assert payload["default_mode"] == "dry_run"


def test_cli_schema_validate_packet(tmp_path):
    run_cli("init", root=tmp_path)
    result = run_cli(
        "schema",
        "validate",
        "--kind",
        "packet",
        "--file",
        str(REPO_ROOT / "examples" / "minimal" / "packet.json"),
        root=tmp_path,
    )
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["ok"] is True
