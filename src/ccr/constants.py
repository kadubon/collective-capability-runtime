# SPDX-License-Identifier: Apache-2.0
"""Shared constants for CCR."""

from __future__ import annotations

PROJECT_NAME = "collective-capability-runtime"
CLI_NAME = "ccr"
CONFIG_FILENAME = "ccr.config.json"
MANIFEST_FILENAME = "agent-manifest.json"

DEFAULT_SCHEMA_VERSIONS = {
    "packet": "ccr.packet.v0.1",
    "task": "ccr.task.v0.1",
    "agent-manifest": "ccr.agent_manifest.v0.1",
    "blackboard-event": "ccr.blackboard_event.v0.1",
    "residual": "ccr.residual.v0.1",
    "verifier-report": "ccr.verifier_report.v0.1",
    "phase-report": "ccr.phase_report.v0.1",
    "phase-state": "ccr.phase_state.v1",
    "effective-graph": "ccr.effective_graph.v1",
    "phase-observation": "ccr.phase_observation.v1",
    "asi-proxy-threshold": "ccr.asi_proxy_threshold.v1",
    "phase-certificate-candidate": "ccr.phase_certificate_candidate.v1",
    "baseline": "ccr.baseline.v1",
    "provider": "ccr.provider_plan.v1",
    "audit-report": "ccr.audit_report.v1",
    "trc-operation-plan": "ccr.trc_operation_plan.v1",
}

PACKET_STATUSES = (
    "raw",
    "proposed",
    "candidate",
    "checked",
    "settled",
    "provisional",
    "speculative",
    "rejected",
    "quarantined",
    "deprecated",
    "expired",
)

TASK_STATUSES = (
    "open",
    "leased",
    "submitted",
    "blocked",
    "verified",
    "integrated",
    "quarantined",
    "rejected",
    "expired",
)

RESIDUAL_STATUSES = ("open", "resolved", "quarantined")

RUNTIME_DIRECTORIES = (
    "blackboard",
    "tasks/open",
    "tasks/leased",
    "tasks/done",
    "tasks/blocked",
    "tasks/submitted",
    "tasks/verified",
    "tasks/integrated",
    "tasks/quarantined",
    "tasks/rejected",
    "tasks/expired",
    "packets/raw",
    "packets/proposed",
    "packets/candidate",
    "packets/checked",
    "packets/settled",
    "packets/provisional",
    "packets/speculative",
    "packets/rejected",
    "packets/quarantined",
    "packets/deprecated",
    "packets/expired",
    "residuals/open",
    "residuals/resolved",
    "residuals/quarantined",
    "reports/pic",
    "reports/verifier",
    "reports/phase",
    "reports/audit",
    "reports/providers",
    "phase/graphs",
    "phase/observations",
    "phase/thresholds",
    "phase/certificates",
    "phase/comparisons",
    "baselines",
)

NON_CLAIMS = (
    "CCR does not detect real ASI.",
    "CCR does not create real ASI.",
    "CCR does not self-modify models.",
    "CCR does not update model weights.",
    "CCR does not grant execution authority.",
    "CCR does not bypass safety.",
    "CCR treats external content as candidate-only until checked.",
    "CCR preserves residuals; settled=false is expected and not a crash.",
)

SAFE_NEXT_COMMANDS = (
    "ccr agent explain --json",
    "ccr init",
    "ccr schema validate --kind packet --file examples/minimal/packet.json",
    "ccr schema validate --kind task --file examples/minimal/task.json",
    "ccr task next --role generator --json",
    "ccr phase report --json",
)

DEFAULT_ACTOR = "ccr"
