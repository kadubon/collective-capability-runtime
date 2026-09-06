# SPDX-License-Identifier: Apache-2.0
"""Bridge optimizer tasks into the existing fenced worker protocol."""

from __future__ import annotations

from typing import Any

from ccr.optimizer.engine import claim, task_transition
from ccr.storage.control import ControlStore


def find(store: ControlStore, task_id: str) -> tuple[str, str] | None:
    for run in store.list_objects("optimizer:"):
        for trial in run["trials"]:
            if trial["task"]["task_id"] == task_id:
                return run["run_id"], trial["trial_id"]
    return None


def claim_next(
    store: ControlStore, *, role: str, worker_id: str, ttl_minutes: int
) -> dict[str, Any] | None:
    for run in store.list_objects("optimizer:"):
        for trial in run["trials"]:
            # Network-bound work must use optimizer run; arbitrary handlers do not dispatch it.
            if trial["task"]["role"] != role or "operation_plan" in trial:
                continue
            result = claim(
                store,
                run["run_id"],
                trial["trial_id"],
                worker=worker_id,
                ttl_seconds=ttl_minutes * 60,
            )
            if result["ok"]:
                return result
    return None


def transition(
    store: ControlStore,
    *,
    task_id: str,
    worker_id: str,
    fencing_token: int,
    result: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    target = find(store, task_id)
    if target is None:
        return None
    return task_transition(
        store,
        *target,
        worker=worker_id,
        token=fencing_token,
        result=result,
        idempotency_key=idempotency_key,
    )
