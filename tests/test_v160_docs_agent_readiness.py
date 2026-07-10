from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from ccr import __version__
from ccr.audit.repo import audit_repository
from ccr.cli import main
from tests.conftest import REPO_ROOT


def test_task_oriented_docs_and_manifest_routes_exist() -> None:
    required = {
        "README.md": [
            "## Five-Minute Start",
            "## Choose A Workflow",
            "## Important Output Fields",
            "## State And External Effects",
        ],
        "docs/README.md": ["## Start Locally", "## Choose A Task", "## Safety Boundaries"],
        "docs/getting-started.md": [
            "## Install And Inspect",
            "## Create A Local Mission",
            "## Route Remaining Work",
            "## Choose The Next Guide",
        ],
        "examples/collective_runtime/README.md": [
            "effective_support_count",
            "resource-matched",
            "not a general capability benchmark",
        ],
    }
    for relative, markers in required.items():
        text = _read(relative)
        for marker in markers:
            assert marker in text, f"{relative} missing {marker}"

    manifest = json.loads(_read("agent-manifest.json"))
    layout = manifest["repository_layout"]
    for group in ("docs", "schemas"):
        for relative in layout[group]:
            assert (REPO_ROOT / relative).exists(), relative


def test_all_relative_markdown_links_resolve() -> None:
    files = [REPO_ROOT / "README.md", *(REPO_ROOT / "docs").glob("*.md")]
    missing: list[tuple[str, str]] = []
    for path in files:
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            relative = target.split("#", 1)[0]
            if not relative or "://" in relative or relative.startswith("mailto:"):
                continue
            if not (path.parent / relative).resolve().exists():
                missing.append((str(path.relative_to(REPO_ROOT)), target))
    assert missing == []


def test_agent_explain_advertises_v160_runtime(tmp_path: Path, capsys: Any) -> None:
    report = _run(["--root", str(tmp_path), "agent", "explain", "--json"], capsys)
    assert report["docs"]["collective_workcells"] == "docs/collective-workcells.md"
    assert report["docs"]["distributed_runtime"] == "docs/distributed-runtime.md"
    assert report["docs"]["measurement_protocol"] == "docs/measurement-protocol.md"
    assert "ccr storage doctor --json" in report["safe_next_commands"]
    assert "collective_coordination" in report["v1_6_runtime"]
    assert report["safe_boundaries"]["unknown_coordinates_do_not_contribute_progress"]
    assert report["safe_boundaries"]["physical_outcome_proven_is_always_false"]
    assert (
        "ccr workcell create/submit/advance/integrate"
        in report["local_mutation_boundary"]["explicit_local_writes"]
    )


def test_collective_runtime_fixture_is_executable(tmp_path: Path, capsys: Any) -> None:
    root_args = ["--root", str(tmp_path)]
    _run(
        [
            *root_args,
            "workcell",
            "create",
            "--template",
            "packet-distillation",
            "--name",
            "review-a",
            "--json",
        ],
        capsys,
    )
    for proposal in ("proposal-a.json", "proposal-b.json"):
        _run(
            [
                *root_args,
                "workcell",
                "submit",
                "--workcell",
                "review-a",
                "--file",
                str(REPO_ROOT / "examples" / "collective_runtime" / proposal),
                "--json",
            ],
            capsys,
        )
    for stage in ("reveal", "critique", "revision", "verification"):
        _run(
            [
                *root_args,
                "workcell",
                "advance",
                "--workcell",
                "review-a",
                "--to",
                stage,
                "--json",
            ],
            capsys,
        )
    integrated = _run(
        [
            *root_args,
            "workcell",
            "integrate",
            "--workcell",
            "review-a",
            "--strategy",
            "residual-preserving",
            "--json",
        ],
        capsys,
    )
    assert integrated["protocol_complete"] is True
    assert integrated["claims"][0]["effective_support_count"] == 1
    assert integrated["settled"] is False

    fixture = REPO_ROOT / "examples" / "collective_runtime"
    registered = _run(
        [
            *root_args,
            "experiment",
            "register",
            "--suite",
            "study-a",
            "--manifest",
            str(fixture / "experiment-manifest.json"),
            "--json",
        ],
        capsys,
    )
    assert registered["ok"] is True
    for label, name in (("baseline", "baseline.json"), ("collective", "collective.json")):
        ingested = _run(
            [
                *root_args,
                "experiment",
                "ingest",
                "--suite",
                "study-a",
                "--label",
                label,
                "--file",
                str(fixture / name),
                "--json",
            ],
            capsys,
        )
        assert ingested["ok"] is True
    compared = _run(
        [
            *root_args,
            "experiment",
            "compare",
            "--baseline",
            str(fixture / "baseline.json"),
            "--candidate",
            str(fixture / "collective.json"),
            "--json",
        ],
        capsys,
    )
    assert compared["resource_matched"] is True
    assert compared["acceleration_claim_admissible"] is True


def test_public_metadata_is_searchable_and_versioned() -> None:
    pyproject = _read("pyproject.toml")
    changelog = _read("CHANGELOG.md")
    init = _read("src/ccr/__init__.py")
    for keyword in (
        "collective-intelligence",
        "multi-agent-systems",
        "distributed-ai",
        "postgresql",
        "task-queue",
        "oidc",
        "dpop",
    ):
        assert f'"{keyword}"' in pyproject
    assert f'version = "{__version__}"' in pyproject
    assert f'__version__ = "{__version__}"' in init
    assert f"## {__version__} -" in changelog


def test_repository_audit_rejects_broken_doc_link(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT,
        repo,
        ignore=shutil.ignore_patterns(
            ".git",
            ".venv",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "__pycache__",
            "*.pyc",
            "*.sqlite*",
        ),
    )
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n[missing](docs/not-present.md)\n",
        encoding="utf-8",
    )
    report = audit_repository(repo)
    assert any(finding["kind"] == "broken-doc-link" for finding in report["findings"])


def test_ccr_audit_action_uses_checkout_and_does_not_publish() -> None:
    action = _read(".github/actions/ccr-audit/action.yml")
    assert "uv sync --all-extras" in action
    assert "uv run ccr audit repo --json" in action
    assert "python -m pip install -e ." in action
    for forbidden in (
        "twine upload",
        "git tag",
        "gh release",
        "pip install collective-capability-runtime",
        "pypa/gh-action-pypi-publish",
    ):
        assert forbidden not in action


def _run(args: list[str], capsys: Any) -> dict[str, Any]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")
