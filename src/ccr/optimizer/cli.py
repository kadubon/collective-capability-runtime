# SPDX-License-Identifier: Apache-2.0
"""Optimizer CLI registration, kept separate from the legacy command module."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ccr.io import pretty_dumps, read_json
from ccr.optimizer import engine
from ccr.paths import runtime_root
from ccr.storage.control import ControlStore


def register(sub: Any) -> None:
    parser = sub.add_parser("optimizer", help="Optimize verified capability under fixed budgets.")
    commands = parser.add_subparsers(dest="optimizer_command", required=True)
    for name in (
        "init",
        "plan",
        "step",
        "run",
        "ingest",
        "status",
        "report",
        "stop",
        "freeze",
        "claim",
        "heartbeat",
        "export",
    ):
        command = commands.add_parser(name)
        command.add_argument("--json", action="store_true", dest="json_output")
        command.add_argument("--database-url-env", default="CCR_DATABASE_URL")
        if name == "init":
            command.add_argument("--mission", required=True)
        else:
            command.add_argument("--run", required=True)
        if name in {"init", "run"}:
            command.add_argument("--config", required=True)
        if name == "step":
            command.add_argument("--apply", action="store_true")
            command.add_argument("--expected-revision", type=int)
        if name == "run":
            command.add_argument("--execute", action="store_true")
        if name == "ingest":
            command.add_argument("--file", required=True)
        if name in {"claim", "run", "heartbeat"}:
            command.add_argument("--trial", required=True)
            command.add_argument("--worker", required=True)
        if name in {"run", "heartbeat"}:
            command.add_argument("--fencing-token", type=int, required=True)
        command.set_defaults(func=execute)


def object_file(path: str) -> dict[str, Any]:
    data = read_json(Path(path))
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    return data


def execute(args: argparse.Namespace) -> int:
    store = ControlStore(runtime_root(args.root), os.getenv(args.database_url_env, ""))
    name = args.optimizer_command
    if name == "init":
        try:
            result = engine.initialize(store, mission=args.mission, config=object_file(args.config))
        except ValueError as exc:
            result = engine.response(ok=False, blockers=[str(exc)])
    elif name == "step":
        result = engine.step(
            store, args.run, apply=args.apply, expected_revision=args.expected_revision
        )
    elif name == "run":
        result = engine.dispatch(
            store,
            args.run,
            trial_id=args.trial,
            worker=args.worker,
            token=args.fencing_token,
            config=object_file(args.config),
            execute=args.execute,
        )
    elif name == "ingest":
        result = engine.ingest(store, args.run, object_file(args.file))
    elif name == "export":
        engine.load(store, args.run)
        result = engine.response(exports=store.export(args.run), mutated_runtime=True)
    elif name == "claim":
        result = engine.claim(store, args.run, args.trial, worker=args.worker)
    elif name == "heartbeat":
        result = engine.task_transition(
            store, args.run, args.trial, worker=args.worker, token=args.fencing_token
        )
    else:
        functions = {
            "plan": engine.plan,
            "status": engine.report,
            "report": engine.report,
            "stop": engine.stop,
            "freeze": engine.freeze,
        }
        result = functions[name](store, args.run)
    print(pretty_dumps(result))
    return 0 if result["ok"] else 4
