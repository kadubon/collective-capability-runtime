# SPDX-License-Identifier: Apache-2.0
"""Schema and manifest resource loading."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any, cast

from ccr.constants import MANIFEST_FILENAME
from ccr.paths import manifest_path, schemas_dir

SCHEMA_FILENAMES = {
    "packet": "packet.schema.json",
    "task": "task.schema.json",
    "agent-manifest": "agent-manifest.schema.json",
    "blackboard-event": "blackboard-event.schema.json",
    "residual": "residual.schema.json",
    "verifier-report": "verifier-report.schema.json",
    "phase-report": "phase-report.schema.json",
    "phase-state": "phase-state.schema.json",
    "effective-graph": "effective-graph.schema.json",
    "phase-observation": "phase-observation.schema.json",
    "asi-proxy-threshold": "asi-proxy-threshold.schema.json",
    "phase-certificate-candidate": "phase-certificate-candidate.schema.json",
    "baseline": "baseline.schema.json",
    "provider": "provider.schema.json",
    "audit-report": "audit-report.schema.json",
    "trc-operation-plan": "trc-operation-plan.schema.json",
    "trc-operation-preflight": "trc-operation-preflight.schema.json",
    "trc-operation-observation": "trc-operation-observation.schema.json",
    "asi-proxy-target": "asi-proxy-target.schema.json",
    "target-validity-certificate": "target-validity-certificate.schema.json",
    "baseline-upper-envelope": "baseline-upper-envelope.schema.json",
    "runtime-capital-witness": "runtime-capital-witness.schema.json",
    "phase-acceleration-report": "phase-acceleration-report.schema.json",
    "capital-transition-report": "capital-transition-report.schema.json",
    "opportunity-law-report": "opportunity-law-report.schema.json",
    "deployment-admissibility-report": "deployment-admissibility-report.schema.json",
    "activation-construction-certificate": "activation-construction-certificate.schema.json",
    "phase-response-control-step": "phase-response-control-step.schema.json",
    "path-law-response-policy": "path-law-response-policy.schema.json",
    "phase-control-action": "phase-control-action.schema.json",
    "operation-profile": "operation-profile.schema.json",
    "physical-provider-profile": "physical-provider-profile.schema.json",
    "observation-verifier-profile": "observation-verifier-profile.schema.json",
    "incident-ledger": "incident-ledger.schema.json",
    "mcp-tool-descriptor-report": "mcp-tool-descriptor-report.schema.json",
    "mcp-tool-invocation-preflight": "mcp-tool-invocation-preflight.schema.json",
    "a2a-agent-card-report": "a2a-agent-card-report.schema.json",
    "a2a-task-handoff-report": "a2a-task-handoff-report.schema.json",
    "mission": "mission.schema.json",
    "mission-state": "mission-state.schema.json",
    "mission-run-report": "mission-run-report.schema.json",
    "workbench-report": "workbench-report.schema.json",
    "claim-passport": "claim-passport.schema.json",
    "mission-bundle": "mission-bundle.schema.json",
    "bundle-validate-report": "bundle-validate-report.schema.json",
    "provider-manifest": "provider-manifest.schema.json",
    "provider-manifest-report": "provider-manifest-report.schema.json",
    "provider-conformance-report": "provider-conformance-report.schema.json",
    "external-ingest-report": "external-ingest-report.schema.json",
    "residual-market": "residual-market.schema.json",
    "residual-bounty": "residual-bounty.schema.json",
    "residual-diff": "residual-diff.schema.json",
    "static-workbench-export-report": "static-workbench-export-report.schema.json",
    "operation-replay-manifest": "operation-replay-manifest.schema.json",
    "observation-verification-report": "observation-verification-report.schema.json",
    "cross-repo-conformance-report": "cross-repo-conformance-report.schema.json",
    "parity-report": "parity-report.schema.json",
    "provider-registry": "provider-registry.schema.json",
    "provider-registry-report": "provider-registry-report.schema.json",
}


def _load_resource_text(relative: str) -> str:
    data_root = resources.files("ccr.data")
    return data_root.joinpath(relative).read_text(encoding="utf-8")


def _loads_object(text: str, source: str) -> dict[str, Any]:
    data: object = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return cast(dict[str, Any], data)


def _repository_resource_path(relative: str) -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return None


def load_schema(kind: str, *, root: Path | None = None) -> dict[str, Any]:
    """Load a schema from local ``schemas/`` first, then package resources."""

    if kind not in SCHEMA_FILENAMES:
        raise KeyError(f"unknown schema kind: {kind}")
    filename = SCHEMA_FILENAMES[kind]
    if root is not None:
        local_path = schemas_dir(root) / filename
        if local_path.exists():
            return _loads_object(local_path.read_text(encoding="utf-8"), str(local_path))
    repository_path = _repository_resource_path(f"schemas/{filename}")
    if repository_path is not None:
        return _loads_object(repository_path.read_text(encoding="utf-8"), str(repository_path))
    return _loads_object(_load_resource_text(f"schemas/{filename}"), f"schemas/{filename}")


def load_agent_manifest(*, root: Path | None = None) -> dict[str, Any]:
    """Load the local agent manifest first, then packaged data."""

    if root is not None:
        local_path = manifest_path(root)
        if local_path.exists():
            return _loads_object(local_path.read_text(encoding="utf-8"), str(local_path))
    repository_path = _repository_resource_path(MANIFEST_FILENAME)
    if repository_path is not None:
        return _loads_object(repository_path.read_text(encoding="utf-8"), str(repository_path))
    return _loads_object(_load_resource_text(MANIFEST_FILENAME), MANIFEST_FILENAME)


def expected_schema_version(kind: str, *, root: Path | None = None) -> str | None:
    """Return the schema_version const declared by a schema."""

    schema = load_schema(kind, root=root)
    version_schema = schema.get("properties", {}).get("schema_version", {})
    value = version_schema.get("const")
    return value if isinstance(value, str) else None
