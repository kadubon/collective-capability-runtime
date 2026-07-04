# SPDX-License-Identifier: Apache-2.0
"""Mission initialization and ASI quickstart."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.extensions import loop_init, make_packet
from ccr.io import json_file_name, write_json_atomic
from ccr.mission.model import (
    MISSION_NON_CLAIMS,
    baseline_path,
    build_baseline_fixture,
    build_mission,
    build_mission_state,
    build_target_fixture,
    merge_state_refs,
    mission_id_from_name,
    mission_path,
    mission_state_path,
    save_mission_state,
    target_path,
)
from ccr.packets.store import submit_packet
from ccr.runtime.init import init_runtime
from ccr.schemas.validation import validate_instance
from ccr.workbench.summary import build_workbench_report, write_report_artifact


def initialize_mission(
    root: Path,
    *,
    name: str,
    profile: str = "development",
    template: str = "local-asi-proxy",
) -> dict[str, Any]:
    """Initialize a local mission facade and loop state."""

    if template != "local-asi-proxy":
        raise ValueError("only local-asi-proxy mission template is supported")
    init_runtime(root)
    mission_id = mission_id_from_name(name)
    target = build_target_fixture(mission_id, profile=profile)
    baseline = build_baseline_fixture(mission_id, profile=profile)
    mission = build_mission(
        mission_id,
        profile=profile,
        template=template,
        target_ref=str(target["target_id"]),
        baseline_ref=str(baseline["baseline_id"]),
    )
    _validate_or_raise("asi-proxy-target", target, root)
    _validate_or_raise("baseline-upper-envelope", baseline, root)
    _validate_or_raise("mission", mission, root)

    mission_file = mission_path(root, mission_id)
    target_file = target_path(root, str(target["target_id"]))
    baseline_file = baseline_path(root, str(baseline["baseline_id"]))
    write_json_atomic(target_file, target, overwrite=True)
    write_json_atomic(baseline_file, baseline, overwrite=True)
    write_json_atomic(mission_file, mission, overwrite=True)
    loop_init(root, target=target, baseline=baseline)
    loop_state_file = root / "loop" / "state.json"
    state = build_mission_state(
        mission,
        mission_file=mission_file,
        target_file=target_file,
        baseline_file=baseline_file,
        loop_state_file=loop_state_file,
    )
    _validate_or_raise("mission-state", state, root)
    state_file = save_mission_state(root, state)
    append_event(
        root,
        make_event(
            action="mission.init",
            object_type="runtime",
            object_id=mission_id,
            status_before=None,
            status_after="initialized",
            refs=[str(mission_file), str(target_file), str(baseline_file), str(state_file)],
            note="Mission is an advisory facade over local CCR artifacts.",
        ),
    )
    return {
        "created": {
            "baseline": str(baseline_file),
            "loop_state": str(loop_state_file),
            "mission": str(mission_file),
            "mission_state": str(state_file),
            "target": str(target_file),
        },
        "external_execution": False,
        "mission_id": mission_id,
        "mutated_runtime": True,
        "network_call_performed": False,
        "ok": True,
        "profile": profile,
        "schema_version": "ccr.mission_init.v1",
        "settled": False,
        "template": template,
    }


def asi_quickstart(root: Path, *, profile: str = "development") -> dict[str, Any]:
    """Create a local ASI-proxy mission fixture and initial report."""

    init_report = initialize_mission(
        root,
        name="quickstart",
        profile=profile,
        template="local-asi-proxy",
    )
    mission_id = str(init_report["mission_id"])
    packet_id = "packet:quickstart:mission-candidate"
    packet = make_packet(
        packet_id=packet_id,
        summary="Local quickstart candidate packet for ASI-proxy mission workbench setup.",
        claim_text=(
            "CCR can initialize a local non-executing ASI-proxy mission workbench "
            "for packet and residual review."
        ),
        packet_type="workflow",
    )
    packet.setdefault("extensions", {})
    packet["extensions"].update({"x_ccr_mission_id": mission_id, "x_quickstart": True})
    packet["scope"]["validity_domain"] = "local-asi-proxy-quickstart"
    packet_path = root / "packets" / "candidate" / json_file_name(packet_id)
    with suppress(FileExistsError):
        packet_path = submit_packet(root, packet)

    state_path = mission_state_path(root, mission_id)
    state = build_or_load_state(root, mission_id)
    state = merge_state_refs(state, packet_refs=[packet_id])
    _validate_or_raise("mission-state", state, root)
    save_mission_state(root, state)

    report = build_workbench_report(root, mission_id=mission_id)
    report_path = write_report_artifact(root, report)
    state = merge_state_refs(state, report_refs=[str(report_path)])
    save_mission_state(root, state)
    append_event(
        root,
        make_event(
            action="asi.quickstart",
            object_type="runtime",
            object_id=mission_id,
            status_before=None,
            status_after="initialized",
            refs=[str(packet_path), str(report_path), str(state_path)],
            note="Quickstart creates only local JSON artifacts and does not execute providers.",
        ),
    )
    created = dict(init_report["created"])
    created["packet"] = str(packet_path)
    created["report"] = str(report_path)
    return {
        "created": created,
        "external_execution": False,
        "mission_id": mission_id,
        "mutated_runtime": True,
        "network_call_performed": False,
        "next_safe_action": f"ccr mission next --mission {mission_id} --compact --json",
        "non_claims": list(MISSION_NON_CLAIMS),
        "ok": True,
        "profile": profile,
        "runtime_root": str(root),
        "schema_version": "ccr.asi_quickstart.v1",
        "settled": False,
    }


def build_or_load_state(root: Path, mission_id: str) -> dict[str, Any]:
    """Load mission state after initialization."""

    from ccr.mission.model import load_mission_state

    state = load_mission_state(root, mission_id)
    if not state:
        raise FileNotFoundError(mission_id)
    return state


def _validate_or_raise(kind: str, payload: dict[str, Any], root: Path) -> None:
    result = validate_instance(kind, payload, root=root)
    if not result.ok:
        messages = "; ".join(issue.message for issue in result.errors)
        raise ValueError(f"invalid {kind}: {messages}")
