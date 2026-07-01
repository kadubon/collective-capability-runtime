# SPDX-License-Identifier: Apache-2.0
"""Repository self-audit for commercial readiness and safety invariants."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.constants import NON_CLAIMS
from ccr.ids import stable_id
from ccr.residuals.model import build_residual
from ccr.time import now_iso

REQUIRED_SCHEMA_FILES = [
    "packet.schema.json",
    "task.schema.json",
    "agent-manifest.schema.json",
    "blackboard-event.schema.json",
    "residual.schema.json",
    "verifier-report.schema.json",
    "phase-report.schema.json",
    "phase-state.schema.json",
    "effective-graph.schema.json",
    "phase-observation.schema.json",
    "asi-proxy-threshold.schema.json",
    "phase-certificate-candidate.schema.json",
    "baseline.schema.json",
    "provider.schema.json",
    "audit-report.schema.json",
    "trc-operation-plan.schema.json",
]

DOC_ROUTE_FILES = [
    "README.md",
    "SPEC.md",
    "FORMAL_MODEL.md",
    "INTEROP_PIC.md",
    "SECURITY.md",
    "AGENTS.md",
    "GOVERNANCE.md",
    "CONTRIBUTING.md",
    "AUDIT.md",
    "examples/phase_formation/README.md",
    "examples/pic_interop/README.md",
]

PIC_REPOSITORY_ROUTE = (
    "[kadubon/percolation-inversion-compiler]"
    "(https://github.com/kadubon/percolation-inversion-compiler)"
)
PIC_PIP_INSTALL = "python -m pip install percolation-inversion-compiler"
CCR_PIP_INSTALL = "python -m pip install collective-capability-runtime"
PUBLISH_WORKFLOW = ".github/workflows/workflow.yml"
CI_WORKFLOW = ".github/workflows/ci.yml"
REQUIRED_RELEASE_GATE_MARKERS = [
    "uv run ruff format --check .",
    "uv run ruff check .",
    "uv run mypy src",
    "uv run python -m compileall -q src tests",
    "uv run pytest",
    "uv run ccr schema validate --kind packet --file examples/minimal/packet.json",
    "uv run ccr schema validate --kind task --file examples/minimal/task.json",
    "uv run ccr schema validate --kind baseline --file examples/phase_formation/baseline.json",
    "uv run ccr schema validate --kind asi-proxy-threshold --file "
    "examples/phase_formation/threshold.json",
    "uv run ccr schema validate --kind trc-operation-plan --file "
    "examples/asi_proxy_benchmark_bundle/trc_operation_plan.json",
    "uv run ccr --root /tmp/ccr-phase-formation phase form --profile development --json",
    "uv run ccr audit repo --json",
    "uv build",
    "uv run ccr audit release --dist dist --json",
    "uvx twine check dist/*",
]
REQUIRED_PIC_CI_MARKERS = [
    "kadubon/percolation-inversion-compiler",
    "uv run ccr audit pic --pic-root .tmp/pic-root --json",
]
PIC_COMPAT_EXAMPLES = [
    "examples/pic_interop/pic_v050_agent_check_report.json",
    "examples/pic_interop/pic_v050_phase_plan_report.json",
    "examples/pic_interop/pic_v050_collective_certificate_candidate.json",
    "examples/pic_interop/pic_v050_provider_missing_report.json",
]
PIC_COMPAT_DOCS = [
    "README.md",
    "SPEC.md",
    "INTEROP_PIC.md",
    "SECURITY.md",
    "AGENTS.md",
]
FIRST_TIME_AGENT_DOC_FILES = [
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
FIRST_TIME_AGENT_MARKERS = [
    "First-time agent guide",
    "Purpose:",
    "First commands:",
    "Safe boundary:",
    "Expected outputs:",
    "Failure/residual handling:",
    "Provider import:",
    "Phase formation cycle:",
    "What not to claim:",
]
PUBLIC_RELEASE_DOC_FILES = [
    "README.md",
    "AGENTS.md",
    "SPEC.md",
    "SECURITY.md",
    "INTEROP_PIC.md",
    "AUDIT.md",
    "examples/pic_interop/README.md",
]
PUBLIC_DOC_FORBIDDEN_MARKERS = [
    "C:" + "\\Users",
    "199" + "1m",
]


def audit_repository(root: Path) -> dict[str, Any]:
    """Audit repository files without mutating state."""

    findings: list[dict[str, Any]] = []
    _check_file(
        root,
        findings,
        "README.md",
        must_contain=["protocol-relative ASI-proxy", CCR_PIP_INSTALL],
        missing_content_blocks=True,
    )
    _check_file(
        root,
        findings,
        "pyproject.toml",
        must_contain=[
            'name = "collective-capability-runtime"',
            'version = "1.2.0"',
            "Apache-2.0",
            "Development Status :: 5 - Production/Stable",
            "ccr =",
        ],
        missing_content_blocks=True,
    )
    _check_file(
        root,
        findings,
        CI_WORKFLOW,
        must_contain=[*REQUIRED_RELEASE_GATE_MARKERS, *REQUIRED_PIC_CI_MARKERS],
        missing_content_blocks=True,
    )
    _check_file(
        root,
        findings,
        PUBLISH_WORKFLOW,
        must_contain=[
            "release:",
            "published",
            "id-token: write",
            "pypa/gh-action-pypi-publish@release/v1",
            "uv build",
            "uvx twine check dist/*",
            "https://pypi.org/p/collective-capability-runtime",
            *REQUIRED_RELEASE_GATE_MARKERS,
            *REQUIRED_PIC_CI_MARKERS,
        ],
        missing_content_blocks=True,
    )
    _check_file(root, findings, "SECURITY.md", must_contain=["HTTP provider", "safe commands"])
    _check_file(root, findings, "AGENTS.md", must_contain=["phase form", "safe commands"])
    for schema in REQUIRED_SCHEMA_FILES:
        _check_file(
            root,
            findings,
            f"schemas/{schema}",
            must_contain=["$schema"],
            missing_content_blocks=True,
        )
    _check_pic_doc_routes(root, findings)
    _check_pic_compatibility_surface(root, findings)
    _check_first_time_agent_docs(root, findings)
    _check_public_release_hygiene(root, findings)
    _check_publish_workflow_secrets(root, findings)
    _check_publish_workflow_order(root, findings)
    _check_generated_example_artifacts(root, findings)
    _check_non_claims(root, findings)
    _check_spdx(root, findings)
    _check_cli_surface(root, findings)
    blocking = [finding for finding in findings if finding["blocking"]]
    return {
        "accepted": not blocking,
        "blocking_finding_count": len(blocking),
        "created_at": now_iso(),
        "finding_count": len(findings),
        "findings": findings,
        "ok": not blocking,
        "report_id": stable_id("audit-report", [finding["finding_id"] for finding in findings]),
        "schema_version": "ccr.audit_report.v1",
        "settled": False,
    }


def _check_file(
    root: Path,
    findings: list[dict[str, Any]],
    relative: str,
    *,
    must_contain: list[str],
    missing_content_blocks: bool = False,
) -> None:
    path = root / relative
    if not path.exists():
        findings.append(_finding("missing-file", relative, "high", True, f"{relative} is missing."))
        return
    text = path.read_text(encoding="utf-8")
    for needle in must_contain:
        if needle not in text:
            findings.append(
                _finding(
                    "missing-content",
                    relative,
                    "medium",
                    missing_content_blocks,
                    f"{relative} does not contain required text: {needle}",
                )
            )


def _check_pic_doc_routes(root: Path, findings: list[dict[str, Any]]) -> None:
    for relative in DOC_ROUTE_FILES:
        _check_file(
            root,
            findings,
            relative,
            must_contain=[PIC_REPOSITORY_ROUTE, PIC_PIP_INSTALL],
            missing_content_blocks=True,
        )


def _check_pic_compatibility_surface(root: Path, findings: list[dict[str, Any]]) -> None:
    _check_file(
        root,
        findings,
        "src/ccr/audit/pic.py",
        must_contain=[
            "audit_pic_compatibility",
            "EXPECTED_PIC_COMMANDS",
            "SUPPORTED_PIC_IMPORT_FIELDS",
        ],
        missing_content_blocks=True,
    )
    for relative in PIC_COMPAT_DOCS:
        _check_file(
            root,
            findings,
            relative,
            must_contain=[
                "ccr audit pic",
                "ccr provider health --provider pic --json",
            ],
            missing_content_blocks=True,
        )
    _check_file(
        root,
        findings,
        "INTEROP_PIC.md",
        must_contain=["PIC v0.5.0/v0.6.0 compatibility matrix"],
        missing_content_blocks=True,
    )
    for relative in PIC_COMPAT_EXAMPLES:
        _check_file(
            root,
            findings,
            relative,
            must_contain=["settled", "safe_commands"],
            missing_content_blocks=True,
        )


def _check_first_time_agent_docs(root: Path, findings: list[dict[str, Any]]) -> None:
    for relative in FIRST_TIME_AGENT_DOC_FILES:
        _check_file(
            root,
            findings,
            relative,
            must_contain=FIRST_TIME_AGENT_MARKERS,
            missing_content_blocks=True,
        )


def _check_public_release_hygiene(root: Path, findings: list[dict[str, Any]]) -> None:
    for relative in PUBLIC_RELEASE_DOC_FILES:
        _check_file(
            root,
            findings,
            relative,
            must_contain=["<PIC_ROOT>"],
            missing_content_blocks=True,
        )
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in PUBLIC_DOC_FORBIDDEN_MARKERS:
            if marker in text:
                findings.append(
                    _finding(
                        "public-local-path-leak",
                        relative,
                        "critical",
                        True,
                        f"{relative} contains user-specific local release text.",
                    )
                )
    _check_file(
        root,
        findings,
        "src/ccr/audit/release.py",
        must_contain=["audit_release", "LOCAL_PATH_RE", "SECRET_ASSIGNMENT_RE"],
        missing_content_blocks=True,
    )


def _check_publish_workflow_secrets(root: Path, findings: list[dict[str, Any]]) -> None:
    path = root / PUBLISH_WORKFLOW
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    forbidden = [
        "password:",
        "username:",
        "secrets." + "PYPI",
        "PYPI" + "_TOKEN",
        "__token__",
        "api-token",
    ]
    for needle in forbidden:
        if needle in text:
            findings.append(
                _finding(
                    "publish-secret-required",
                    PUBLISH_WORKFLOW,
                    "high",
                    True,
                    f"Publish workflow must use trusted publishing, not {needle}.",
                )
            )


def _check_publish_workflow_order(root: Path, findings: list[dict[str, Any]]) -> None:
    path = root / PUBLISH_WORKFLOW
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    pic_checkout_index = text.find("path: .tmp/pic-root")
    release_audit_index = text.find("uv run ccr audit release --dist dist --json")
    if (
        pic_checkout_index != -1
        and release_audit_index != -1
        and pic_checkout_index < release_audit_index
    ):
        findings.append(
            _finding(
                "publish-pic-checkout-before-release-audit",
                PUBLISH_WORKFLOW,
                "high",
                True,
                "Publish workflow checks out PIC before the CCR release audit, which can "
                "contaminate the source-tree hygiene scan.",
            )
        )


def _check_generated_example_artifacts(root: Path, findings: list[dict[str, Any]]) -> None:
    generated_paths = [
        root / "examples" / "phase_formation" / "ccr.sqlite",
        root / "examples" / "phase_formation" / "blackboard",
        root / "examples" / "phase_formation" / "phase",
    ]
    for path in generated_paths:
        if path.exists():
            findings.append(
                _finding(
                    "generated-example-artifact",
                    str(path.relative_to(root)),
                    "medium",
                    True,
                    "Generated phase formation runtime artifact must not be shipped as source.",
                )
            )


def _check_non_claims(root: Path, findings: list[dict[str, Any]]) -> None:
    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    constants = (root / "src" / "ccr" / "constants.py").read_text(encoding="utf-8")
    for non_claim in NON_CLAIMS[:6]:
        phrase = non_claim.removeprefix("CCR ").rstrip(".")
        if phrase not in readme and phrase not in constants:
            findings.append(
                _finding(
                    "missing-non-claim",
                    "README.md",
                    "high",
                    True,
                    f"Non-claim is not visible: {non_claim}",
                )
            )


def _check_spdx(root: Path, findings: list[dict[str, Any]]) -> None:
    for path in sorted((root / "src" / "ccr").rglob("*.py")):
        if path.name == "__init__.py" and path.read_text(encoding="utf-8").strip() == "":
            continue
        text = path.read_text(encoding="utf-8")
        if "SPDX-License-Identifier: Apache-2.0" not in text:
            findings.append(
                _finding(
                    "missing-spdx",
                    str(path.relative_to(root)),
                    "low",
                    False,
                    "Python source file lacks SPDX header.",
                )
            )


def _check_cli_surface(root: Path, findings: list[dict[str, Any]]) -> None:
    cli = (root / "src" / "ccr" / "cli.py").read_text(encoding="utf-8")
    required = [
        'sub.add_parser("audit"',
        'sub.add_parser("provider"',
        "cmd_phase_graph",
        "cmd_phase_observe",
        "cmd_phase_threshold",
        "cmd_phase_compare",
        "cmd_phase_form",
        "cmd_phase_certify",
        "cmd_provider_execute",
        "cmd_audit_pic",
        "cmd_audit_release",
        'audit_sub.add_parser("pic"',
        'audit_sub.add_parser("release"',
    ]
    for needle in required:
        if needle not in cli:
            findings.append(
                _finding(
                    "missing-cli-surface",
                    "src/ccr/cli.py",
                    "medium",
                    True,
                    f"CLI implementation missing marker: {needle}",
                )
            )


def _finding(
    kind: str, location: str, severity: str, blocking: bool, description: str
) -> dict[str, Any]:
    finding_id = stable_id("finding", kind, location, description)
    residual = build_residual(
        kind="missing_evidence" if kind.startswith("missing") else "other",
        description=description,
        blocking=blocking,
        object_type="runtime",
        object_id=location,
        severity=severity,
        refs=[location],
        source="ccr.audit.repo",
        repair_hint="Address the repository audit finding and rerun ccr audit repo --json.",
        extensions={"finding_id": finding_id, "finding_kind": kind},
    )
    return {
        "blocking": blocking,
        "description": description,
        "finding_id": finding_id,
        "kind": kind,
        "location": location,
        "residual_ready": residual,
        "severity": severity,
    }
