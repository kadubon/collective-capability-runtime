# SPDX-License-Identifier: Apache-2.0
"""Optional versioned CCR HTTP API."""

from __future__ import annotations

import contextvars
import importlib
from pathlib import Path
from typing import Any

from ccr.distributed.auth import AuthError, identity_class, verify_oidc_dpop
from ccr.io import DEFAULT_MAX_JSON_BYTES, validate_json_depth
from ccr.operations.approval import create_operation_approval
from ccr.schemas.validation import validate_instance
from ccr.storage.base import RuntimeStore

_request_identity: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "ccr_request_identity", default=None
)


def create_app(*, root: Path, store: RuntimeStore, auth_config: dict[str, Any]) -> Any:
    """Create the FastAPI app without importing optional dependencies in core mode."""

    try:
        fastapi = importlib.import_module("fastapi")
        responses = importlib.import_module("fastapi.responses")
    except ImportError as exc:
        raise RuntimeError("CCR server requires the 'distributed' extra") from exc
    app = fastapi.FastAPI(title="Collective Capability Runtime", version="v1")

    @app.middleware("http")  # type: ignore[untyped-decorator]
    async def authenticate(request: Any, call_next: Any) -> Any:
        max_request_bytes = auth_config.get("max_request_bytes", DEFAULT_MAX_JSON_BYTES)
        if isinstance(max_request_bytes, bool) or not isinstance(max_request_bytes, int):
            return responses.JSONResponse(
                status_code=500,
                content={"error": "max_request_bytes must be an integer", "ok": False},
            )
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_request_bytes:
                    return responses.JSONResponse(
                        status_code=413,
                        content={"error": "request body exceeds byte limit", "ok": False},
                    )
            except ValueError:
                return responses.JSONResponse(
                    status_code=400,
                    content={"error": "invalid content-length", "ok": False},
                )
        if request.method in {"POST", "PUT", "PATCH"}:
            body = await request.body()
            if len(body) > max_request_bytes:
                return responses.JSONResponse(
                    status_code=413,
                    content={"error": "request body exceeds byte limit", "ok": False},
                )
        if request.url.path == "/v1/health":
            return await call_next(request)
        try:
            claims = verify_oidc_dpop(
                authorization=request.headers.get("authorization"),
                dpop_proof=request.headers.get("dpop"),
                method=request.method,
                url=str(request.url),
                config=auth_config,
                store=store,
            )
            claims["identity_class"] = identity_class(claims, auth_config)
            token = _request_identity.set(claims)
            try:
                return await call_next(request)
            finally:
                _request_identity.reset(token)
        except (AuthError, RuntimeError) as exc:
            return responses.JSONResponse(status_code=401, content={"error": str(exc), "ok": False})

    @app.get("/v1/health")  # type: ignore[untyped-decorator]
    async def health() -> dict[str, Any]:
        return {"ok": True, "schema_version": "ccr.api_health.v1"}

    @app.post("/v1/tasks")  # type: ignore[untyped-decorator]
    async def submit_task_api(body: dict[str, Any]) -> dict[str, Any]:
        _require_identity("worker")
        validate_json_depth(body)
        validation = validate_instance("task", body, root=root)
        if not validation.ok:
            raise fastapi.HTTPException(
                status_code=422,
                detail=[issue.message for issue in validation.errors],
            )
        return store.append_task(body)

    @app.post("/v1/tasks/claim")  # type: ignore[untyped-decorator]
    async def claim_task_api(body: dict[str, Any]) -> dict[str, Any]:
        validate_json_depth(body)
        identity = _require_identity("worker")
        worker_id = str(identity["sub"])
        claim = store.claim_task(
            role=str(body["role"]),
            worker_id=worker_id,
            ttl_minutes=int(body.get("ttl_minutes", 30)),
        )
        return {"claim": claim, "ok": True}

    @app.post("/v1/tasks/{task_id}/heartbeat")  # type: ignore[untyped-decorator]
    async def heartbeat_task_api(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        validate_json_depth(body)
        identity = _require_identity("worker")
        return store.heartbeat(
            task_id=task_id,
            worker_id=str(identity["sub"]),
            fencing_token=int(body["fencing_token"]),
        )

    @app.post("/v1/tasks/{task_id}/complete")  # type: ignore[untyped-decorator]
    async def complete_task_api(task_id: str, body: dict[str, Any]) -> dict[str, Any]:
        validate_json_depth(body)
        identity = _require_identity("worker")
        result = body.get("result")
        if not isinstance(result, dict):
            raise fastapi.HTTPException(status_code=422, detail="result must be an object")
        return store.complete(
            task_id=task_id,
            worker_id=str(identity["sub"]),
            fencing_token=int(body["fencing_token"]),
            idempotency_key=str(body["idempotency_key"]),
            result=result,
        )

    @app.post("/v1/operation-approvals")  # type: ignore[untyped-decorator]
    async def approve_operation_api(body: dict[str, Any]) -> dict[str, Any]:
        validate_json_depth(body)
        identity = _require_identity("human")
        plan = body.get("plan")
        config = body.get("config")
        if not isinstance(plan, dict) or not isinstance(config, dict):
            raise fastapi.HTTPException(status_code=422, detail="plan and config must be objects")
        return create_operation_approval(
            root,
            plan=plan,
            provider=str(body["provider"]),
            config=config,
            approvers=[str(identity["sub"])],
            expires_at=str(body["expires_at"]),
            nonce=str(body["nonce"]),
            max_uses=int(body.get("max_uses", 1)),
        )

    return app


def run_server(
    *,
    root: Path,
    store: RuntimeStore,
    auth_config: dict[str, Any],
    host: str,
    port: int,
) -> None:
    try:
        uvicorn = importlib.import_module("uvicorn")
    except ImportError as exc:
        raise RuntimeError("CCR server requires the 'distributed' extra") from exc
    app = create_app(root=root, store=store, auth_config=auth_config)
    uvicorn.run(app, host=host, port=port, log_config=None)


def _require_identity(expected: str) -> dict[str, Any]:
    identity = _request_identity.get()
    if identity is None or identity.get("identity_class") != expected:
        raise AuthError(f"endpoint requires {expected} identity")
    return identity
