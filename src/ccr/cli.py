# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for Collective Capability Runtime."""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

from ccr.adapters.pic import PicVerifierProvider, report_output_path
from ccr.audit.pic import audit_pic_compatibility
from ccr.audit.release import audit_release
from ccr.audit.repo import audit_repository
from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.constants import DEFAULT_ACTOR, NON_CLAIMS, SAFE_NEXT_COMMANDS
from ccr.errors import (
    EXIT_INTERNAL,
    EXIT_MISSING,
    EXIT_POLICY_FAILURE,
    EXIT_SUCCESS,
    CCRException,
    CCRMissingError,
)
from ccr.ids import stable_id
from ccr.io import json_file_name, pretty_dumps, read_json, write_json_atomic
from ccr.packets.promotion import promote_packet
from ccr.packets.store import load_packet, save_packet_at_status, submit_packet, validate_packet
from ccr.paths import runtime_root
from ccr.phase.baseline import compare_observation_to_baseline
from ccr.phase.certify import build_certificate_candidate
from ccr.phase.form import run_phase_formation
from ccr.phase.graph import build_effective_graph
from ccr.phase.observe import build_phase_observation
from ccr.phase.threshold import default_threshold, evaluate_threshold
from ccr.providers.base import Provider
from ccr.providers.registry import get_provider, list_providers
from ccr.reports.json_report import phase_report
from ccr.reports.markdown import render_markdown_report
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.runtime.init import init_runtime
from ccr.schemas.loader import load_agent_manifest
from ccr.schemas.validation import validate_instance
from ccr.storage.sqlite import record_object, record_phase_observation, record_provider_run
from ccr.tasks.lease import lease_task, release_task
from ccr.tasks.scheduler import next_task
from ccr.tasks.store import submit_task, validate_task
from ccr.time import now_iso


def main(argv: list[str] | None = None) -> int:
    """Run the CCR CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except CCRException as exc:
        _emit_json(exc.payload)
        return exc.exit_code
    except FileNotFoundError as exc:
        _emit_json({"error": f"missing file or object: {exc}", "ok": False})
        return EXIT_MISSING
    except FileExistsError as exc:
        _emit_json({"error": f"object already exists: {exc}", "ok": False})
        return EXIT_POLICY_FAILURE
    except ValueError as exc:
        _emit_json({"error": str(exc), "ok": False})
        return EXIT_POLICY_FAILURE
    except Exception as exc:  # pragma: no cover - last-resort CLI boundary.
        _emit_json({"error": str(exc), "ok": False, "type": type(exc).__name__})
        return EXIT_INTERNAL


def build_parser() -> argparse.ArgumentParser:
    """Build the command parser."""

    parser = argparse.ArgumentParser(prog="ccr")
    parser.add_argument("--root", help="CCR runtime root. Defaults to CCR_ROOT or cwd.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialize CCR runtime directories.")
    init.add_argument("--force", action="store_true", help="Rewrite ccr.config.json.")
    init.set_defaults(func=cmd_init)

    agent = sub.add_parser("agent", help="Agent-facing commands.")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    agent_explain = agent_sub.add_parser("explain", help="Explain CCR contract.")
    agent_explain.add_argument("--json", action="store_true", dest="json_output")
    agent_explain.set_defaults(func=cmd_agent_explain)

    schema = sub.add_parser("schema", help="Schema commands.")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    schema_validate = schema_sub.add_parser("validate", help="Validate JSON.")
    schema_validate.add_argument("--kind", required=True)
    schema_validate.add_argument("--file", required=True)
    schema_validate.set_defaults(func=cmd_schema_validate)

    audit = sub.add_parser("audit", help="Repository and runtime audit commands.")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_repo = audit_sub.add_parser("repo", help="Audit repository v1 readiness.")
    audit_repo.add_argument("--json", action="store_true", dest="json_output")
    audit_repo.set_defaults(func=cmd_audit_repo)
    audit_pic = audit_sub.add_parser("pic", help="Audit optional PIC compatibility.")
    audit_pic.add_argument("--pic-root", help="PIC source root for compatibility audit.")
    audit_pic.add_argument("--json", action="store_true", dest="json_output")
    audit_pic.set_defaults(func=cmd_audit_pic)
    audit_release_cmd = audit_sub.add_parser("release", help="Audit public release artifacts.")
    audit_release_cmd.add_argument("--dist", default="dist", help="Distribution directory.")
    audit_release_cmd.add_argument("--json", action="store_true", dest="json_output")
    audit_release_cmd.set_defaults(func=cmd_audit_release)

    task = sub.add_parser("task", help="Task queue commands.")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_submit = task_sub.add_parser("submit", help="Submit a task.")
    task_submit.add_argument("--file", required=True)
    task_submit.set_defaults(func=cmd_task_submit)
    task_next = task_sub.add_parser("next", help="Return next task without leasing.")
    task_next.add_argument("--role", required=True)
    task_next.add_argument("--json", action="store_true", dest="json_output")
    task_next.set_defaults(func=cmd_task_next)
    task_lease = task_sub.add_parser("lease", help="Lease a task.")
    task_lease.add_argument("task_id")
    task_lease.add_argument("--ttl", required=True)
    task_lease.add_argument("--agent", required=True)
    task_lease.add_argument("--json", action="store_true", dest="json_output")
    task_lease.set_defaults(func=cmd_task_lease)
    task_release = task_sub.add_parser("release", help="Release a leased task.")
    task_release.add_argument("task_id")
    task_release.add_argument("--reason", required=True)
    task_release.add_argument("--json", action="store_true", dest="json_output")
    task_release.set_defaults(func=cmd_task_release)

    packet = sub.add_parser("packet", help="Packet commands.")
    packet_sub = packet.add_subparsers(dest="packet_command", required=True)
    packet_submit = packet_sub.add_parser("submit", help="Submit a packet.")
    packet_submit.add_argument("--file", required=True)
    packet_submit.add_argument("--json", action="store_true", dest="json_output")
    packet_submit.set_defaults(func=cmd_packet_submit)
    packet_show = packet_sub.add_parser("show", help="Show a packet.")
    packet_show.add_argument("packet_id")
    packet_show.add_argument("--json", action="store_true", dest="json_output")
    packet_show.set_defaults(func=cmd_packet_show)
    packet_promote = packet_sub.add_parser("promote", help="Promote a packet.")
    packet_promote.add_argument("packet_id")
    packet_promote.add_argument("--target", required=True)
    packet_promote.add_argument("--json", action="store_true", dest="json_output")
    packet_promote.set_defaults(func=cmd_packet_promote)

    residual = sub.add_parser("residual", help="Residual ledger commands.")
    residual_sub = residual.add_subparsers(dest="residual_command", required=True)
    residual_add = residual_sub.add_parser("add", help="Add a residual.")
    residual_add.add_argument("--file", required=True)
    residual_add.add_argument("--json", action="store_true", dest="json_output")
    residual_add.set_defaults(func=cmd_residual_add)

    verify = sub.add_parser("verify", help="Run or plan a verifier provider.")
    verify.add_argument("--provider", required=True)
    verify.add_argument("--packet", required=True, dest="packet_id")
    verify.add_argument("--profile", default="development")
    verify.add_argument("--execute", action="store_true")
    verify.add_argument("--timeout", type=int, default=60)
    verify.add_argument("--json", action="store_true", dest="json_output")
    verify.set_defaults(func=cmd_verify)

    integrate = sub.add_parser("integrate", help="Import a PIC-like report.")
    integrate.add_argument("--report", required=True)
    integrate.add_argument("--json", action="store_true", dest="json_output")
    integrate.set_defaults(func=cmd_integrate)

    provider = sub.add_parser("provider", help="External provider commands.")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    provider_list = provider_sub.add_parser("list", help="List providers.")
    provider_list.add_argument("--json", action="store_true", dest="json_output")
    provider_list.set_defaults(func=cmd_provider_list)
    provider_health = provider_sub.add_parser("health", help="Check provider health.")
    provider_health.add_argument("--provider", required=True)
    provider_health.add_argument("--json", action="store_true", dest="json_output")
    provider_health.set_defaults(func=cmd_provider_health)
    provider_plan = provider_sub.add_parser("plan", help="Build a dry-run provider plan.")
    provider_plan.add_argument("--provider", required=True)
    provider_plan.add_argument("--action", required=True)
    provider_plan.add_argument("--file")
    provider_plan.add_argument("--packet", dest="packet_id")
    provider_plan.add_argument("--profile", default="development")
    provider_plan.add_argument("--json", action="store_true", dest="json_output")
    provider_plan.set_defaults(func=cmd_provider_plan)
    provider_execute = provider_sub.add_parser(
        "execute",
        help="Execute an explicitly configured provider.",
    )
    provider_execute.add_argument("--provider", required=True)
    provider_execute.add_argument("--action", required=True)
    provider_execute.add_argument("--config", required=True)
    provider_execute.add_argument("--file")
    provider_execute.add_argument("--packet", dest="packet_id")
    provider_execute.add_argument("--profile", default="development")
    provider_execute.add_argument("--execute", action="store_true")
    provider_execute.add_argument("--json", action="store_true", dest="json_output")
    provider_execute.set_defaults(func=cmd_provider_execute)
    provider_import = provider_sub.add_parser("import", help="Import a provider report.")
    provider_import.add_argument("--provider", required=True)
    provider_import.add_argument("--report", required=True)
    provider_import.add_argument("--json", action="store_true", dest="json_output")
    provider_import.set_defaults(func=cmd_provider_import)

    phase = sub.add_parser("phase", help="Phase commands.")
    phase_sub = phase.add_subparsers(dest="phase_command", required=True)
    phase_graph_cmd = phase_sub.add_parser("graph", help="Build the effective packet graph.")
    phase_graph_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_graph_cmd.set_defaults(func=cmd_phase_graph)
    phase_observe_cmd = phase_sub.add_parser("observe", help="Build a phase observation.")
    phase_observe_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_observe_cmd.set_defaults(func=cmd_phase_observe)
    phase_threshold_cmd = phase_sub.add_parser("threshold", help="Evaluate an ASI-proxy threshold.")
    phase_threshold_cmd.add_argument("--file", required=True)
    phase_threshold_cmd.add_argument("--observation")
    phase_threshold_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_threshold_cmd.set_defaults(func=cmd_phase_threshold)
    phase_compare_cmd = phase_sub.add_parser("compare", help="Compare observation to baseline.")
    phase_compare_cmd.add_argument("--baseline", required=True)
    phase_compare_cmd.add_argument("--candidate", required=True)
    phase_compare_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_compare_cmd.set_defaults(func=cmd_phase_compare)
    phase_form_cmd = phase_sub.add_parser("form", help="Run a local phase formation cycle.")
    phase_form_cmd.add_argument("--profile", default="development")
    phase_form_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_form_cmd.set_defaults(func=cmd_phase_form)
    phase_certify_cmd = phase_sub.add_parser("certify", help="Build a phase certificate candidate.")
    phase_certify_cmd.add_argument("--threshold")
    phase_certify_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_certify_cmd.set_defaults(func=cmd_phase_certify)
    phase_plan_cmd = phase_sub.add_parser("plan", help="Build a dry-run phase plan.")
    phase_plan_cmd.add_argument("--provider", required=True)
    phase_plan_cmd.add_argument("--profile", default="development")
    phase_plan_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_plan_cmd.set_defaults(func=cmd_phase_plan)
    phase_report_cmd = phase_sub.add_parser("report", help="Summarize runtime state.")
    phase_report_cmd.add_argument("--json", action="store_true", dest="json_output")
    phase_report_cmd.set_defaults(func=cmd_phase_report)

    report = sub.add_parser("report", help="Human-readable report.")
    report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    report.set_defaults(func=cmd_report)
    return parser


def cmd_init(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    payload = init_runtime(root, force=bool(args.force))
    append_event(
        root,
        make_event(
            action="runtime.init",
            object_type="runtime",
            object_id=str(root),
            status_before=None,
            status_after="initialized",
            note="idempotent runtime initialization",
        ),
    )
    _emit_json(payload)
    return EXIT_SUCCESS


def cmd_agent_explain(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    manifest = load_agent_manifest(root=root)
    payload = {
        "agent_manifest": manifest,
        "default_mode": "dry_run",
        "non_claims": list(NON_CLAIMS),
        "ok": True,
        "runtime_paths": {
            "blackboard": str(root / "blackboard" / "events.jsonl"),
            "packets": str(root / "packets"),
            "reports": str(root / "reports"),
            "residuals": str(root / "residuals"),
            "root": str(root),
            "tasks": str(root / "tasks"),
        },
        "safe_next_commands": list(SAFE_NEXT_COMMANDS),
    }
    _emit_json(payload)
    return EXIT_SUCCESS


def cmd_schema_validate(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    path = Path(args.file)
    data = _read_object(path)
    result = validate_instance(args.kind, data, root=root)
    payload = result.to_json()
    payload["file"] = str(path)
    payload["kind"] = args.kind
    _emit_json(payload)
    return EXIT_SUCCESS if result.ok else EXIT_POLICY_FAILURE


def cmd_audit_repo(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    report = audit_repository(root)
    _emit_json(report)
    return EXIT_SUCCESS if report.get("ok") else EXIT_POLICY_FAILURE


def cmd_audit_pic(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    pic_root = Path(args.pic_root) if args.pic_root else None
    report = audit_pic_compatibility(root, pic_root=pic_root)
    _emit_json(report)
    return EXIT_SUCCESS if report.get("ok") else EXIT_POLICY_FAILURE


def cmd_audit_release(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    dist = Path(args.dist)
    if not dist.is_absolute():
        dist = root / dist
    report = audit_release(root, dist=dist)
    _emit_json(report)
    return EXIT_SUCCESS if report.get("ok") else EXIT_POLICY_FAILURE


def cmd_task_submit(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    path = Path(args.file)
    task = _read_object(path)
    result = validate_task(task, root=root)
    if not result.ok:
        payload = _validation_failure_payload("task", task, path, result.to_json())
        _emit_json(payload)
        return EXIT_POLICY_FAILURE
    destination = submit_task(root, task)
    append_event(
        root,
        make_event(
            action="task.submit",
            object_type="task",
            object_id=str(task["task_id"]),
            status_before=None,
            status_after=str(task.get("status", "open")),
            refs=[str(path)],
        ),
    )
    _emit_json({"ok": True, "path": str(destination), "task_id": task["task_id"]})
    return EXIT_SUCCESS


def cmd_task_next(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    task = next_task(root, role=args.role)
    _emit_json({"ok": True, "role": args.role, "task": task})
    return EXIT_SUCCESS


def cmd_task_lease(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    result = lease_task(root, args.task_id, ttl=args.ttl, agent=args.agent)
    if result.get("ok"):
        append_event(
            root,
            make_event(
                action="task.lease",
                actor=args.agent,
                object_type="task",
                object_id=args.task_id,
                status_before=str(result.get("status_before")),
                status_after=str(result.get("status_after")),
            ),
        )
        _emit_json(result)
        return EXIT_SUCCESS
    _emit_json(result)
    return EXIT_POLICY_FAILURE


def cmd_task_release(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    result = release_task(root, args.task_id, reason=args.reason)
    residual_ids: list[str] = []
    residual = result.get("residual")
    if isinstance(residual, dict):
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
        append_event(
            root,
            make_event(
                action="residual.add",
                object_type="residual",
                object_id=str(residual["residual_id"]),
                status_before=None,
                status_after=str(residual["status"]),
                refs=[args.task_id],
                residuals=residual_ids,
            ),
        )
    append_event(
        root,
        make_event(
            action="task.release",
            object_type="task",
            object_id=args.task_id,
            status_before=str(result.get("status_before")),
            status_after=str(result.get("status_after")),
            residuals=residual_ids,
            note=args.reason,
        ),
    )
    result["residuals"] = residual_ids
    _emit_json(result)
    return EXIT_SUCCESS


def cmd_packet_submit(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    path = Path(args.file)
    packet = _read_object(path)
    result = validate_packet(packet, root=root)
    if not result.ok:
        payload = _validation_failure_payload("packet", packet, path, result.to_json())
        _emit_json(payload)
        return EXIT_POLICY_FAILURE
    destination = submit_packet(root, packet)
    append_event(
        root,
        make_event(
            action="packet.submit",
            object_type="packet",
            object_id=str(packet["packet_id"]),
            status_before=None,
            status_after=str(packet.get("status", "candidate")),
            refs=[str(path)],
        ),
    )
    _emit_json({"ok": True, "packet_id": packet["packet_id"], "path": str(destination)})
    return EXIT_SUCCESS


def cmd_packet_show(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    packet, path, status = load_packet(root, args.packet_id)
    _emit_json({"ok": True, "packet": packet, "path": str(path), "status": status})
    return EXIT_SUCCESS


def cmd_packet_promote(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    result = promote_packet(root, args.packet_id, target=args.target, actor=DEFAULT_ACTOR)
    _emit_json(result)
    return EXIT_SUCCESS if result.get("ok") else EXIT_POLICY_FAILURE


def cmd_residual_add(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    path = Path(args.file)
    residual = _read_object(path)
    result = validate_instance("residual", residual, root=root)
    if not result.ok:
        payload = _validation_failure_payload("residual", residual, path, result.to_json())
        _emit_json(payload)
        return EXIT_POLICY_FAILURE
    destination = save_residual(root, residual, overwrite=False)
    append_event(
        root,
        make_event(
            action="residual.add",
            object_type="residual",
            object_id=str(residual["residual_id"]),
            status_before=None,
            status_after=str(residual["status"]),
            refs=[str(path)],
            residuals=[str(residual["residual_id"])],
        ),
    )
    _emit_json({"ok": True, "path": str(destination), "residual_id": residual["residual_id"]})
    return EXIT_SUCCESS


def cmd_verify(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    if args.provider != "pic":
        raise CCRMissingError(
            f"unknown verifier provider: {args.provider}",
            {"ok": False, "provider": args.provider, "error": "unknown verifier provider"},
        )
    packet, packet_path, _status = load_packet(root, args.packet_id)
    provider = PicVerifierProvider()
    availability = provider.availability()
    plan = provider.plan_verify(packet, profile=args.profile, packet_path=str(packet_path))
    if not availability.get("available"):
        residual = build_residual(
            kind="provider_missing",
            description="PIC provider is unavailable; verifier execution was not attempted.",
            blocking=False,
            object_type="packet",
            object_id=str(args.packet_id),
            refs=[str(packet_path)],
            source="ccr.verify.pic",
            repair_hint="Install PIC or import a PIC-compatible verifier report.",
        )
        payload = {
            "availability": availability,
            "error": "PIC provider is unavailable; dry-run plan returned without execution.",
            "ok": False,
            "plan": plan,
            "residual_ready": residual,
        }
        _emit_json(payload)
        return EXIT_MISSING
    if not args.execute:
        _emit_json({"availability": availability, "ok": True, "plan": plan})
        return EXIT_SUCCESS
    report = provider.execute_verify(
        packet,
        profile=args.profile,
        packet_path=str(packet_path),
        timeout_seconds=int(args.timeout),
    )
    if not report.get("ok"):
        _emit_json(report)
        if "unavailable" in str(report.get("error", "")).lower():
            return EXIT_MISSING
        return EXIT_POLICY_FAILURE
    report_id = stable_id("pic-report", report)
    report["report_id"] = report_id
    destination = report_output_path(root, report_id)
    write_json_atomic(destination, report, overwrite=True)
    append_event(
        root,
        make_event(
            action="verify.pic.execute",
            object_type="report",
            object_id=report_id,
            status_before=None,
            status_after="created",
            refs=[args.packet_id],
        ),
    )
    _emit_json({"ok": True, "path": str(destination), "report": report})
    return EXIT_SUCCESS


def cmd_integrate(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    report_path = Path(args.report)
    report = _read_object(report_path)
    provider = PicVerifierProvider()
    normalized = provider.normalize_report(report)
    import_id = str(normalized["import_id"])
    original_path = report_output_path(root, f"{import_id}-original")
    normalized_path = report_output_path(root, import_id)
    write_json_atomic(original_path, report, overwrite=True)
    write_json_atomic(normalized_path, normalized, overwrite=True)

    residual_ids = _materialize_provider_residuals(root, normalized, "pic")
    task_ids = _materialize_provider_safe_command_tasks(root, normalized, "pic")
    packet_update = _apply_provider_packet_update(
        root, normalized, normalized_path, residual_ids, "pic"
    )
    append_event(
        root,
        make_event(
            action="integrate.pic",
            object_type="report",
            object_id=import_id,
            status_before=None,
            status_after=str(normalized["ccr_status"]),
            refs=[str(report_path), str(original_path), str(normalized_path)],
            residuals=residual_ids,
            note="PIC report imported without executing safe commands.",
        ),
    )
    _emit_json(
        {
            "import_id": import_id,
            "normalized": normalized,
            "normalized_path": str(normalized_path),
            "ok": True,
            "original_report_path": str(original_path),
            "packet_update": packet_update,
            "residuals": residual_ids,
            "task_hints": task_ids,
        }
    )
    return EXIT_SUCCESS


def cmd_provider_list(args: argparse.Namespace) -> int:
    providers = []
    for provider in list_providers():
        providers.append(
            {
                "capabilities": provider.capabilities(),
                "health": provider.health(),
                "provider": provider.provider_name,
            }
        )
    _emit_json({"ok": True, "providers": providers})
    return EXIT_SUCCESS


def cmd_provider_health(args: argparse.Namespace) -> int:
    provider = _get_provider_or_raise(args.provider)
    health = provider.health()
    _emit_json({"health": health, "ok": True, "provider": provider.provider_name})
    return EXIT_SUCCESS


def cmd_provider_plan(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    provider = _get_provider_or_raise(args.provider)
    payload = _provider_payload(args)
    plan = provider.plan(action=args.action, payload=payload, root=root)
    run_id = stable_id("provider-plan", provider.provider_name, args.action, payload, plan)
    record_provider_run(
        root,
        run_id=run_id,
        provider=provider.provider_name,
        action=args.action,
        status="planned",
        dry_run=True,
    )
    _emit_json(
        {
            "dry_run": True,
            "network_call_performed": False,
            "ok": True,
            "plan": plan,
            "provider": provider.provider_name,
            "run_id": run_id,
            "schema_version": "ccr.provider_plan.v1",
        }
    )
    return EXIT_SUCCESS


def cmd_provider_execute(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    provider = _get_provider_or_raise(args.provider)
    payload = _provider_payload(args)
    config = _read_object(Path(args.config))
    if not args.execute:
        residual = build_residual(
            kind="authority_gap",
            description="Provider execution requires explicit --execute.",
            blocking=True,
            object_type="runtime",
            object_id=provider.provider_name,
            refs=[str(args.config)],
            source="ccr.provider",
            repair_hint="Rerun with --execute only when external authority is explicit.",
        )
        _emit_json(
            {
                "error": "provider execute requires explicit --execute",
                "ok": False,
                "provider": provider.provider_name,
                "residual_ready": residual,
            }
        )
        return EXIT_POLICY_FAILURE
    report = provider.execute(action=args.action, payload=payload, root=root, config=config)
    run_id = stable_id("provider-run", provider.provider_name, args.action, payload, report)
    report_payload = {
        "action": args.action,
        "config_digest": stable_id("provider-config", config),
        "dry_run": False,
        "ok": bool(report.get("ok")),
        "provider": provider.provider_name,
        "report": report,
        "run_id": run_id,
        "schema_version": "ccr.provider_run.v1",
    }
    if not report_payload["ok"]:
        report_payload["residual_ready"] = _provider_failure_residual(
            provider.provider_name, args.action, report
        )
    report_path = _provider_report_path(root, provider.provider_name, run_id)
    write_json_atomic(report_path, report_payload, overwrite=True)
    record_provider_run(
        root,
        run_id=run_id,
        provider=provider.provider_name,
        action=args.action,
        status="ok" if report_payload["ok"] else "failed",
        dry_run=False,
        report_path=str(report_path),
    )
    append_event(
        root,
        make_event(
            action=f"provider.{provider.provider_name}.execute",
            object_type="report",
            object_id=run_id,
            status_before=None,
            status_after="ok" if report_payload["ok"] else "failed",
            refs=[str(report_path)],
            note="Provider execution used explicit config and --execute.",
        ),
    )
    report_payload["path"] = str(report_path)
    _emit_json(report_payload)
    return EXIT_SUCCESS if report_payload["ok"] else EXIT_POLICY_FAILURE


def cmd_provider_import(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    provider = _get_provider_or_raise(args.provider)
    report_path = Path(args.report)
    report = _read_object(report_path)
    normalized = provider.normalize(report)
    import_id = str(normalized["import_id"])
    normalized_path = _provider_report_path(root, provider.provider_name, import_id)
    write_json_atomic(normalized_path, normalized, overwrite=True)
    residual_ids = _materialize_provider_residuals(root, normalized, provider.provider_name)
    task_ids = _materialize_provider_safe_command_tasks(root, normalized, provider.provider_name)
    packet_update = _apply_provider_packet_update(
        root, normalized, normalized_path, residual_ids, provider.provider_name
    )
    record_object(
        root,
        object_type="report",
        object_id=import_id,
        status=str(normalized.get("ccr_status", "imported")),
        path=normalized_path,
        content=normalized,
    )
    append_event(
        root,
        make_event(
            action=f"provider.{provider.provider_name}.import",
            object_type="report",
            object_id=import_id,
            status_before=None,
            status_after=str(normalized.get("ccr_status", "imported")),
            refs=[str(report_path), str(normalized_path)],
            residuals=residual_ids,
            note="Provider report imported; safe commands remain task hints only.",
        ),
    )
    _emit_json(
        {
            "import_id": import_id,
            "normalized": normalized,
            "normalized_path": str(normalized_path),
            "ok": True,
            "packet_update": packet_update,
            "provider": provider.provider_name,
            "residuals": residual_ids,
            "task_hints": task_ids,
        }
    )
    return EXIT_SUCCESS


def cmd_phase_graph(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    graph = build_effective_graph(root)
    path = _phase_artifact_path(root, "graphs", str(graph["graph_id"]))
    write_json_atomic(path, graph, overwrite=True)
    record_object(
        root,
        object_type="phase",
        object_id=str(graph["graph_id"]),
        status="graph",
        path=path,
        content=graph,
    )
    append_event(
        root,
        make_event(
            action="phase.graph",
            object_type="phase",
            object_id=str(graph["graph_id"]),
            status_before=None,
            status_after="graph",
            refs=[str(path)],
            note="Effective packet graph built without external execution.",
        ),
    )
    _emit_json({"graph": graph, "ok": True, "path": str(path)})
    return EXIT_SUCCESS


def cmd_phase_observe(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    graph = build_effective_graph(root)
    observation = build_phase_observation(root, graph)
    path = _phase_artifact_path(root, "observations", str(observation["observation_id"]))
    write_json_atomic(path, observation, overwrite=True)
    record_phase_observation(root, observation=observation, path=path)
    append_event(
        root,
        make_event(
            action="phase.observe",
            object_type="phase",
            object_id=str(observation["observation_id"]),
            status_before=None,
            status_after="observed",
            refs=[str(path)],
            note="Phase observation records execution availability without execution.",
        ),
    )
    _emit_json({"observation": observation, "ok": True, "path": str(path)})
    return EXIT_SUCCESS


def cmd_phase_threshold(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    threshold = _read_object(Path(args.file))
    if args.observation:
        observation = _read_object(Path(args.observation))
    else:
        observation = build_phase_observation(root)
    status = evaluate_threshold(observation, threshold)
    path = _phase_artifact_path(root, "thresholds", str(status["status_id"]))
    write_json_atomic(path, status, overwrite=True)
    record_object(
        root,
        object_type="phase",
        object_id=str(status["status_id"]),
        status=str(status["certificate_status"]),
        path=path,
        content=status,
    )
    append_event(
        root,
        make_event(
            action="phase.threshold",
            object_type="phase",
            object_id=str(status["status_id"]),
            status_before=None,
            status_after=str(status["certificate_status"]),
            refs=[str(args.file), str(path)],
            note="ASI-proxy threshold evaluated as protocol-relative status.",
        ),
    )
    _emit_json({"ok": True, "path": str(path), "threshold_status": status})
    return EXIT_SUCCESS if status.get("accepted") else EXIT_POLICY_FAILURE


def cmd_phase_compare(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    baseline = _read_object(Path(args.baseline))
    observation = _read_object(Path(args.candidate))
    baseline_result = validate_instance("baseline", baseline, root=root)
    observation_result = validate_instance("phase-observation", observation, root=root)
    if not baseline_result.ok:
        _emit_json(
            _validation_failure_payload(
                "baseline",
                baseline,
                Path(args.baseline),
                baseline_result.to_json(),
            )
        )
        return EXIT_POLICY_FAILURE
    if not observation_result.ok:
        _emit_json(
            _validation_failure_payload(
                "phase-observation", observation, Path(args.candidate), observation_result.to_json()
            )
        )
        return EXIT_POLICY_FAILURE
    comparison = compare_observation_to_baseline(baseline, observation)
    path = _phase_artifact_path(root, "comparisons", str(comparison["comparison_id"]))
    write_json_atomic(path, comparison, overwrite=True)
    record_object(
        root,
        object_type="phase",
        object_id=str(comparison["comparison_id"]),
        status="accepted" if comparison.get("accepted") else "diagnostic",
        path=path,
        content=comparison,
    )
    append_event(
        root,
        make_event(
            action="phase.compare",
            object_type="phase",
            object_id=str(comparison["comparison_id"]),
            status_before=None,
            status_after="accepted" if comparison.get("accepted") else "diagnostic",
            refs=[str(args.baseline), str(args.candidate), str(path)],
            note="Baseline comparison preserves resource mismatches as residual-ready diagnostics.",
        ),
    )
    _emit_json({"comparison": comparison, "ok": True, "path": str(path)})
    return EXIT_SUCCESS


def cmd_phase_form(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    result = run_phase_formation(root, profile=args.profile)
    _emit_json(result)
    return EXIT_SUCCESS


def cmd_phase_certify(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    graph = build_effective_graph(root)
    observation = build_phase_observation(root, graph)
    threshold = _read_object(Path(args.threshold)) if args.threshold else default_threshold()
    threshold_status = evaluate_threshold(observation, threshold)
    certificate = build_certificate_candidate(
        root,
        graph=graph,
        observation=observation,
        threshold=threshold,
        threshold_status=threshold_status,
    )
    path = _phase_artifact_path(root, "certificates", str(certificate["certificate_id"]))
    write_json_atomic(path, certificate, overwrite=True)
    record_object(
        root,
        object_type="phase",
        object_id=str(certificate["certificate_id"]),
        status=str(certificate["certificate_status"]),
        path=path,
        content=certificate,
    )
    append_event(
        root,
        make_event(
            action="phase.certify",
            object_type="phase",
            object_id=str(certificate["certificate_id"]),
            status_before=None,
            status_after=str(certificate["certificate_status"]),
            refs=[str(path)],
            note="CollectivePhaseCertificateCandidate generated; this is not real ASI proof.",
        ),
    )
    _emit_json({"certificate": certificate, "ok": True, "path": str(path)})
    return EXIT_SUCCESS


def cmd_phase_report(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    _emit_json({"ok": True, "report": phase_report(root)})
    return EXIT_SUCCESS


def cmd_phase_plan(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    if args.provider != "pic":
        raise CCRMissingError(
            f"unknown phase provider: {args.provider}",
            {"error": "unknown phase provider", "ok": False, "provider": args.provider},
        )
    provider = PicVerifierProvider()
    availability = provider.availability()
    plan = {
        "dry_run": True,
        "expected_import_command": "ccr integrate --report reports/pic/<report>.json --json",
        "phase_report": phase_report(root),
        "provider": "pic",
        "recommended_argv": [
            "pic",
            "phase",
            "plan",
            "--compact",
            "--profile",
            args.profile,
        ],
        "safe_command_policy": "task_hints_only",
    }
    _emit_json(
        {
            "availability": availability,
            "ok": bool(availability.get("available")),
            "plan": plan,
        }
    )
    return EXIT_SUCCESS if availability.get("available") else EXIT_MISSING


def cmd_report(args: argparse.Namespace) -> int:
    root = runtime_root(args.root)
    if args.format == "json":
        _emit_json({"ok": True, "report": phase_report(root)})
    else:
        sys.stdout.write(render_markdown_report(root))
    return EXIT_SUCCESS


def _materialize_pic_residuals(root: Path, normalized: dict[str, Any]) -> list[str]:
    residual_ids: list[str] = []
    packet_id = normalized.get("packet_id") or ""
    for reason in normalized.get("candidate_only_reasons", []):
        residual = build_residual(
            kind="candidate_only_reason",
            description=f"PIC candidate-only reason: {reason}",
            blocking=False,
            object_type="packet" if packet_id else "report",
            object_id=str(packet_id or normalized["import_id"]),
            refs=[str(normalized["import_id"])],
            source="pic",
            extensions={"source_pic_field": "candidate_only_reasons"},
        )
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
        append_event(
            root,
            make_event(
                action="residual.add",
                object_type="residual",
                object_id=str(residual["residual_id"]),
                status_before=None,
                status_after="open",
                refs=[str(normalized["import_id"])],
                residuals=[str(residual["residual_id"])],
            ),
        )
    for blocker in normalized.get("settled_blockers", []):
        residual = build_residual(
            kind="settlement_blocker",
            description=f"PIC settled blocker: {blocker}",
            blocking=True,
            object_type="packet" if packet_id else "report",
            object_id=str(packet_id or normalized["import_id"]),
            refs=[str(normalized["import_id"])],
            source="pic",
            extensions={"source_pic_field": "settled_blockers"},
        )
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
        append_event(
            root,
            make_event(
                action="residual.add",
                object_type="residual",
                object_id=str(residual["residual_id"]),
                status_before=None,
                status_after="open",
                refs=[str(normalized["import_id"])],
                residuals=[str(residual["residual_id"])],
            ),
        )
    return residual_ids


def _materialize_safe_command_tasks(root: Path, normalized: dict[str, Any]) -> list[str]:
    task_ids: list[str] = []
    for command in normalized.get("safe_commands", []):
        task_id = stable_id("task:pic-safe-command", normalized["import_id"], command)
        task = {
            "blackboard_refs": [],
            "completion": {},
            "constraints": {
                "allowed_commands": [],
                "authority_policy": "read_only",
                "forbidden_actions": ["automatic_execution", "shell_expansion"],
                "max_runtime_minutes": 30,
                "network_policy": "none",
                "side_effect_policy": "dry_run_only",
            },
            "created_at": now_iso(),
            "dependencies": [],
            "expected_outputs": [
                {
                    "acceptance_criteria": [
                        "Operator reviews the hint and decides whether separate authority exists."
                    ],
                    "destination": "tasks/open",
                    "kind": "json",
                    "schema_ref": "schemas/task.schema.json",
                }
            ],
            "extensions": {"x_safe_command_hint": command},
            "inputs": [
                {
                    "kind": "text",
                    "notes": str(command),
                    "ref": f"pic.safe_command:{normalized['import_id']}",
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
            "objective": "Review a PIC safe command hint without executing it automatically.",
            "pic_interop": {
                "candidate_only_until_checked": True,
                "enabled": True,
                "identity_context_required": False,
                "input_mapping": "none",
                "output_mapping": "none",
                "pic_profile": str(normalized.get("pic_profile", "development")),
                "recommended_pic_commands": [],
            },
            "priority": 30,
            "residual_policy": {
                "blocking_residuals_prevent_settlement": True,
                "minimum_residual_fields": [
                    "residual_id",
                    "kind",
                    "description",
                    "blocking",
                ],
                "preserve_residuals": True,
                "residual_destination": "residuals/open",
            },
            "role": "pic_adapter",
            "schema_version": "ccr.task.v0.1",
            "status": "open",
            "task_id": task_id,
            "title": "Review PIC safe command hint",
            "verifier_plan": {
                "failure_route": "residual",
                "optional_verifiers": ["human"],
                "promotion_gate": "none",
                "required_verifiers": [],
            },
        }
        result = validate_task(task, root=root)
        if not result.ok:
            continue
        with suppress(FileExistsError):
            submit_task(root, task)
        task_ids.append(task_id)
        append_event(
            root,
            make_event(
                action="task.hint.create",
                object_type="task",
                object_id=task_id,
                status_before=None,
                status_after="open",
                refs=[str(normalized["import_id"])],
                note="PIC safe command preserved as non-executed task hint.",
            ),
        )
    return task_ids


def _apply_pic_packet_update(
    root: Path,
    normalized: dict[str, Any],
    normalized_path: Path,
    residual_ids: list[str],
) -> dict[str, Any] | None:
    packet_id = normalized.get("packet_id")
    if not packet_id:
        return None
    try:
        packet, old_path, status_before = load_packet(root, str(packet_id))
    except FileNotFoundError:
        return {"error": "packet not found", "packet_id": packet_id}
    report_id = stable_id("verifier-report:pic", normalized)
    report_ref = {
        "accepted": bool(normalized["accepted"]),
        "blocking_residuals": residual_ids,
        "provider": "pic",
        "ref": str(normalized_path),
        "report_id": report_id,
        "settled": bool(normalized["settled"]),
    }
    packet.setdefault("verifier_reports", [])
    packet["verifier_reports"].append(report_ref)
    target_status = str(normalized["ccr_status"])
    if target_status == "settled":
        target_status = "checked"
    packet["updated_at"] = now_iso()
    save_packet_at_status(root, packet, status=target_status, old_path=old_path)
    append_event(
        root,
        make_event(
            action="packet.pic_import",
            object_type="packet",
            object_id=str(packet_id),
            status_before=status_before,
            status_after=target_status,
            refs=[str(normalized_path)],
            residuals=residual_ids,
            note="PIC import never grants final CCR settlement.",
        ),
    )
    return {"packet_id": packet_id, "status_after": target_status, "status_before": status_before}


def _get_provider_or_raise(name: str) -> Provider:
    try:
        return get_provider(name)
    except KeyError as exc:
        raise CCRMissingError(
            f"unknown provider: {name}",
            {"error": "unknown provider", "ok": False, "provider": name},
        ) from exc


def _provider_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if getattr(args, "file", None):
        payload.update(_read_object(Path(args.file)))
    if getattr(args, "packet_id", None):
        payload["packet_id"] = args.packet_id
    if getattr(args, "profile", None):
        payload["profile"] = args.profile
    return payload


def _provider_report_path(root: Path, provider_name: str, report_id: str) -> Path:
    return root / "reports" / "providers" / provider_name / json_file_name(report_id)


def _phase_artifact_path(root: Path, directory: str, object_id: str) -> Path:
    return root / "phase" / directory / json_file_name(object_id)


def _provider_failure_residual(
    provider_name: str, action: str, report: dict[str, Any]
) -> dict[str, Any]:
    error = str(report.get("error", "provider action failed"))
    kind = "provider_missing" if "unavailable" in error.lower() else "settlement_blocker"
    return build_residual(
        kind=kind,
        description=f"Provider {provider_name} action {action} failed: {error}",
        blocking=kind != "provider_missing",
        object_type="report",
        object_id=stable_id("provider-failure", provider_name, action, report),
        refs=[],
        source=f"ccr.provider.{provider_name}",
        repair_hint="Inspect the provider report, fix configuration or route a repair task.",
        extensions={"provider_report": report},
    )


def _materialize_provider_residuals(
    root: Path, normalized: dict[str, Any], provider_name: str
) -> list[str]:
    residual_ids: list[str] = []
    packet_id = str(normalized.get("packet_id") or "")
    import_id = str(normalized["import_id"])
    for reason in normalized.get("candidate_only_reasons", []):
        residual_ids.append(
            _save_provider_residual(
                root,
                provider_name,
                import_id,
                packet_id,
                kind="candidate_only_reason",
                description=f"{provider_name} candidate-only reason: {reason}",
                blocking=False,
                field="candidate_only_reasons",
                raw_value=reason,
            )
        )
    for blocker in normalized.get("settled_blockers", []):
        residual_ids.append(
            _save_provider_residual(
                root,
                provider_name,
                import_id,
                packet_id,
                kind="settlement_blocker",
                description=f"{provider_name} settled blocker: {blocker}",
                blocking=True,
                field="settled_blockers",
                raw_value=blocker,
            )
        )
    for obligation in normalized.get("missing_obligations", []):
        residual_ids.append(
            _save_provider_residual(
                root,
                provider_name,
                import_id,
                packet_id,
                kind="settlement_blocker",
                description=f"{provider_name} missing obligation: {obligation}",
                blocking=True,
                field="missing_obligations",
                raw_value=obligation,
            )
        )
    for reason in normalized.get("cannot_promote_because", []):
        residual_ids.append(
            _save_provider_residual(
                root,
                provider_name,
                import_id,
                packet_id,
                kind="settlement_blocker",
                description=f"{provider_name} cannot promote because: {reason}",
                blocking=True,
                field="cannot_promote_because",
                raw_value=reason,
            )
        )
    for provider_residual in normalized.get("residuals", []):
        description = (
            str(provider_residual.get("description", provider_residual))
            if isinstance(provider_residual, dict)
            else str(provider_residual)
        )
        blocking = (
            bool(provider_residual.get("blocking", False))
            if isinstance(provider_residual, dict)
            else False
        )
        residual_ids.append(
            _save_provider_residual(
                root,
                provider_name,
                import_id,
                packet_id,
                kind="settlement_blocker" if blocking else "other",
                description=f"{provider_name} residual: {description}",
                blocking=blocking,
                field="residuals",
                raw_value=provider_residual,
            )
        )
    return residual_ids


def _save_provider_residual(
    root: Path,
    provider_name: str,
    import_id: str,
    packet_id: str,
    *,
    kind: str,
    description: str,
    blocking: bool,
    field: str,
    raw_value: Any,
) -> str:
    residual = build_residual(
        kind=kind,
        description=description,
        blocking=blocking,
        object_type="packet" if packet_id else "report",
        object_id=packet_id or import_id,
        refs=[import_id],
        source=f"ccr.provider.{provider_name}",
        extensions={"raw_value": raw_value, "source_provider_field": field},
    )
    save_residual(root, residual, overwrite=True)
    append_event(
        root,
        make_event(
            action="residual.add",
            object_type="residual",
            object_id=str(residual["residual_id"]),
            status_before=None,
            status_after="open",
            refs=[import_id],
            residuals=[str(residual["residual_id"])],
        ),
    )
    return str(residual["residual_id"])


def _materialize_provider_safe_command_tasks(
    root: Path, normalized: dict[str, Any], provider_name: str
) -> list[str]:
    task_ids: list[str] = []
    for command in normalized.get("safe_commands", []):
        task_id = stable_id(
            "task:provider-safe-command",
            provider_name,
            normalized["import_id"],
            command,
        )
        task = {
            "blackboard_refs": [],
            "completion": {},
            "constraints": {
                "allowed_commands": [],
                "authority_policy": "read_only",
                "forbidden_actions": ["automatic_execution", "shell_expansion"],
                "max_runtime_minutes": 30,
                "network_policy": "none",
                "side_effect_policy": "dry_run_only",
            },
            "created_at": now_iso(),
            "dependencies": [],
            "expected_outputs": [
                {
                    "acceptance_criteria": [
                        "Operator reviews the provider hint and decides whether authority exists."
                    ],
                    "destination": "tasks/open",
                    "kind": "json",
                    "schema_ref": "schemas/task.schema.json",
                }
            ],
            "extensions": {"x_provider_safe_command_hint": command, "x_provider": provider_name},
            "inputs": [
                {
                    "kind": "text",
                    "notes": str(command),
                    "ref": f"{provider_name}.safe_command:{normalized['import_id']}",
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
            "objective": "Review a provider safe command hint without executing it automatically.",
            "pic_interop": {
                "candidate_only_until_checked": True,
                "enabled": provider_name == "pic",
                "identity_context_required": False,
                "input_mapping": "none",
                "output_mapping": "none",
                "pic_profile": "development",
                "recommended_pic_commands": [],
            },
            "priority": 30,
            "residual_policy": {
                "blocking_residuals_prevent_settlement": True,
                "minimum_residual_fields": [
                    "residual_id",
                    "kind",
                    "description",
                    "blocking",
                ],
                "preserve_residuals": True,
                "residual_destination": "residuals/open",
            },
            "role": "integrator",
            "schema_version": "ccr.task.v0.1",
            "status": "open",
            "task_id": task_id,
            "title": "Review provider safe command hint",
            "verifier_plan": {
                "failure_route": "residual",
                "optional_verifiers": ["human"],
                "promotion_gate": "none",
                "required_verifiers": [],
            },
        }
        result = validate_task(task, root=root)
        if not result.ok:
            continue
        with suppress(FileExistsError):
            submit_task(root, task)
        task_ids.append(task_id)
        append_event(
            root,
            make_event(
                action="task.hint.create",
                object_type="task",
                object_id=task_id,
                status_before=None,
                status_after="open",
                refs=[str(normalized["import_id"])],
                note="Provider safe command preserved as non-executed task hint.",
            ),
        )
    return task_ids


def _apply_provider_packet_update(
    root: Path,
    normalized: dict[str, Any],
    normalized_path: Path,
    residual_ids: list[str],
    provider_name: str,
) -> dict[str, Any] | None:
    packet_id = normalized.get("packet_id")
    if not packet_id:
        return None
    try:
        packet, old_path, status_before = load_packet(root, str(packet_id))
    except FileNotFoundError:
        return {"error": "packet not found", "packet_id": packet_id}
    report_id = stable_id(f"verifier-report:{provider_name}", normalized)
    packet.setdefault("verifier_reports", [])
    packet["verifier_reports"].append(
        {
            "accepted": bool(normalized.get("accepted")),
            "blocking_residuals": residual_ids,
            "provider": provider_name,
            "ref": str(normalized_path),
            "report_id": report_id,
            "settled": bool(normalized.get("settled")),
        }
    )
    target_status = str(normalized.get("ccr_status", "provisional"))
    if target_status == "settled":
        target_status = "checked"
    if target_status not in {"checked", "provisional", "rejected", "quarantined"}:
        target_status = "provisional"
    packet["updated_at"] = now_iso()
    save_packet_at_status(root, packet, status=target_status, old_path=old_path)
    append_event(
        root,
        make_event(
            action=f"packet.{provider_name}_import",
            object_type="packet",
            object_id=str(packet_id),
            status_before=status_before,
            status_after=target_status,
            refs=[str(normalized_path)],
            residuals=residual_ids,
            note="Provider import never grants final CCR settlement.",
        ),
    )
    return {"packet_id": packet_id, "status_after": target_status, "status_before": status_before}


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = read_json(path)
    if not isinstance(data, dict):
        raise CCRMissingError(
            f"{path} must contain a JSON object",
            {"error": "file is not a JSON object", "file": str(path), "ok": False},
        )
    return data


def _validation_failure_payload(
    object_type: str,
    data: dict[str, Any],
    path: Path,
    validation: dict[str, Any],
) -> dict[str, Any]:
    object_id = str(
        data.get(f"{object_type}_id")
        or data.get("packet_id")
        or data.get("task_id")
        or data.get("residual_id")
        or path
    )
    residual = build_residual(
        kind="validation_error",
        description=f"{object_type} validation failed for {path}",
        blocking=True,
        object_type=object_type if object_type in {"packet", "task", "report"} else "unknown",
        object_id=object_id,
        refs=[str(path)],
        source="ccr.schema.validation",
        extensions={"validation_errors": validation.get("errors", [])},
    )
    return {
        "errors": validation.get("errors", []),
        "kind": object_type,
        "ok": False,
        "residual_ready": residual,
        "schema_version": validation.get("schema_version"),
    }


def _emit_json(payload: Any) -> None:
    sys.stdout.write(pretty_dumps(payload))
    sys.stdout.write("\n")
