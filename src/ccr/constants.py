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
    "trc-operation-preflight": "ccr.trc_operation_preflight.v1",
    "trc-operation-observation": "ccr.trc_operation_observation.v1",
    "asi-proxy-target": "ccr.asi_proxy_target.v1",
    "target-validity-certificate": "ccr.target_validity_certificate.v1",
    "baseline-upper-envelope": "ccr.baseline_upper_envelope.v1",
    "runtime-capital-witness": "ccr.runtime_capital_witness.v1",
    "phase-acceleration-report": "ccr.phase_acceleration_report.v1",
    "capital-transition-report": "ccr.capital_transition_report.v1",
    "opportunity-law-report": "ccr.opportunity_law_report.v1",
    "deployment-admissibility-report": "ccr.deployment_admissibility_report.v1",
    "activation-construction-certificate": "ccr.activation_construction_certificate.v1",
    "phase-response-control-step": "ccr.phase_response_control_step.v1",
    "path-law-response-policy": "ccr.path_law_response_policy.v1",
    "phase-control-action": "ccr.phase_control_action.v1",
    "operation-profile": "ccr.operation_profile.v1",
    "physical-provider-profile": "ccr.physical_provider_profile.v1",
    "observation-verifier-profile": "ccr.observation_verifier_profile.v1",
    "incident-ledger": "ccr.incident_ledger.v1",
    "mcp-tool-descriptor-report": "ccr.mcp_tool_descriptor_report.v1",
    "mcp-tool-invocation-preflight": "ccr.mcp_tool_invocation_preflight.v1",
    "a2a-agent-card-report": "ccr.a2a_agent_card_report.v1",
    "a2a-task-handoff-report": "ccr.a2a_task_handoff_report.v1",
    "mission": "ccr.mission.v1",
    "mission-state": "ccr.mission_state.v1",
    "mission-run-report": "ccr.mission_run_report.v1",
    "workbench-report": "ccr.workbench_report.v1",
    "claim-passport": "ccr.claim_passport.v1",
    "mission-bundle": "ccr.mission_bundle.v1",
    "bundle-validate-report": "ccr.bundle_validate.v1",
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
    "reports/workbench",
    "reports/claims",
    "phase/graphs",
    "phase/observations",
    "phase/thresholds",
    "phase/certificates",
    "phase/comparisons",
    "baselines",
    "missions",
    "missions/state",
    "missions/targets",
    "missions/baselines",
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
    "ccr asi quickstart --profile development --json",
    "ccr mission next --mission mission:quickstart --compact --json",
    "ccr agent explain --json",
    "ccr init",
    "ccr schema validate --kind packet --file examples/minimal/packet.json",
    "ccr schema validate --kind task --file examples/minimal/task.json",
    "ccr task next --role generator --json",
    "ccr phase report --json",
)

DEFAULT_ACTOR = "ccr"
