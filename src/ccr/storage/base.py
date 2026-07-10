# SPDX-License-Identifier: Apache-2.0
"""Storage profile interface shared by local and distributed runtimes."""

from __future__ import annotations

from typing import Any, Protocol


class RuntimeStore(Protocol):
    """Authoritative task state machine boundary."""

    def initialize(self) -> dict[str, Any]: ...

    def claim_task(
        self, *, role: str, worker_id: str, ttl_minutes: int
    ) -> dict[str, Any] | None: ...

    def heartbeat(self, *, task_id: str, worker_id: str, fencing_token: int) -> dict[str, Any]: ...

    def complete(
        self,
        *,
        task_id: str,
        worker_id: str,
        fencing_token: int,
        idempotency_key: str,
        result: dict[str, Any],
    ) -> dict[str, Any]: ...

    def append_task(self, task: dict[str, Any]) -> dict[str, Any]: ...

    def consume_dpop_jti(self, *, jti: str, expires_at: str) -> bool: ...
