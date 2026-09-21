# SPDX-License-Identifier: Apache-2.0
"""Explicit native interchange commands; inspection never initializes storage."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ccr.io import pretty_dumps
from ccr.optimizer import (
    engine,
    native_accounting,
    native_checks,
    native_projection,
    native_projection_check,
    native_replan,
    native_runtime,
)
from ccr.optimizer.native_wire import MAX_BYTES, loads
from ccr.paths import runtime_root
from ccr.storage.control import ControlStore


def register(commands: Any) -> None:
    parser = commands.add_parser("native", help="Opt-in pinned native companion interchange.")
    sub = parser.add_subparsers(dest="native_command", required=True)
    for name in (
        "sources",
        "example",
        "inspect",
        "project",
        "check",
        "register",
        "stage",
        "admit",
        "export",
        "feedback",
        "reconcile",
        "replan",
        "status",
        "replay",
    ):
        command = sub.add_parser(name)
        command.add_argument("--json", action="store_true", dest="json_output")
        if name in {"inspect", "project", "check", "stage", "replan"}:
            command.add_argument("--file", required=True)
        if name in {"project", "register"}:
            command.add_argument("--registration", required=True)
        if name in {"check", "stage"}:
            command.add_argument("--projection", required=True)
        if name not in {"sources", "example", "inspect", "project"}:
            command.add_argument("--run", required=True)
            command.add_argument("--database-url-env", default="CCR_DATABASE_URL")
        if name in {"register", "stage", "admit", "reconcile"}:
            command.add_argument("--expected-revision", type=int, required=True)
        if name == "stage":
            command.add_argument("--idempotency-key", required=True)
        if name == "admit":
            command.add_argument("--proposal-id", required=True)
        if name in {"feedback", "reconcile"}:
            command.add_argument("--export", required=True)
            command.add_argument("--report", required=True)
        command.set_defaults(func=execute)


def read(path: str) -> bytes:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("native source byte limit")
    return raw


def execute(args: argparse.Namespace) -> int:
    try:
        result = invoke(args)
    except (ValueError, KeyError, OSError, ImportError) as exc:
        result = engine.response(ok=False, blockers=[str(exc)])
    print(pretty_dumps(result))
    return 0 if result.get("ok", True) else 2


def invoke(args: argparse.Namespace) -> dict[str, Any]:
    name = args.native_command
    if name == "example":
        from ccr.optimizer.native_example import run_example

        return run_example()
    if name == "sources":
        return {
            "supported": {
                k: {"package": v[0], "version": v[1]} for k, v in native_checks.PACKAGES.items()
            },
            "evidence_mode": "synthetic",
            "source_authentication": "unestablished",
            "ccr_admission": False,
            "continuation_guarantee_transferred": False,
            "status": "development; release qualification incomplete",
        }
    if name == "inspect":
        return native_checks.inspect(read(args.file))
    if name == "project":
        return native_projection.project(read(args.file), loads(read(args.registration)))
    store = ControlStore(runtime_root(args.root), os.getenv(args.database_url_env, ""))
    if name == "register":
        return native_runtime.register(
            store,
            args.run,
            loads(read(args.registration)),
            expected_revision=args.expected_revision,
        )
    if name == "stage":
        return native_runtime.stage(
            store,
            args.run,
            read(args.file),
            loads(read(args.projection)),
            expected_revision=args.expected_revision,
            idempotency_key=args.idempotency_key,
        )
    if name == "admit":
        return native_runtime.admit(
            store, args.run, args.proposal_id, expected_revision=args.expected_revision
        )
    if name == "reconcile":
        return native_accounting.reconcile(
            store,
            args.run,
            loads(read(args.export)),
            loads(read(args.report)),
            expected_revision=args.expected_revision,
        )
    run = engine.load(store, args.run)
    if name == "check":
        return native_projection_check.check(run, read(args.file), loads(read(args.projection)))
    if name == "export":
        return native_accounting.export(run, store.now())
    if name == "feedback":
        return native_accounting.check_feedback(
            run, loads(read(args.export)), loads(read(args.report)), store.now()
        )
    if name == "replan":
        return loads(native_replan.cpcf(run, read(args.file)))
    report = engine.report(store, args.run)
    return {
        "ok": True,
        "revision": run["revision"],
        "registration": run.get("native_registration"),
        "admitted": run.get("native_admitted", {}),
        "feedback": run.get("native_feedback", {}),
        "verification_work": native_runtime.verification_work(run, store.now()),
        "ledgers": report.get("ledgers", {}),
        "next_action": report.get("next_action"),
        "mutated_runtime": False,
    }
