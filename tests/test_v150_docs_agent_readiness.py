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


def _read(relative: str) -> str:
    return (Path(REPO_ROOT) / relative).read_text(encoding="utf-8")
