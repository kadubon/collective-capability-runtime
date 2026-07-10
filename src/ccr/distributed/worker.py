# SPDX-License-Identifier: Apache-2.0
"""Generic fenced worker loop with optional application handler."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable
from typing import Any, cast

from ccr.ids import sha256_json
from ccr.io import pretty_dumps
from ccr.storage.base import RuntimeStore


def run_worker(
    *,
    store: RuntimeStore,
    role: str,
    worker_id: str,
    handler_ref: str | None,
    once: bool,
    poll_seconds: float,
) -> None:
    handler = _load_handler(handler_ref) if handler_ref else None
    while True:
        claim = store.claim_task(role=role, worker_id=worker_id, ttl_minutes=30)
        if claim is None:
            if once:
                return
            time.sleep(poll_seconds)
            continue
        print(pretty_dumps(claim), flush=True)
        if handler is not None:
            task = claim.get("task")
            result = handler(task if isinstance(task, dict) else {})
            if not isinstance(result, dict):
                raise TypeError("worker handler must return a JSON object")
            store.complete(
                task_id=str(claim["task_id"]),
                worker_id=worker_id,
                fencing_token=int(claim["fencing_token"]),
                idempotency_key=f"worker.{sha256_json(result)[:24]}",
                result=result,
            )
        if once:
            return


def _load_handler(reference: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    module_name, separator, attribute = reference.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("handler must use module:function syntax")
    module = importlib.import_module(module_name)
    handler = getattr(module, attribute)
    if not callable(handler):
        raise TypeError("worker handler is not callable")
    return cast(Callable[[dict[str, Any]], dict[str, Any]], handler)
