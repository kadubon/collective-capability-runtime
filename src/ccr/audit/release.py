# SPDX-License-Identifier: Apache-2.0
"""Public release hygiene audit for source trees and distribution archives."""

from __future__ import annotations

import re
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ccr.ids import stable_id
from ccr.residuals.model import build_residual
from ccr.time import now_iso

TEXT_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".json",
    ".lock",
    ".md",
    ".pem",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
ARCHIVE_SUFFIXES = (".whl", ".tar.gz")
SKIP_SOURCE_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
}
GENERATED_TOP_LEVEL_DIRS = {
    "blackboard",
    "cache",
    "experiments",
    "loop",
    "missions",
    "packets",
    "phase",
    "providers",
    "reports",
    "residuals",
    "tasks",
    "tokens",
    "workcells",
}
GENERATED_EXAMPLE_DIRS = {
    "blackboard",
    "phase",
    "reports",
    "residuals",
    "tasks",
}
CACHE_OR_BUILD_PARTS = {
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "htmlcov",
}
FORBIDDEN_NAME_SUFFIXES = {
    ".pyc",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
}
_WIN_HOME_PATTERN = r"[A-Za-z]:\\" + "Users" + r"\\[^\\\s]+"
_MAC_HOME_PATTERN = "/" + "Users" + r"/[^/\s]+"
_LINUX_HOME_PATTERN = "/" + "home" + r"/[^/\s]+"
LOCAL_PATH_RE = re.compile(rf"(?:{_WIN_HOME_PATTERN}|{_MAC_HOME_PATTERN}|{_LINUX_HOME_PATTERN})")
PEM_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|SECRET KEY)[A-Z0-9 ]*-----")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password|pypi[_-]?token)\b"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{8,}"
)
GITHUB_SECRET_REF_RE = re.compile(r"secrets\.[A-Za-z0-9_]*(?:TOKEN|PASSWORD|SECRET|KEY)")


def audit_release(root: Path, *, dist: Path | None = None) -> dict[str, Any]:
    """Audit source and distribution artifacts before public release."""

    findings: list[dict[str, Any]] = []
    dist_path = dist if dist is not None else root / "dist"
    _scan_source_tree(root, findings)
    _scan_dist(dist_path, findings)
    blocking = [finding for finding in findings if finding["blocking"]]
    return {
        "accepted": not blocking,
        "blocking_finding_count": len(blocking),
        "created_at": now_iso(),
        "dist": str(dist_path),
        "finding_count": len(findings),
        "findings": findings,
        "ok": not blocking,
        "report_id": stable_id(
            "release-audit", str(root), str(dist_path), [item["finding_id"] for item in findings]
        ),
        "schema_version": "ccr.audit_report.v1",
        "settled": False,
    }


def _scan_source_tree(root: Path, findings: list[dict[str, Any]]) -> None:
    for path in sorted(root.rglob("*")):
        relative = _safe_relative(path, root)
        if _is_skipped_source_path(relative):
            continue
        if path.is_dir():
            if _has_forbidden_artifact_name(relative):
                findings.append(
                    _finding(
                        "release-generated-artifact",
                        relative,
                        "high",
                        True,
                        f"Generated or local runtime artifact directory is present: {relative}",
                    )
                )
            continue
        if _has_forbidden_artifact_name(relative):
            findings.append(
                _finding(
                    "release-generated-artifact",
                    relative,
                    "high",
                    True,
                    f"Generated or local runtime artifact is present: {relative}",
                )
            )
        if _should_scan_text(path.name):
            _scan_text_bytes(
                location=relative,
                data=path.read_bytes(),
                findings=findings,
                archive=False,
            )


def _scan_dist(dist: Path, findings: list[dict[str, Any]]) -> None:
    if not dist.exists():
        findings.append(
            _finding(
                "missing-dist",
                str(dist),
                "high",
                True,
                "Distribution directory is missing; run uv build before release audit.",
            )
        )
        return
    archives = [path for path in sorted(dist.iterdir()) if _is_distribution_archive(path.name)]
    if not archives:
        findings.append(
            _finding(
                "missing-dist-archive",
                str(dist),
                "high",
                True,
                "No wheel or sdist archive found in distribution directory.",
            )
        )
    for archive in archives:
        if archive.name.endswith(".whl"):
            _scan_wheel(archive, findings)
        elif archive.name.endswith(".tar.gz"):
            _scan_sdist(archive, findings)


def _scan_wheel(path: Path, findings: list[dict[str, Any]]) -> None:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            _scan_archive_member_name(path.name, name, findings)
            if _should_scan_text(name):
                _scan_text_bytes(
                    location=f"{path.name}!{name}",
                    data=archive.read(name),
                    findings=findings,
                    archive=True,
                )


def _scan_sdist(path: Path, findings: list[dict[str, Any]]) -> None:
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            _scan_archive_member_name(path.name, member.name, findings)
            if member.isfile() and _should_scan_text(member.name):
                file_obj = archive.extractfile(member)
                if file_obj is not None:
                    _scan_text_bytes(
                        location=f"{path.name}!{member.name}",
                        data=file_obj.read(),
                        findings=findings,
                        archive=True,
                    )


def _scan_archive_member_name(
    archive_name: str, member_name: str, findings: list[dict[str, Any]]
) -> None:
    if _has_forbidden_artifact_name(member_name):
        findings.append(
            _finding(
                "release-archive-artifact",
                f"{archive_name}!{member_name}",
                "high",
                True,
                f"Distribution archive contains generated or local artifact: {member_name}",
            )
        )


def _scan_text_bytes(
    *, location: str, data: bytes, findings: list[dict[str, Any]], archive: bool
) -> None:
    text = data.decode("utf-8", errors="ignore")
    checks = [
        ("release-local-path", LOCAL_PATH_RE, "Local user path or username is present."),
        ("release-pem-secret", PEM_RE, "PEM-like private secret material is present."),
        ("release-secret-assignment", SECRET_ASSIGNMENT_RE, "Secret-like assignment is present."),
        (
            "release-token-secret-ref",
            GITHUB_SECRET_REF_RE,
            "GitHub secret token/password/key reference is present.",
        ),
    ]
    for kind, pattern, description in checks:
        if pattern.search(text):
            findings.append(
                _finding(
                    kind,
                    location,
                    "critical" if "secret" in kind or "token" in kind else "high",
                    True,
                    f"{description} Location is {'archive' if archive else 'source'} content.",
                )
            )


def _is_distribution_archive(name: str) -> bool:
    return name.endswith(ARCHIVE_SUFFIXES)


def _is_skipped_source_path(relative: str) -> bool:
    return any(part in SKIP_SOURCE_PARTS for part in _parts(relative))


def _has_forbidden_artifact_name(relative: str) -> bool:
    parts = _normalized_parts(relative)
    part_set = set(parts)
    if part_set & CACHE_OR_BUILD_PARTS:
        return True
    if parts and parts[0] in GENERATED_TOP_LEVEL_DIRS:
        return True
    if (
        len(parts) >= 3
        and parts[:2] == ["examples", "phase_formation"]
        and parts[2] in GENERATED_EXAMPLE_DIRS
    ):
        return True
    if parts and parts[-1].startswith("ccr.sqlite"):
        return True
    return any(relative.endswith(suffix) for suffix in FORBIDDEN_NAME_SUFFIXES)


def _parts(relative: str) -> Iterator[str]:
    return iter(relative.replace("\\", "/").split("/"))


def _normalized_parts(relative: str) -> list[str]:
    parts = list(_parts(relative))
    if parts and parts[0].startswith("collective_capability_runtime-"):
        return parts[1:]
    if (
        len(parts) > 1
        and _looks_like_archive_root(parts[0])
        and (parts[1] == "examples" or parts[1] in GENERATED_TOP_LEVEL_DIRS)
    ):
        return parts[1:]
    return parts


def _looks_like_archive_root(part: str) -> bool:
    return "-" in part and any(character.isdigit() for character in part)


def _should_scan_text(name: str) -> bool:
    return Path(name).suffix.lower() in TEXT_SUFFIXES or Path(name).name in {
        "PKG-INFO",
        "METADATA",
        "LICENSE",
        "NOTICE",
    }


def _safe_relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _finding(
    kind: str,
    location: str,
    severity: str,
    blocking: bool,
    description: str,
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
        source="ccr.audit.release",
        repair_hint="Remove release hygiene issue and rerun ccr audit release --dist dist --json.",
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
