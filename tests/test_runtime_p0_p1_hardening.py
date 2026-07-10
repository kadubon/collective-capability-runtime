from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ccr.extensions import experiment_init, workcell_create
from ccr.ids import sha256_bytes
from ccr.io import read_json, write_json_atomic
from ccr.phase.eligibility import packet_eligibility
from ccr.residuals.lifecycle import assign_residual, reopen_residual, resolve_residual
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.schemas.validation import validate_instance
from ccr.storage.local_store import SQLiteRuntimeStore
from ccr.tasks.factory import build_task
from ccr.tasks.lease import lease_task
from ccr.tasks.lifecycle import complete_task, heartbeat_task
from ccr.tasks.store import submit_task
from tests.conftest import example_json


def test_runtime_identifiers_cannot_escape_root(runtime_root: Path) -> None:
    with pytest.raises(ValueError):
        workcell_create(runtime_root, template="packet-distillation", name="../../escape")
    with pytest.raises(ValueError):
        experiment_init(runtime_root, suite="../escape")
    assert not (runtime_root.parent / "escape").exists()


def test_workcell_rejects_symlink_escape(runtime_root: Path) -> None:
    workcells = runtime_root / "workcells"
    workcells.mkdir(exist_ok=True)
    external = runtime_root.parent / f"{runtime_root.name}-external-workcell"
    external.mkdir()
    link = workcells / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are not available in this Windows session")
    with pytest.raises(ValueError, match="outside"):
        workcell_create(runtime_root, template="packet-distillation", name="linked")


def test_runtime_local_schema_cannot_override_normative_schema(runtime_root: Path) -> None:
    local_schema = runtime_root / "schemas" / "packet.schema.json"
    write_json_atomic(local_schema, {})
    packet = example_json("examples/minimal/packet.json")
    packet.pop("scope")
    assert validate_instance("packet", packet, root=runtime_root).ok is False


def test_missing_phase_coordinates_never_create_positive_progress(runtime_root: Path) -> None:
    packet = example_json("examples/minimal/packet.json")
    packet["status"] = "checked"
    packet["metrics"] = {}
    result = packet_eligibility(runtime_root, packet)
    assert result["positive_contribution"] is False
    assert result["liquidity_lower_bound"] is None
    assert all(item["status"] == "unknown" for item in result["coordinates"].values())


def test_task_lifecycle_rejects_stale_fence_and_is_idempotent(runtime_root: Path) -> None:
    task = example_json("examples/minimal/task.json")
    submit_task(runtime_root, task)
    leased = lease_task(runtime_root, task["task_id"], ttl="30m", agent="agent.a")
    token = leased["task"]["lease"]["fencing_token"]

    with pytest.raises(ValueError, match="stale"):
        heartbeat_task(
            runtime_root,
            task["task_id"],
            agent="agent.a",
            fencing_token=token + 1,
        )

    completed = complete_task(
        runtime_root,
        task["task_id"],
        agent="agent.a",
        fencing_token=token,
        output_refs=["artifact:one"],
        summary="Completed under verifier review.",
        idempotency_key="completion.one",
    )
    repeated = complete_task(
        runtime_root,
        task["task_id"],
        agent="agent.a",
        fencing_token=token,
        output_refs=["artifact:one"],
        summary="Completed under verifier review.",
        idempotency_key="completion.one",
    )
    assert completed["status_after"] == "submitted"
    assert repeated["idempotent"] is True


def test_sqlite_concurrent_workers_receive_unique_leases(runtime_root: Path) -> None:
    for index in range(20):
        submit_task(
            runtime_root,
            build_task(
                kind="local_concurrency",
                title="Concurrent task",
                objective=f"Lease local task {index} once.",
                role="generator",
                source=f"local:{index}",
            ),
        )
    store = SQLiteRuntimeStore(runtime_root)
    with ThreadPoolExecutor(max_workers=20) as executor:
        claims = list(
            executor.map(
                lambda index: store.claim_task(
                    role="generator", worker_id=f"worker.{index}", ttl_minutes=5
                ),
                range(20),
            )
        )
    task_ids = [str(item["task"]["task_id"]) for item in claims if item is not None]
    assert len(task_ids) == 20
    assert len(set(task_ids)) == 20


def test_residual_resolution_requires_independent_digest_bound_verifier(
    runtime_root: Path, tmp_path: Path
) -> None:
    residual = build_residual(
        kind="missing_evidence",
        description="Repair evidence is missing.",
        blocking=True,
        object_type="packet",
        object_id="packet.test",
        source="test",
    )
    save_residual(runtime_root, residual)
    assign_residual(runtime_root, residual["residual_id"], agent="agent.builder")
    artifact = tmp_path / "repair.json"
    artifact.write_text('{"repaired":true}\n', encoding="utf-8")
    verifier = tmp_path / "verifier.json"
    write_json_atomic(
        verifier,
        {
            "accepted": True,
            "artifact_sha256": sha256_bytes(artifact.read_bytes()),
            "verifier_id": "agent.verifier",
        },
    )
    result = resolve_residual(
        runtime_root,
        residual["residual_id"],
        artifact=artifact,
        verifier=verifier,
    )
    assert result["status_after"] == "resolved"
    reopened = reopen_residual(runtime_root, residual["residual_id"], reason="new contradiction")
    assert reopened["status_after"] == "open"
    assert reopened["residual"]["extensions"]["workflow"]["resolution_history"]


def test_sqlite_connections_close_on_windows_compatible_cleanup(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    experiment_init(root, suite="cleanup")
    shutil.rmtree(root)
    assert not root.exists()


def test_json_reader_rejects_oversized_input(tmp_path: Path) -> None:
    path = tmp_path / "large.json"
    path.write_text('{"value":"' + ("x" * 64) + '"}', encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds"):
        read_json(path, max_bytes=16)
