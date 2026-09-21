# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from ccr.optimizer import native_artifacts, native_cli
from ccr.optimizer.native_wire import loads, rational
from tests.test_native_interchange import FIXTURES, native, setup_run


def parser(root: Path) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.set_defaults(root=str(root))
    commands = result.add_subparsers()
    native_cli.register(commands)
    return result


def test_native_cli_inspection_does_not_initialize(tmp_path: Path, capsys: Any) -> None:
    root = tmp_path / "absent"
    p = parser(root)
    for command in (["sources"], ["inspect", "--file", str(FIXTURES / "alt.json")]):
        assert native_cli.execute(p.parse_args(["native", *command])) == 0
        assert json.loads(capsys.readouterr().out)
    assert not root.exists()
    assert native_cli.execute(p.parse_args(["native", "inspect", "--file", str(root)])) == 2
    assert not json.loads(capsys.readouterr().out)["ok"]
    huge = tmp_path / "oversized"
    huge.write_bytes(b" " * 2_000_001)
    with pytest.raises(ValueError, match="byte limit"):
        native_cli.read(str(huge))


@native
def test_native_cli_roundtrip(tmp_path: Path, capsys: Any) -> None:
    _, _store, run_id, source, registration = setup_run(tmp_path)
    p = parser(tmp_path)
    raw_file = tmp_path / "source.json"
    raw_file.write_bytes(source)
    reg_file = tmp_path / "registration.json"
    reg_file.write_text(json.dumps(registration), encoding="utf-8")

    def invoke(*args: str) -> dict[str, Any]:
        assert native_cli.execute(p.parse_args(["native", *args])) == 0
        return json.loads(capsys.readouterr().out)

    projected = invoke("project", "--file", str(raw_file), "--registration", str(reg_file))
    projection_file = tmp_path / "projection.json"
    projection_file.write_text(json.dumps(projected), encoding="utf-8")
    invoke("register", "--run", run_id, "--registration", str(reg_file), "--expected-revision", "0")
    args = ("--run", run_id, "--file", str(raw_file), "--projection", str(projection_file))
    assert invoke("check", *args)["ok"]
    staged = invoke("stage", *args, "--expected-revision", "1", "--idempotency-key", "cli")
    invoke(
        "admit", "--run", run_id, "--proposal-id", staged["proposal_id"], "--expected-revision", "2"
    )
    for command in ("status", "replay"):
        report = invoke(command, "--run", run_id)
        assert report["revision"] == 3 and not report["mutated_runtime"]
    assert invoke("replan", "--run", run_id, "--file", str(raw_file))["producer"] == "cpcf"


def test_source_schema_hash_pins_fail_closed(tmp_path: Path, monkeypatch: Any) -> None:
    path = tmp_path / "source.py"
    path.write_bytes(b"original")
    from ccr.optimizer.native_wire import raw_digest

    pin = {"package": "synthetic", "version": "1", "files": {"source.py": raw_digest(b"original")}}

    class Distribution:
        version = "1"

        def locate_file(self, relative: str) -> Path:
            return tmp_path / relative

    distribution = Distribution()
    monkeypatch.setattr(native_artifacts, "manifest", lambda: {"test": pin})
    monkeypatch.setattr(native_artifacts.metadata, "distribution", lambda _: distribution)
    assert len(native_artifacts.verify("test")) == 64
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        native_artifacts.verify("test")
    distribution.version = "2"
    with pytest.raises(ValueError, match="version mismatch"):
        native_artifacts.verify("test")


def test_finite_parser_remaining_bounds() -> None:
    with pytest.raises(ValueError, match="object limit"):
        loads(json.dumps({str(i): i for i in range(513)}).encode())
    with pytest.raises(ValueError, match="node limit"):
        loads(json.dumps({"rows": [[0] * 500 for _ in range(100)]}).encode())
    with pytest.raises(ValueError, match="oversized"):
        rational(str(2**128))


@native
def test_native_integrated_example_has_independent_finite_accounting_oracle(
    tmp_path: Path, capsys: Any, monkeypatch: Any
) -> None:
    import socket

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("offline example attempted network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.chdir(tmp_path)
    p = parser(tmp_path / "not-created")
    assert native_cli.execute(p.parse_args(["native", "example"])) == 0
    report = json.loads(capsys.readouterr().out)
    # Independent finite oracle: eight physical attempts at two declared units,
    # one formation, four distinct service tasks, no service from either check.
    assert len(report["trace"]) == len({r["trial_id"] for r in report["trace"]}) == 8
    assert report["first_cycle"]["actual_costs"] == {"cost": 16}
    assert report["first_cycle"]["asset_count"] == 1
    assert report["first_cycle"]["observed_service"] == {"task": 4, "research": 4}
    assert report["clock_mode"] == "explicit_finite_simulation"
    assert report["second_cycle_next_action"] == "review"
    assert report["feedback"]["reward_added"] == report["feedback"]["asset_stock_added"] == 0
    assert report["after_reconciliation"]["actual_costs"] == {"cost": 16}
    assert list(tmp_path.iterdir()) == []


@native
def test_native_cli_accounting_roundtrip(tmp_path: Path, capsys: Any) -> None:
    import importlib

    from tests.test_native_accounting_faults import history

    _, run_id, _ = history(tmp_path)
    p = parser(tmp_path)
    assert native_cli.execute(p.parse_args(["native", "export", "--run", run_id])) == 0
    exported = json.loads(capsys.readouterr().out)
    report = importlib.import_module("cait_schema.accounting.report").analyze(exported["bundle"])
    export_file, report_file = tmp_path / "export.json", tmp_path / "report.json"
    export_file.write_text(json.dumps(exported), encoding="utf-8")
    report_file.write_text(json.dumps(report), encoding="utf-8")
    args = ["--run", run_id, "--export", str(export_file), "--report", str(report_file)]
    assert native_cli.execute(p.parse_args(["native", "feedback", *args])) == 0
    assert json.loads(capsys.readouterr().out)["complete"]
    assert (
        native_cli.execute(
            p.parse_args(
                ["native", "reconcile", *args, "--expected-revision", str(exported["revision"])]
            )
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["reward_added"] == 0
