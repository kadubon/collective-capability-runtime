from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from ccr.adapters.pic import PicVerifierProvider
from ccr.blackboard.events import make_event
from ccr.conformance.pic_contract import validate_pic_contract
from ccr.experiments.protocol import (
    compare_experiment_results,
    ingest_experiment_result,
    register_experiment,
)
from ccr.extensions import (
    operation_dispatch,
    operation_observe,
    workcell_advance,
    workcell_create,
    workcell_integrate,
    workcell_submit,
)
from ccr.ids import canonical_bytes, sha256_bytes, sha256_json
from ccr.operations.approval import create_operation_approval
from ccr.providers.http import HttpProvider
from ccr.schemas.registry import audit_schema_registry, validate_registered_report
from ccr.storage.admin import storage_doctor, storage_migrate
from ccr.storage.export import export_content_addressed
from ccr.storage.factory import create_store
from ccr.storage.local_store import SQLiteRuntimeStore
from ccr.tasks.factory import build_task


class _EffectProvider:
    provider_name = "fake"

    def plan(self, *, action: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
        return {"action": action, "network_call_performed": False, "provider": "fake"}

    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        root: Path,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "effect_executed": True,
            "network_call_performed": True,
            "ok": True,
            "provider": "fake",
        }


def _ready_plan() -> dict[str, Any]:
    return {
        "constraints": {
            "allowed_commands": [],
            "requires_execute_flag": True,
            "requires_provider_config": True,
        },
        "executed": False,
        "execution_blockers": [],
        "operations": [
            {
                "action_type": "tool-call",
                "authority_envelope": {
                    "expires_at": "2099-01-01T00:00:00Z",
                    "status": "approved",
                },
                "resource_use": {"budget": 1},
                "step_id": "step.one",
                "validity_domain": {"environment": "test"},
            }
        ],
        "plan_id": "plan.test",
        "real_world_operation_ready": True,
        "residuals": [],
        "schema_version": "ccr.trc_operation_plan.v1",
        "settled": False,
    }


def test_operation_approval_is_parameter_bound_and_single_use(
    runtime_root: Path, monkeypatch: Any
) -> None:
    import ccr.providers.registry as registry

    monkeypatch.setattr(registry, "get_provider", lambda name: _EffectProvider())
    plan = _ready_plan()
    base_config = {
        "allow_execute": True,
        "allowed_provider_classes": ["fake"],
        "provider_class": "fake",
        "side_effect_policy": "controlled_provider_allowed",
    }
    approval = create_operation_approval(
        runtime_root,
        plan=plan,
        provider="fake",
        config=base_config,
        approvers=["human.reviewer"],
        expires_at="2099-01-01T00:00:00Z",
        nonce="nonce.bound",
    )
    config = {
        **base_config,
        "approval_nonce": "nonce.bound",
        "operator_approval_ref": approval["approval"]["approval_id"],
    }
    tampered = operation_dispatch(
        runtime_root,
        plan=plan,
        provider_name="fake",
        config={**config, "provider_class": "other"},
        execute=True,
    )
    first = operation_dispatch(
        runtime_root,
        plan=plan,
        provider_name="fake",
        config=config,
        execute=True,
    )
    replay = operation_dispatch(
        runtime_root,
        plan=plan,
        provider_name="fake",
        config=config,
        execute=True,
    )
    assert tampered["ok"] is False
    assert tampered["residual_ready"]["kind"] in {
        "approval_config_mismatch",
        "preflight_required",
        "provider_class_not_allowed",
    }
    assert first["ok"] is True
    assert first["executed"] is True
    assert replay["residual_ready"]["kind"] == "approval_replayed"


def test_physical_outcome_requires_trusted_ed25519_scope_and_window() -> None:
    ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    serialization = pytest.importorskip("cryptography.hazmat.primitives.serialization")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    scope = {"environment": "test-rig"}
    plan = {
        "operations": [{"step_id": "step.one", "validity_domain": scope}],
        "trusted_verifier_key_digests": [sha256_bytes(public_key)],
    }
    observation = {
        "hazard_observation": {"status": "clear"},
        "observed_at": "2026-07-10T00:00:00Z",
        "physical_outcome": {"fixture": "observed"},
        "physical_outcome_verifier_acceptance_ref": "verifier.report.one",
        "physical_outcome_verifier_scope": "test-rig",
        "provider": "fake",
        "schema_version": "ccr.trc_operation_observation_input.v1",
    }
    signed_payload = {
        "observation_sha256": sha256_json(observation),
        "scope": scope,
        "valid_from": "2026-07-09T00:00:00Z",
        "valid_until": "2026-07-11T00:00:00Z",
        "verifier_id": "verifier.one",
    }
    observation["verifier_report"] = {
        "accepted": True,
        "public_key_base64": base64.b64encode(public_key).decode(),
        "schema_version": "ccr.observation_verification_report.v1",
        "signature_alg": "ed25519",
        "signature_base64": base64.b64encode(
            private_key.sign(canonical_bytes(signed_payload))
        ).decode(),
        "signed_payload": signed_payload,
    }
    result = operation_observe(
        dispatch_report={
            "executed": True,
            "preflight": {"operation_plan": plan},
            "provider": "fake",
            "report": {
                "effect_executed": True,
                "normalized": True,
                "schema_version": "ccr.provider_run.v1",
            },
        },
        observation=observation,
    )
    assert result["ok"] is True
    assert result["physical_outcome_proven"] is False
    assert result["physical_outcome_verified"] is True


def test_http_provider_rejects_truthy_string_and_private_resolution(
    tmp_path: Path, monkeypatch: Any
) -> None:
    string_bool = HttpProvider().execute(
        action="trc_operation",
        payload={},
        root=tmp_path,
        config={"allow_execute": "true"},
    )
    monkeypatch.setattr(
        "ccr.providers.http.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    private = HttpProvider().execute(
        action="trc_operation",
        payload={},
        root=tmp_path,
        config={
            "allow_execute": True,
            "allowed_hosts": ["localhost"],
            "endpoint": "https://localhost/hook",
            "method": "POST",
        },
    )
    assert string_bool["network_call_performed"] is False
    assert private["network_call_performed"] is False
    assert "non-public" in private["error"]


def test_pic_adapter_rejects_string_boolean() -> None:
    with pytest.raises(ValueError, match="JSON boolean"):
        PicVerifierProvider().normalize_report({"accepted": "false", "settled": False})


def test_pic_100_contract_keeps_commands_as_hints_and_checks_digest() -> None:
    report = {
        "accepted": True,
        "residuals": [],
        "safe_commands": ["pic packet inspect packet.json"],
        "settled": False,
    }
    contract = validate_pic_contract(report, pic_version="1.0.0")
    assert contract["accepted"] is True
    assert contract["safe_command_hints_executed"] is False
    assert contract["settled"] is False


def test_workcell_discounts_correlated_support(runtime_root: Path, tmp_path: Path) -> None:
    workcell_create(runtime_root, template="packet-distillation", name="correlation")
    for index in range(2):
        submission = tmp_path / f"submission-{index}.json"
        submission.write_text(
            json.dumps(
                {
                    "claims": [{"claim_text": "The bounded mechanism improves yield."}],
                    "provenance": {"model": "same", "source": "same", "tool": "same"},
                }
            ),
            encoding="utf-8",
        )
        workcell_submit(runtime_root, workcell="correlation", file=submission)
    report = workcell_integrate(
        runtime_root, workcell="correlation", strategy="residual-preserving"
    )
    assert report["claims"][0]["effective_support_count"] == 1
    assert report["minority_reports"]
    assert report["settled"] is False


def test_workcell_explicit_stage_machine_reveals_before_integration(
    runtime_root: Path, tmp_path: Path
) -> None:
    workcell_create(runtime_root, template="residual-repair", name="staged")
    submission = tmp_path / "proposal.json"
    submission.write_text(
        json.dumps({"claims": [{"claim_text": "A repair candidate exists."}]}),
        encoding="utf-8",
    )
    workcell_submit(runtime_root, workcell="staged", file=submission)
    reveal = workcell_advance(runtime_root, workcell="staged", target_stage="reveal")
    assert Path(reveal["reveal_manifest"]).exists()
    for stage in ("critique", "revision", "verification"):
        workcell_advance(runtime_root, workcell="staged", target_stage=stage)
    integrated = workcell_integrate(runtime_root, workcell="staged", strategy="residual-preserving")
    assert integrated["protocol_complete"] is True
    assert integrated["stage"] == "integration"


def test_preregistered_resource_matched_experiment_reports_conservative_uplift(
    runtime_root: Path, tmp_path: Path
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "evaluation_design": {
                    "alpha": 0.05,
                    "horizon": 100,
                    "mode": "fixed_horizon",
                    "pre_registered": True,
                },
                "evaluator_plugin": "example:evaluate",
                "outcome_schema": {"type": "number"},
                "pre_registered": True,
                "resource_envelope": {"budget": 100, "time": 100},
                "task_manifest": {"task_family": "user-supplied"},
            }
        ),
        encoding="utf-8",
    )
    registered = register_experiment(runtime_root, suite="metrics", manifest_path=manifest_path)
    results: dict[str, dict[str, Any]] = {}
    for label, outcomes in (("baseline", [0.0] * 100), ("collective", [1.0] * 100)):
        path = tmp_path / f"{label}.json"
        path.write_text(
            json.dumps(
                {
                    "agent_weights": [1, 1] if label == "collective" else [1],
                    "evaluation_design": registered["manifest"]["evaluation_design"],
                    "outcomes": outcomes,
                    "resource_envelope": {"budget": 100, "time": 100},
                    "seed": 7,
                    "tool_model_version": "fixture-v1",
                }
            ),
            encoding="utf-8",
        )
        results[label] = ingest_experiment_result(
            runtime_root, suite="metrics", label=label, result_path=path
        )["result"]
    comparison = compare_experiment_results(results["baseline"], results["collective"])
    assert comparison["resource_matched"] is True
    assert comparison["acceleration_claim_admissible"] is True
    assert comparison["confidence_interval"][0] > 0
    assert comparison["metrics"]["effective_agent_count"] == 2


def test_schema_registry_storage_and_cloudevent_envelope(runtime_root: Path) -> None:
    registry = audit_schema_registry(Path(__file__).resolve().parents[1])
    event = make_event(action="task.test", object_type="task", object_id="task.test")
    migration = storage_migrate(runtime_root)
    doctor = storage_doctor(runtime_root)
    report_errors = validate_registered_report(
        {"schema_version": "ccr.storage_doctor.v1", "ok": True},
        root=Path(__file__).resolve().parents[1],
    )
    assert registry["ok"] is True
    assert event["specversion"] == "1.0"
    assert event["traceparent"].startswith("00-")
    assert migration["applied"] is False
    assert doctor["integrity"] == "ok"
    assert report_errors == []

    exported = export_content_addressed(
        runtime_root,
        object_type="report",
        object_id="report.one",
        content={"schema_version": "ccr.storage_doctor.v1", "ok": True},
    )
    assert Path(exported["path"]).name == f"sha256-{exported['content_sha256']}.json"


def test_local_dpop_replay_store_is_one_time(runtime_root: Path) -> None:
    store = SQLiteRuntimeStore(runtime_root)
    assert store.consume_dpop_jti(jti="proof.one", expires_at="2099-01-01T00:00:00Z") is True
    assert store.consume_dpop_jti(jti="proof.one", expires_at="2099-01-01T00:00:00Z") is False


def test_oidc_dpop_signature_binding_and_replay_rejection(runtime_root: Path) -> None:
    pytest.importorskip("authlib")
    from authlib.deprecate import AuthlibDeprecationWarning

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AuthlibDeprecationWarning)
        import authlib.jose as authlib_jose
    from ccr.distributed.auth import AuthError, _jwk_thumbprint, verify_oidc_dpop

    issuer = "https://issuer.example"
    audience = "ccr-api"
    url = "https://api.example/v1/tasks"
    issuer_key = authlib_jose.JsonWebKey.generate_key(
        "EC", "P-256", is_private=True, options={"kid": "issuer-key"}
    )
    proof_key = authlib_jose.JsonWebKey.generate_key("EC", "P-256", is_private=True)
    proof_public = proof_key.as_dict(is_private=False)
    now = int(time.time())
    jwt = authlib_jose.JsonWebToken(["ES256"])
    credential = jwt.encode(
        {"alg": "ES256", "kid": "issuer-key"},
        {
            "aud": audience,
            "cnf": {"jkt": _jwk_thumbprint(proof_public)},
            "exp": now + 300,
            "iat": now,
            "iss": issuer,
            "sub": "worker:test",
        },
        issuer_key,
    ).decode()
    credential_hash = (
        base64.urlsafe_b64encode(hashlib.sha256(credential.encode()).digest()).rstrip(b"=").decode()
    )
    proof = jwt.encode(
        {"alg": "ES256", "jwk": proof_public, "typ": "dpop+jwt"},
        {
            "ath": credential_hash,
            "htm": "POST",
            "htu": url,
            "iat": now,
            "jti": "proof.crypto.one",
        },
        proof_key,
    ).decode()
    store = SQLiteRuntimeStore(runtime_root)
    config = {
        "audience": audience,
        "issuer": issuer,
        "jwks": {"keys": [issuer_key.as_dict(is_private=False)]},
    }
    claims = verify_oidc_dpop(
        authorization=f"DPoP {credential}",
        dpop_proof=proof,
        method="POST",
        url=url,
        config=config,
        store=store,
    )
    assert claims["sub"] == "worker:test"
    with pytest.raises(AuthError, match="replay"):
        verify_oidc_dpop(
            authorization=f"DPoP {credential}",
            dpop_proof=proof,
            method="POST",
            url=url,
            config=config,
            store=store,
        )


@pytest.mark.skipif(not os.environ.get("CCR_TEST_POSTGRES_DSN"), reason="PostgreSQL DSN not set")
def test_postgres_one_hundred_worker_leases_are_unique() -> None:
    dsn = os.environ["CCR_TEST_POSTGRES_DSN"]
    store = create_store(root=Path("."), database_url=dsn)
    store.initialize()
    role = f"benchmark_runner_{os.getpid()}"
    for index in range(100):
        task = build_task(
            kind="postgres_concurrency",
            title="Concurrent task",
            objective=f"Lease task {index} exactly once.",
            role="benchmark_runner",
            source=f"postgres:{os.getpid()}:{index}",
        )
        task["role"] = role
        store.append_task(task)
    with ThreadPoolExecutor(max_workers=100) as executor:
        claims = list(
            executor.map(
                lambda index: store.claim_task(
                    role=role, worker_id=f"worker:{index}", ttl_minutes=5
                ),
                range(100),
            )
        )
    task_ids = [str(item["task_id"]) for item in claims if item is not None]
    assert len(task_ids) == 100
    assert len(set(task_ids)) == 100
