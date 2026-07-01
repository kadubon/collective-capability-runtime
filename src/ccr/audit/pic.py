# SPDX-License-Identifier: Apache-2.0
"""PIC compatibility audit for the optional provider boundary."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import re
import shutil
from pathlib import Path
from typing import Any

from ccr.errors import CCRMissingError
from ccr.ids import stable_id
from ccr.providers.pic import PicProvider
from ccr.residuals.model import build_residual
from ccr.time import now_iso

EXPECTED_PIC_COMMANDS = [
    "pic agent check --compact",
    "pic packet inspect",
    "pic phase plan --compact",
    "pic phase acceleration-report",
    "pic runtime collective-certify",
    "pic token admissibility",
    "pic token extract-pipeline",
    "pic trc trace-normalize",
    "pic trc trace-check",
    "pic trc trace-to-packet",
    "pic trc operation-gate",
    "pic mcp invocation-preflight",
    "pic a2a handoff-check",
    "pic sqot protocol-integrity",
    "pic bit mec-frontier",
]

SUPPORTED_PIC_IMPORT_FIELDS = [
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
    "capital_witnesses",
    "certified_acceleration_candidate",
    "certified_acceleration_interval_candidate",
    "ccr_tasks",
    "mcp_tool_gate",
    "a2a_agent_gate",
    "operation_residuals",
    "token_id",
    "candidate_token",
]

PIC_ROUTE_TEXT = "python -m pip install percolation-inversion-compiler"


def default_pic_root_candidates(ccr_root: Path) -> list[Path]:
    """Return deterministic PIC source-root candidates for local compatibility checks."""

    candidates = [
        Path.home() / "percolation-inversion-compiler",
        ccr_root.parent / "percolation-inversion-compiler",
    ]
    seen: set[str] = set()
    unique: list[Path] = []
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def resolve_pic_root(ccr_root: Path, explicit_pic_root: Path | None = None) -> Path:
    """Resolve a PIC root or raise a CLI-ready missing-path error."""

    if explicit_pic_root is not None:
        pic_root = explicit_pic_root.expanduser()
        if not pic_root.exists():
            raise CCRMissingError(
                f"PIC root does not exist: {pic_root}",
                {
                    "error": "pic root missing",
                    "ok": False,
                    "pic_root": str(pic_root),
                    "schema_version": "ccr.pic_compat_audit.v1",
                },
            )
        return pic_root
    searched = default_pic_root_candidates(ccr_root)
    for candidate in searched:
        if candidate.exists():
            return candidate
    raise CCRMissingError(
        "PIC root was not found in default search candidates.",
        {
            "error": "pic root missing",
            "ok": False,
            "searched": [str(path) for path in searched],
            "schema_version": "ccr.pic_compat_audit.v1",
        },
    )


def audit_pic_compatibility(ccr_root: Path, *, pic_root: Path | None = None) -> dict[str, Any]:
    """Audit the CCR/PIC operational compatibility boundary."""

    resolved_pic_root = resolve_pic_root(ccr_root, pic_root)
    findings: list[dict[str, Any]] = []
    pic_repo_version = _read_pyproject_version(resolved_pic_root / "pyproject.toml")
    package_version = _installed_distribution_version("percolation-inversion-compiler")
    pic_executable = shutil.which("pic")

    if package_version is None:
        findings.append(
            _finding(
                "provider_missing",
                "python-package:percolation-inversion-compiler",
                "medium",
                False,
                "PIC package is not installed in the active Python environment.",
                repair_hint=PIC_ROUTE_TEXT,
            )
        )
    if pic_executable is None:
        findings.append(
            _finding(
                "provider_missing",
                "cli:pic",
                "medium",
                False,
                "PIC CLI executable is not available on PATH.",
                repair_hint=PIC_ROUTE_TEXT,
            )
        )

    _check_pic_source_tree(resolved_pic_root, findings, pic_repo_version=pic_repo_version)
    _check_pic_repo_version(pic_repo_version, findings)
    _check_provider_mapping(findings)
    _check_non_claim_boundary(ccr_root, resolved_pic_root, findings)

    blocking = [finding for finding in findings if finding["blocking"]]
    return {
        "accepted": not blocking,
        "blocking_finding_count": len(blocking),
        "created_at": now_iso(),
        "expected_pic_commands": EXPECTED_PIC_COMMANDS,
        "finding_count": len(findings),
        "findings": findings,
        "installed_package_version": package_version,
        "ok": not blocking,
        "pic_cli": {"available": pic_executable is not None, "path": pic_executable},
        "pic_repo_version": pic_repo_version,
        "pic_root": str(resolved_pic_root),
        "report_id": stable_id(
            "pic-compat-audit",
            str(resolved_pic_root),
            pic_repo_version,
            package_version,
            [finding["finding_id"] for finding in findings],
        ),
        "schema_version": "ccr.audit_report.v1",
        "settled": False,
        "supported_import_fields": SUPPORTED_PIC_IMPORT_FIELDS,
    }


def _check_pic_source_tree(
    pic_root: Path,
    findings: list[dict[str, Any]],
    *,
    pic_repo_version: str | None,
) -> None:
    required_files = {
        "README.md": [
            "percolation-inversion-compiler",
            "pic agent check --compact",
            "pic phase plan --compact",
            "pic token admissibility",
            "safe_commands",
            "settled=false",
        ],
        "pyproject.toml": [
            'name = "percolation-inversion-compiler"',
            'pic = "percolation_inversion_compiler.cli:app"',
        ],
        "docs/porting.md": ["workflow_usable", "settled", "candidate-only"],
        "docs/phase-acceleration.md": [
            "phase_gap_vector",
            "bottlenecks",
            "cannot_promote_because",
            "settled_blockers",
        ],
        "docs/v050-audit.md": ["Package version: `0.5.0`", "safe_commands"],
        "examples/portability_conformance/phase_acceleration_plan.json": [
            "PhaseAccelerationPlan",
            "candidate_only_reasons",
            "cannot_promote_because",
            "settled_blockers",
        ],
    }
    if pic_repo_version is not None and pic_repo_version.startswith("0.6."):
        required_files.update(
            {
                "docs/v060-audit.md": ["Package version: `0.6.0`", "operation-readiness"],
                "docs/ccr-pic-roundtrip.md": ["CCR", "JSONL", "residual"],
                "docs/asi-proxy-acceleration.md": ["ASI-proxy", "TRC", "CCR"],
                "examples/asi_proxy_benchmark_bundle/trc_agent_trace.json": [
                    "authority_envelope",
                    "resource_ledger",
                    "tolerance_ledger",
                ],
            }
        )
    if pic_repo_version is not None and (
        pic_repo_version.startswith("0.8.") or pic_repo_version.startswith("0.9.")
    ):
        required_files.update(
            {
                "docs/asi-proxy-loop.md": [
                    "Token extraction is not settlement",
                    "safe commands are hints",
                ],
                "docs/agent-loop-protocol.md": ["CCR `loop next`", "non-mutating"],
                "docs/token-extraction.md": ["Token admissibility", "capital admission"],
                "docs/operation-gate.md": ["provider dispatch readiness", "physical outcome"],
                "docs/phase-acceleration-interval.md": [
                    "certified_acceleration_interval_candidate",
                    "proxy-only evidence",
                ],
                "docs/cross-repo-loop-conformance.md": ["PIC-TS", "CCR imports"],
                "examples/asi_proxy_loop_bundle/target.json": ["target:asi-proxy-loop-v090"],
                "examples/asi_proxy_loop_bundle/pic_token_admissibility.example.json": [
                    "pic.token_admissibility_report.v1"
                ],
            }
        )
    for relative, needles in required_files.items():
        path = pic_root / relative
        if not path.exists():
            findings.append(
                _finding(
                    "missing-pic-source-file",
                    relative,
                    "high",
                    True,
                    f"PIC source tree does not contain {relative}.",
                    repair_hint="Point --pic-root at a PIC v0.6.0-compatible source tree.",
                )
            )
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                findings.append(
                    _finding(
                        "missing-pic-compat-marker",
                        relative,
                        "medium",
                        True,
                        f"PIC compatibility marker is missing: {needle}",
                        repair_hint="Update the PIC root or compatibility matrix.",
                    )
                )


def _check_pic_repo_version(version: str | None, findings: list[dict[str, Any]]) -> None:
    if version is None:
        findings.append(
            _finding(
                "missing-pic-version",
                "pyproject.toml",
                "high",
                True,
                "PIC pyproject.toml does not expose a package version.",
                repair_hint="Use a PIC source root with explicit version metadata.",
            )
        )
        return
    if not (
        version.startswith("0.5.")
        or version.startswith("0.6.")
        or version.startswith("0.7.")
        or version.startswith("0.8.")
        or version.startswith("0.9.")
    ):
        findings.append(
            _finding(
                "unsupported-pic-version",
                "pyproject.toml",
                "medium",
                False,
                f"PIC source version is {version}; CCR v1.4 matrix targets PIC v0.5.x-v0.9.x.",
                repair_hint="Review INTEROP_PIC.md before relying on this PIC version.",
            )
        )


def _check_provider_mapping(findings: list[dict[str, Any]]) -> None:
    capabilities = PicProvider().capabilities()
    commands = capabilities.get("expected_pic_commands", [])
    fields = capabilities.get("supported_import_fields", [])
    for command in EXPECTED_PIC_COMMANDS:
        if command not in commands:
            findings.append(
                _finding(
                    "provider-command-mapping-gap",
                    "src/ccr/providers/pic.py",
                    "high",
                    True,
                    f"PicProvider.capabilities() does not expose command: {command}",
                    repair_hint="Expose the PIC command in PicProvider.capabilities().",
                )
            )
    for field in SUPPORTED_PIC_IMPORT_FIELDS:
        if field not in fields:
            findings.append(
                _finding(
                    "provider-field-mapping-gap",
                    "src/ccr/providers/pic.py",
                    "high",
                    True,
                    f"PicProvider.capabilities() does not expose import field: {field}",
                    repair_hint="Expose the field in PicProvider.capabilities().",
                )
            )


def _check_non_claim_boundary(
    ccr_root: Path, pic_root: Path, findings: list[dict[str, Any]]
) -> None:
    ccr_text = _read_texts(
        ccr_root,
        [
            "INTEROP_PIC.md",
            "SECURITY.md",
            "README.md",
            "SPEC.md",
        ],
    )
    pic_text = _read_texts(
        pic_root,
        [
            "README.md",
            "docs/porting.md",
            "docs/phase-acceleration.md",
            "docs/v060-audit.md",
            "docs/asi-proxy-loop.md",
            "docs/token-extraction.md",
        ],
    )
    required_ccr = [
        "PIC output never settles CCR by itself",
        "safe commands",
        "not real ASI",
        "ccr audit pic",
    ]
    required_pic = [
        "accepted=true",
        "settled=false",
        "safe_commands",
        "workflow_usable",
    ]
    for needle in required_ccr:
        if needle not in ccr_text:
            findings.append(
                _finding(
                    "missing-ccr-pic-boundary",
                    "CCR docs",
                    "high",
                    True,
                    f"CCR documentation does not preserve PIC boundary text: {needle}",
                    repair_hint="Update README, SPEC, SECURITY, or INTEROP_PIC.md.",
                )
            )
    for needle in required_pic:
        if needle not in pic_text:
            findings.append(
                _finding(
                    "missing-pic-boundary",
                    "PIC docs",
                    "medium",
                    True,
                    f"PIC documentation does not expose compatibility boundary text: {needle}",
                    repair_hint="Review the supplied --pic-root for v0.6.0 compatibility.",
                )
            )


def _read_texts(root: Path, relatives: list[str]) -> str:
    chunks: list[str] = []
    for relative in relatives:
        path = root / relative
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _installed_distribution_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _read_pyproject_version(path: Path) -> str | None:
    if not path.exists():
        return None
    match = re.search(r'^version\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def _finding(
    kind: str,
    location: str,
    severity: str,
    blocking: bool,
    description: str,
    *,
    repair_hint: str,
) -> dict[str, Any]:
    finding_id = stable_id("finding", kind, location, description)
    if kind == "provider_missing":
        residual_kind = "provider_missing"
    elif kind.startswith("missing"):
        residual_kind = "missing_evidence"
    else:
        residual_kind = "other"
    residual = build_residual(
        kind=residual_kind,
        description=description,
        blocking=blocking,
        object_type="runtime",
        object_id=location,
        severity=severity,
        refs=[location],
        source="ccr.audit.pic",
        repair_hint=repair_hint,
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
