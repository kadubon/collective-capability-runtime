from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

from ccr.experiments.protocol import (
    compare_experiment_results,
    ingest_experiment_result,
    register_experiment,
)
from ccr.ids import sha256_bytes, sha256_json
from ccr.io import read_json, write_json_atomic
from ccr.operations.approval import (
    create_operation_approval,
    validate_and_consume_approval,
)
from ccr.operations.verifier import verify_physical_observation
from ccr.providers.http import HttpProvider
from ccr.residuals.lifecycle import assign_residual, resolve_residual, review_residual
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from ccr.storage.local_store import SQLiteRuntimeStore
from ccr.tasks.factory import build_task
from ccr.tasks.lease import lease_task, release_task
from ccr.tasks.lifecycle import cancel_task, fail_task, retry_task
from ccr.tasks.model import task_path
from ccr.tasks.store import submit_task


def _plan() -> dict[str, Any]:
    return {
        "operations": [
            {
                "authority_envelope": {
                    "expires_at": "2099-01-01T00:00:00Z",
                    "status": "approved",
                },
                "resource_use": {"budget": 1},
                "validity_domain": {"environment": "test"},
            }
        ],
        "plan_id": "plan.failure-branches",
        "schema_version": "ccr.trc_operation_plan.v1",
    }


def _config() -> dict[str, Any]:
    return {
        "allow_execute": True,
        "provider_class": "fake",
        "side_effect_policy": "controlled_provider_allowed",
    }


def test_approval_creation_and_binding_fail_closed(runtime_root: Path) -> None:
    ok, failure, _ = validate_and_consume_approval(
        runtime_root, plan=_plan(), provider="fake", config=_config()
    )
    assert ok is False
    assert failure == "operator_approval_required"
    with pytest.raises(ValueError, match="distinct approver"):
        create_operation_approval(
            runtime_root,
            plan=_plan(),
            provider="fake",
            config={**_config(), "side_effect_policy": "physical_provider_allowed"},
            approvers=["human.one"],
            expires_at="2099-01-01T00:00:00Z",
            nonce="nonce.physical",
        )
    with pytest.raises(ValueError, match="max_uses"):
        create_operation_approval(
            runtime_root,
            plan=_plan(),
            provider="fake",
            config=_config(),
            approvers=["human.one"],
            expires_at="2099-01-01T00:00:00Z",
            nonce="nonce.invalid",
            max_uses=0,
        )
    with pytest.raises(ValueError, match="future"):
        create_operation_approval(
            runtime_root,
            plan=_plan(),
            provider="fake",
            config=_config(),
            approvers=["human.one"],
            expires_at="2000-01-01T00:00:00Z",
            nonce="nonce.expired",
        )
    approval = create_operation_approval(
        runtime_root,
        plan=_plan(),
        provider="fake",
        config=_config(),
        approvers=["human.one"],
        expires_at="2099-01-01T00:00:00Z",
        nonce="nonce.bound",
    )
    ref = approval["approval"]["approval_id"]
    ok, failure, _ = validate_and_consume_approval(
        runtime_root,
        plan=_plan(),
        provider="other",
        config={
            **_config(),
            "approval_nonce": "nonce.bound",
            "operator_approval_ref": ref,
        },
    )
    assert ok is False
    assert failure == "approval_provider_mismatch"
    ok, failure, _ = validate_and_consume_approval(
        runtime_root,
        plan=_plan(),
        provider="fake",
        config={
            **_config(),
            "approval_nonce": "nonce.bound",
            "operator_approval_ref": ref,
            "timeout_seconds": 10,
        },
    )
    assert ok is False
    assert failure == "approval_config_mismatch"
    ok, failure, _ = validate_and_consume_approval(
        runtime_root,
        plan={**_plan(), "plan_id": "plan.tampered"},
        provider="fake",
        config={
            **_config(),
            "approval_nonce": "nonce.bound",
            "operator_approval_ref": ref,
        },
    )
    assert ok is False
    assert failure == "approval_plan_mismatch"
    ok, failure, _ = validate_and_consume_approval(
        runtime_root,
        plan=_plan(),
        provider="fake",
        config={
            **_config(),
            "approval_nonce": "wrong",
            "operator_approval_ref": ref,
        },
    )
    assert ok is False
    assert failure == "approval_nonce_mismatch"


class _Response:
    status = 200

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self, size: int) -> bytes:
        return b'{"accepted":true,"settled":false}'


class _Opener:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def open(self, request: Any, timeout: int) -> _Response:
        if self.fail:
            raise URLError("request failed?credential=redacted")
        return _Response()


def _http_config() -> dict[str, Any]:
    return {
        "allow_execute": True,
        "allowed_hosts": ["provider.example"],
        "byte_limit": 1024,
        "endpoint": "https://provider.example/report",
        "method": "POST",
        "timeout_seconds": 5,
    }


def test_http_provider_success_error_and_config_rejections(
    tmp_path: Path, monkeypatch: Any
) -> None:
    provider = HttpProvider()
    assert provider.capabilities()["executes_network"] is True
    assert provider.health()["available"] is True
    monkeypatch.setattr(
        "ccr.providers.http.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr("ccr.providers.http.build_opener", lambda *args: _Opener())
    success = provider.execute(
        action="trc_operation", payload={"value": 1}, root=tmp_path, config=_http_config()
    )
    assert success["ok"] is True
    assert provider.normalize(success)["accepted"] is True
    monkeypatch.setattr("ccr.providers.http.build_opener", lambda *args: _Opener(fail=True))
    failure = provider.execute(
        action="trc_operation", payload={}, root=tmp_path, config=_http_config()
    )
    assert failure["ok"] is False
    assert "credential" not in failure["error"]
    for update, message in (
        ({"endpoint": "http://provider.example"}, "HTTPS"),
        ({"allowed_hosts": ["other.example"]}, "allowed_hosts"),
        ({"method": "DELETE"}, "method"),
        ({"timeout_seconds": "5"}, "timeout_seconds"),
        ({"byte_limit": True}, "byte_limit"),
    ):
        report = provider.execute(
            action="trc_operation",
            payload={},
            root=tmp_path,
            config={**_http_config(), **update},
        )
        assert message in report["error"]


def test_physical_verifier_failure_taxonomy() -> None:
    scope = {"environment": "test"}
    plan = {
        "operations": [{"validity_domain": scope}],
        "trusted_verifier_key_digests": [sha256_bytes(b"x" * 32)],
    }
    observation = {"observed_at": "2026-01-01T00:00:00Z", "physical_outcome": True}
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_verifier_report_missing"
    )
    observation["verifier_report"] = {"accepted": False}
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_verifier_report_invalid"
    )
    observation["verifier_report"] = {
        "accepted": True,
        "schema_version": "ccr.observation_verification_report.v1",
        "signature_alg": "ed25519",
    }
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_signed_payload_missing"
    )
    observation["verifier_report"].update(
        {
            "public_key_base64": "not-base64",
            "signature_base64": "not-base64",
            "signed_payload": {},
        }
    )
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_signature_encoding_invalid"
    )
    observation["verifier_report"].update(
        {
            "public_key_base64": base64.b64encode(b"y" * 32).decode(),
            "signature_base64": base64.b64encode(b"signature").decode(),
        }
    )
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_verifier_key_untrusted"
    )
    public_key = b"x" * 32
    observation["verifier_report"].update(
        {
            "public_key_base64": base64.b64encode(public_key).decode(),
            "signature_base64": base64.b64encode(b"invalid-signature").decode(),
            "signed_payload": {
                "observation_sha256": "wrong",
                "scope": scope,
                "valid_from": "2025-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
            },
        }
    )
    report = observation["verifier_report"]
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_observation_digest_mismatch"
    )
    report["signed_payload"]["observation_sha256"] = sha256_json(
        {key: value for key, value in observation.items() if key != "verifier_report"}
    )
    report["signed_payload"]["scope"] = {"environment": "other"}
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_verifier_scope_mismatch"
    )
    report["signed_payload"]["scope"] = scope
    report["signed_payload"]["valid_until"] = "2025-01-01T00:00:00Z"
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_verifier_window_invalid"
    )
    report["signed_payload"]["valid_until"] = "2027-01-01T00:00:00Z"
    assert verify_physical_observation(plan=plan, observation=observation)[1] == (
        "physical_outcome_signature_invalid"
    )


def test_task_and_residual_failure_lifecycle(runtime_root: Path, tmp_path: Path) -> None:
    task = build_task(
        kind="failure_lifecycle",
        title="Failure lifecycle",
        objective="Exercise cancel, fail, and retry.",
        role="generator",
        source="test",
    )
    submit_task(runtime_root, task)
    cancelled = cancel_task(
        runtime_root, str(task["task_id"]), agent="worker.one", reason="withdrawn"
    )
    assert cancelled["status_after"] == "rejected"
    retry_task(runtime_root, str(task["task_id"]), reason="restored")
    leased = lease_task(runtime_root, str(task["task_id"]), ttl="5m", agent="worker.one")
    token = int(leased["task"]["lease"]["fencing_token"])
    with pytest.raises(ValueError, match="fencing"):
        cancel_task(
            runtime_root,
            str(task["task_id"]),
            agent="worker.one",
            reason="stale",
            fencing_token=token + 1,
        )
    failed = fail_task(
        runtime_root,
        str(task["task_id"]),
        agent="worker.one",
        fencing_token=token,
        reason="blocked",
    )
    assert failed["residual_ready"]["blocking"] is True

    residual = build_residual(
        kind="missing_evidence",
        description="Missing repair.",
        blocking=True,
        object_type="task",
        object_id=str(task["task_id"]),
        source="test",
    )
    save_residual(runtime_root, residual)
    assign_residual(runtime_root, residual["residual_id"], agent="worker.one")
    review_residual(runtime_root, residual["residual_id"], reviewer="reviewer.one")
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{}", encoding="utf-8")
    verifier = tmp_path / "verifier.json"
    write_json_atomic(
        verifier,
        {
            "accepted": True,
            "artifact_sha256": sha256_bytes(artifact.read_bytes()),
            "verifier_id": "worker.one",
        },
    )
    with pytest.raises(ValueError, match="independent"):
        resolve_residual(
            runtime_root,
            residual["residual_id"],
            artifact=artifact,
            verifier=verifier,
        )


def test_legacy_release_requires_owner_fence_or_expiry(runtime_root: Path) -> None:
    task = build_task(
        kind="release_lifecycle",
        title="Release lifecycle",
        objective="Exercise fenced legacy release.",
        role="generator",
        source="release-test",
    )
    submit_task(runtime_root, task)
    leased = lease_task(runtime_root, str(task["task_id"]), ttl="5m", agent="worker.one")
    token = int(leased["task"]["lease"]["fencing_token"])
    with pytest.raises(ValueError, match="owner"):
        release_task(runtime_root, str(task["task_id"]), reason="normal")
    released = release_task(
        runtime_root,
        str(task["task_id"]),
        reason="normal",
        agent="worker.one",
        fencing_token=token,
    )
    assert released["status_after"] == "open"
    lease_task(runtime_root, str(task["task_id"]), ttl="5m", agent="worker.two")
    leased_path = task_path(runtime_root, str(task["task_id"]), "leased")
    expired = read_json(leased_path)
    expired["lease"]["leased_at"] = "2000-01-01T00:00:00Z"
    write_json_atomic(leased_path, expired)
    blocked = release_task(runtime_root, str(task["task_id"]), reason="blocking dependency")
    assert blocked["status_after"] == "blocked"
    assert blocked["residual"]["blocking"] is True


def test_experiment_registration_and_ingest_failures(runtime_root: Path, tmp_path: Path) -> None:
    non_object = tmp_path / "non-object.json"
    non_object.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        register_experiment(runtime_root, suite="non-object", manifest_path=non_object)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        register_experiment(runtime_root, suite="invalid", manifest_path=invalid)
    manifest = {
        "evaluation_design": {
            "alpha": 0.05,
            "mode": "confidence_sequence",
            "pre_registered": True,
        },
        "evaluator_plugin": "fixture:evaluate",
        "outcome_schema": {"type": "number"},
        "pre_registered": True,
        "resource_envelope": {"budget": 1},
        "task_manifest": {"kind": "fixture"},
    }
    manifest_path = tmp_path / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    register_experiment(runtime_root, suite="valid", manifest_path=manifest_path)
    bad_mode = {**manifest, "evaluation_design": {"mode": "post_selected"}}
    bad_mode_path = tmp_path / "bad-mode.json"
    write_json_atomic(bad_mode_path, bad_mode)
    with pytest.raises(ValueError, match="evaluation_design"):
        register_experiment(runtime_root, suite="bad-mode", manifest_path=bad_mode_path)
    not_registered = {**manifest, "pre_registered": False}
    not_registered_path = tmp_path / "not-registered.json"
    write_json_atomic(not_registered_path, not_registered)
    with pytest.raises(ValueError, match="pre_registered"):
        register_experiment(runtime_root, suite="not-registered", manifest_path=not_registered_path)
    with pytest.raises(ValueError, match="label"):
        ingest_experiment_result(runtime_root, suite="valid", label="other", result_path=invalid)
    incomplete = tmp_path / "incomplete.json"
    write_json_atomic(incomplete, {"outcomes": []})
    with pytest.raises(ValueError, match="missing fields"):
        ingest_experiment_result(
            runtime_root, suite="valid", label="baseline", result_path=incomplete
        )
    with pytest.raises(ValueError, match="JSON objects"):
        ingest_experiment_result(
            runtime_root, suite="valid", label="baseline", result_path=non_object
        )
    mismatch = tmp_path / "mismatch.json"
    write_json_atomic(
        mismatch,
        {
            "outcomes": [1.0],
            "resource_envelope": {"budget": 2},
            "seed": 1,
            "tool_model_version": "fixture",
        },
    )
    with pytest.raises(ValueError, match="resource envelope"):
        ingest_experiment_result(
            runtime_root, suite="valid", label="baseline", result_path=mismatch
        )
    comparison = compare_experiment_results(
        {"outcomes": [0.0], "resource_envelope": {"budget": 1}},
        {"outcomes": [1.0], "resource_envelope": {"budget": 2}},
    )
    assert comparison["accepted"] is False
    assert comparison["acceleration_claim_admissible"] is False
    sequential = compare_experiment_results(
        {
            "resource_envelope": {"budget": 1},
            "success_score": 0.0,
        },
        {
            "elapsed_seconds": 100,
            "evaluation_design": {
                "alpha": 0.05,
                "mode": "confidence_sequence",
                "pre_registered": True,
            },
            "residuals_opened": 8,
            "residuals_remaining": 2,
            "resource_envelope": {"budget": 1},
            "success_score": 1.0,
        },
    )
    assert sequential["evaluation_design_valid"] is True
    assert sequential["metrics"]["residual_half_life"] == 50


def test_local_store_append_claim_heartbeat_complete(runtime_root: Path) -> None:
    store = SQLiteRuntimeStore(runtime_root)
    task = build_task(
        kind="store_lifecycle",
        title="Store lifecycle",
        objective="Exercise RuntimeStore methods.",
        role="verifier",
        source="test",
    )
    assert store.append_task(task)["ok"] is True
    claim = store.claim_task(role="verifier", worker_id="worker.store", ttl_minutes=5)
    assert claim is not None
    token = int(claim["task"]["lease"]["fencing_token"])
    assert (
        store.heartbeat(
            task_id=str(task["task_id"]), worker_id="worker.store", fencing_token=token
        )["ok"]
        is True
    )
    completed = store.complete(
        task_id=str(task["task_id"]),
        worker_id="worker.store",
        fencing_token=token,
        idempotency_key="store.complete",
        result={"output_refs": ["artifact.one"], "summary": "done"},
    )
    assert completed["status_after"] == "submitted"
