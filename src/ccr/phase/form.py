# SPDX-License-Identifier: Apache-2.0
"""End-to-end local phase formation cycle."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.ids import stable_id
from ccr.io import write_json_atomic
from ccr.phase.certify import build_certificate_candidate
from ccr.phase.graph import build_effective_graph
from ccr.phase.observe import build_phase_observation
from ccr.phase.threshold import default_threshold, evaluate_threshold
from ccr.storage.sqlite import record_object, record_phase_observation
from ccr.tasks.store import submit_task, validate_task
from ccr.time import now_iso


def run_phase_formation(root: Path, *, profile: str = "development") -> dict[str, Any]:
    """Run graph -> observation -> threshold -> certificate -> repair task planning."""

    graph = build_effective_graph(root)
    observation = build_phase_observation(root, graph)
    threshold = default_threshold(profile)
    threshold_status = evaluate_threshold(observation, threshold)
    certificate = build_certificate_candidate(
        root,
        graph=graph,
        observation=observation,
        threshold=threshold,
        threshold_status=threshold_status,
    )
    graph_path = root / "phase" / "graphs" / f"{graph['graph_id'].replace(':', '_')}.json"
    observation_path = (
        root / "phase" / "observations" / f"{observation['observation_id'].replace(':', '_')}.json"
    )
    threshold_path = (
        root / "phase" / "thresholds" / f"{threshold_status['status_id'].replace(':', '_')}.json"
    )
    certificate_path = (
        root / "phase" / "certificates" / f"{certificate['certificate_id'].replace(':', '_')}.json"
    )
    write_json_atomic(graph_path, graph, overwrite=True)
    write_json_atomic(observation_path, observation, overwrite=True)
    write_json_atomic(threshold_path, threshold_status, overwrite=True)
    write_json_atomic(certificate_path, certificate, overwrite=True)
    record_object(
        root,
        object_type="phase",
        object_id=graph["graph_id"],
        status="graph",
        path=graph_path,
        content=graph,
    )
    record_phase_observation(root, observation=observation, path=observation_path)
    record_object(
        root,
        object_type="phase",
        object_id=certificate["certificate_id"],
        status=certificate["certificate_status"],
        path=certificate_path,
        content=certificate,
    )
    tasks = _create_repair_tasks(root, threshold_status, observation)
    append_event(
        root,
        make_event(
            action="phase.form",
            object_type="phase",
            object_id=str(certificate["certificate_id"]),
            status_before=None,
            status_after=str(certificate["certificate_status"]),
            refs=[
                str(graph_path),
                str(observation_path),
                str(threshold_path),
                str(certificate_path),
            ],
            note="Local phase formation cycle completed without external execution.",
        ),
    )
    return {
        "certificate": certificate,
        "certificate_path": str(certificate_path),
        "graph": graph,
        "graph_path": str(graph_path),
        "observation": observation,
        "observation_path": str(observation_path),
        "ok": True,
        "repair_tasks": tasks,
        "threshold_status": threshold_status,
        "threshold_status_path": str(threshold_path),
    }


def _create_repair_tasks(
    root: Path, threshold_status: dict[str, Any], observation: dict[str, Any]
) -> list[str]:
    task_ids: list[str] = []
    for component in threshold_status.get("failed_components", []):
        task_id = stable_id("task:phase-repair", observation.get("observation_id"), component)
        task = _repair_task(task_id, component, observation)
        result = validate_task(task, root=root)
        if not result.ok:
            continue
        with suppress(FileExistsError):
            submit_task(root, task)
        task_ids.append(task_id)
        append_event(
            root,
            make_event(
                action="task.phase_repair.create",
                object_type="task",
                object_id=task_id,
                status_before=None,
                status_after="open",
                refs=[str(observation.get("observation_id", ""))],
                note=f"Repair task generated for failed phase component: {component}",
            ),
        )
    return task_ids


def _repair_task(task_id: str, component: str, observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "blackboard_refs": [],
        "completion": {},
        "constraints": {
            "allowed_commands": [],
            "authority_policy": "read_only",
            "forbidden_actions": ["automatic_execution", "external_side_effect"],
            "max_runtime_minutes": 45,
            "network_policy": "none",
            "side_effect_policy": "dry_run_only",
        },
        "created_at": now_iso(),
        "dependencies": [],
        "expected_outputs": [
            {
                "acceptance_criteria": [
                    "A packet, verifier report, or residual update addresses "
                    "the failed phase component."
                ],
                "destination": "tasks/open",
                "kind": "packet",
                "schema_ref": "schemas/packet.schema.json",
            }
        ],
        "extensions": {"x_phase_component": component},
        "inputs": [
            {
                "kind": "report",
                "notes": f"Observation failed component {component}",
                "ref": str(observation.get("observation_id", "")),
                "required": True,
            }
        ],
        "lease": {
            "lease_required": True,
            "leased_at": None,
            "leased_by": None,
            "renewal_allowed": True,
            "ttl_minutes": 30,
        },
        "objective": f"Repair ASI-proxy phase component: {component}.",
        "pic_interop": {
            "candidate_only_until_checked": True,
            "enabled": True,
            "identity_context_required": False,
            "input_mapping": "report_to_phase_plan",
            "output_mapping": "pic_phase_plan_to_tasks",
            "pic_profile": "development",
            "recommended_pic_commands": ["pic phase plan --compact --profile development"],
        },
        "priority": 80,
        "residual_policy": {
            "blocking_residuals_prevent_settlement": True,
            "minimum_residual_fields": ["residual_id", "kind", "description", "blocking"],
            "preserve_residuals": True,
            "residual_destination": "residuals/open",
        },
        "role": "integrator",
        "schema_version": "ccr.task.v0.1",
        "status": "open",
        "task_id": task_id,
        "title": f"Repair phase component {component}",
        "verifier_plan": {
            "failure_route": "residual",
            "optional_verifiers": ["human", "pic"],
            "promotion_gate": "pic_checked",
            "required_verifiers": [],
        },
    }
