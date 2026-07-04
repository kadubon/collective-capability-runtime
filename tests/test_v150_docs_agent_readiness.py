from __future__ import annotations

from pathlib import Path

from tests.conftest import REPO_ROOT

FIRST_TIME_DOCS = [
    "README.md",
    "AGENTS.md",
    "SPEC.md",
    "SECURITY.md",
    "INTEROP_PIC.md",
    "FORMAL_MODEL.md",
    "AUDIT.md",
    "examples/phase_formation/README.md",
    "examples/pic_interop/README.md",
]


def test_first_time_agent_docs_include_p2_safe_commands() -> None:
    required = [
        "First-time agent guide",
        "Purpose:",
        "First commands:",
        "Safe boundary:",
        "Expected outputs:",
        "Failure/residual handling:",
        "P2 safe commands:",
        "Provider import:",
        "Phase formation cycle:",
        "What not to claim:",
    ]
    for relative in FIRST_TIME_DOCS:
        text = _read(relative)
        for marker in required:
            assert marker in text, f"{relative} missing {marker}"


def test_p2_docs_name_runtime_surfaces_and_non_claims() -> None:
    text = _read("docs/p2-runtime-surfaces.md")
    for marker in [
        "residual market",
        "runtime-wide",
        "static workbench",
        "operation replay",
        "provider registry",
        "physical_outcome_proven=false",
        "no release, tag, PyPI upload, or provider dispatch",
    ]:
        assert marker in text


def test_p2_extended_docs_explain_safe_boundaries() -> None:
    docs = {
        "docs/operation-gate.md": [
            "Operation replay is not dispatch",
            "Observation verification is not physical outcome proof",
            "physical_outcome_proven=false",
        ],
        "docs/real-world-impact.md": [
            "Replay is not dispatch",
            "verification is not physical outcome proof",
            "provider registry validation as static metadata review",
        ],
        "docs/cross-repo-loop-conformance.md": [
            "Missing parity fields become residual-ready evidence",
            "parity is evidence, not settlement",
        ],
        "docs/performance.md": [
            "bounded local operations",
            "cache/index proof claims",
            "JSON artifacts remain source of truth",
        ],
    }
    for relative, markers in docs.items():
        text = _read(relative)
        for marker in markers:
            assert marker in text, f"{relative} missing {marker}"


def test_ccr_audit_action_uses_checkout_and_does_not_publish() -> None:
    action = _read(".github/actions/ccr-audit/action.yml")
    assert "uv sync --all-extras" in action
    assert "uv run ccr audit repo --json" in action
    assert "python -m pip install -e ." in action
    assert (
        "workbench report --mission mission:quickstart --format json "
        "--out .tmp/ccr-action-smoke/workbench.json --json" not in action
    )
    for forbidden in [
        "twine upload",
        "git tag",
        "gh release",
        "pip install collective-capability-runtime",
        "pypa/gh-action-pypi-publish",
    ]:
        assert forbidden not in action


def _read(relative: str) -> str:
    return (Path(REPO_ROOT) / relative).read_text(encoding="utf-8")
