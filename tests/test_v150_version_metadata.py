from __future__ import annotations

from importlib.metadata import version

import ccr
from tests.conftest import REPO_ROOT


def test_source_version_metadata_is_v150() -> None:
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    assert ccr.__version__ == "1.5.0"
    assert version("collective-capability-runtime") == "1.5.0"
    assert 'version = "1.5.0"' in pyproject
    assert "## 1.5.0 - 2026-07-04" in changelog


def test_release_docs_preserve_operator_gated_publication() -> None:
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    github_action = (REPO_ROOT / "docs" / "github-action.md").read_text(encoding="utf-8")

    assert (
        "Do not create releases, tags, or PyPI uploads unless the operator explicitly asks."
        in agents
    )
    assert (
        "does not create releases, push tags, upload to PyPI, or dispatch providers"
        in github_action
    )
