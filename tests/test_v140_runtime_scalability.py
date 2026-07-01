from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.extensions import (
    cache_invalidation,
    cache_rebuild,
    foundry_dashboard,
    foundry_frontier,
    foundry_smooth_next,
    graph_quotient,
    performance_bench,
    performance_report,
    token_dedup,
    token_distill,
    token_import,
    token_next,
)
from ccr.packets.store import submit_packet


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[object]) -> Path:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _packet(packet_id: str, claim: str) -> dict[str, Any]:
    return {
        "body": {"claim": claim},
        "created_at": "2026-07-01T00:00:00Z",
        "created_by": "agent:test",
        "packet_id": packet_id,
        "schema_version": "ccr.packet.v0.1",
        "status": "checked",
        "title": claim,
    }


def test_token_import_dedup_and_next_preserve_candidate_boundary(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    trace_report = token_distill(
        runtime_root,
        trace={
            "provenance": {"source": "fixture"},
            "steps": [{"step": "inspect"}],
            "task_context": "local",
            "trace_id": "trace:v140",
        },
    )
    token_path = _write_json(tmp_path / "token.json", trace_report)
    imported = token_import(runtime_root, file=token_path, provider="pic")
    duplicate_path = _write_json(
        tmp_path / "token-duplicate.json",
        {
            "candidate_token": {
                "claim": "same reusable verifier route",
                "token_id": "token:duplicate",
            }
        },
    )
    token_import(runtime_root, file=duplicate_path, provider="pic")
    dedup = token_dedup(runtime_root)
    next_report = token_next(runtime_root)

    assert imported["capital_admitted"] is False
    assert imported["settled"] is False
    assert (runtime_root / "tokens" / "candidate").is_dir()
    assert dedup["settled"] is False
    assert "duplicate_mass_cannot_increase_support" in dedup["non_claims"]
    assert next_report["mode"] == "advisory"
    assert next_report["recommended_action"]["external_execution"] is False


def test_duplicate_packets_do_not_inflate_foundry_or_graph_support(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    submit_packet(runtime_root, _packet("packet:1", "same claim"))
    submit_packet(runtime_root, _packet("packet:2", "same claim"))
    packets = _write_jsonl(
        tmp_path / "packets.jsonl",
        [
            {"packet_id": "packet:1", "claim": "same claim"},
            {"packet_id": "packet:2", "claim": "same claim"},
        ],
    )

    dashboard = foundry_dashboard(runtime_root)
    quotient = graph_quotient(runtime_root, packets_file=packets)
    smooth = foundry_smooth_next(runtime_root)
    frontier = foundry_frontier(runtime_root)

    assert dashboard["metrics"]["duplicate_mass_count"] >= 1
    assert dashboard["metrics"]["canonical_packet_count"] == 1
    assert quotient["duplicate_mass_count"] == 1
    assert smooth["mode"] == "advisory"
    assert frontier["schema_version"] == "ccr.foundry_frontier.v1"


def test_performance_cache_and_index_reports_are_local_only(
    runtime_root: Path,
    tmp_path: Path,
) -> None:
    cache_input = _write_json(tmp_path / "cache-input.json", {"coordinates": ["coord:x"]})

    rebuild = cache_rebuild(runtime_root, scope="all")
    invalidation = cache_invalidation(runtime_root, file=cache_input)
    report = performance_report(runtime_root)
    bench = performance_bench(runtime_root, objects=3)

    assert rebuild["ok"] is True
    assert rebuild["settled"] is False
    assert invalidation["dirty_set"] == ["coord:x"]
    assert report["schema_version"] == "ccr.performance_report.v1"
    assert report["index_rebuild_required"] is False
    assert bench["local_only"] is True
    assert bench["network_call_performed"] is False
    assert (runtime_root / "ccr.sqlite").is_file()
    with sqlite3.connect(runtime_root / "ccr.sqlite") as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"packets", "residuals", "tasks", "capital_witnesses"}.issubset(tables)


def test_cli_token_performance_cache_and_bundle_assets(
    runtime_root: Path,
    tmp_path: Path,
    capsys: Any,
) -> None:
    trace = _write_json(
        tmp_path / "trace.json",
        {
            "provenance": {"source": "fixture"},
            "steps": [{"step": "inspect"}],
            "task_context": "local",
            "trace_id": "trace:v140-cli",
        },
    )

    assert (
        main(["--root", str(runtime_root), "token", "distill", "--trace", str(trace), "--json"])
        == 0
    )
    token_payload = json.loads(capsys.readouterr().out)
    assert token_payload["schema_version"] == "ccr.token_distill.v1"

    assert main(["--root", str(runtime_root), "performance", "report", "--json"]) == 0
    perf = json.loads(capsys.readouterr().out)
    assert perf["schema_version"] == "ccr.performance_report.v1"

    assert main(["--root", str(runtime_root), "cache", "rebuild", "--scope", "all", "--json"]) == 0
    cache = json.loads(capsys.readouterr().out)
    assert cache["schema_version"] == "ccr.cache_rebuild.v1"

    repo = Path(__file__).resolve().parents[1]
    for relative in [
        "schemas/token-extraction-pipeline-report.schema.json",
        "schemas/performance-report.schema.json",
        "examples/asi_proxy_loop_bundle/target.json",
        "docs/asi-proxy-loop.md",
    ]:
        assert (repo / relative).is_file()
