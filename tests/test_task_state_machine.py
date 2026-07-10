from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis.stateful import RuleBasedStateMachine, invariant, precondition, rule

from ccr.runtime.init import init_runtime
from ccr.tasks.factory import build_task
from ccr.tasks.lease import lease_task
from ccr.tasks.lifecycle import complete_task, fail_task, heartbeat_task, retry_task
from ccr.tasks.model import STATUS_TO_DIR, task_path
from ccr.tasks.store import load_task, submit_task


class TaskLifecycleMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ccr-state-machine-")
        self.root = Path(self.temporary.name)
        init_runtime(self.root)
        self.task = build_task(
            kind="state_machine",
            title="State machine task",
            objective="Exercise fenced lifecycle transitions.",
            role="generator",
            source="hypothesis",
        )
        submit_task(self.root, self.task)
        self.task_id = str(self.task["task_id"])
        self.status = "open"
        self.fencing_token = 0

    @precondition(lambda self: self.status == "open")
    @rule()
    def lease(self) -> None:
        result = lease_task(self.root, self.task_id, ttl="30m", agent="worker.test")
        self.fencing_token = int(result["task"]["lease"]["fencing_token"])
        self.status = "leased"

    @precondition(lambda self: self.status == "leased")
    @rule()
    def heartbeat(self) -> None:
        heartbeat_task(
            self.root,
            self.task_id,
            agent="worker.test",
            fencing_token=self.fencing_token,
        )

    @precondition(lambda self: self.status == "leased")
    @rule()
    def stale_heartbeat_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="stale"):
            heartbeat_task(
                self.root,
                self.task_id,
                agent="worker.test",
                fencing_token=max(0, self.fencing_token - 1),
            )

    @precondition(lambda self: self.status == "leased")
    @rule()
    def fail(self) -> None:
        fail_task(
            self.root,
            self.task_id,
            agent="worker.test",
            fencing_token=self.fencing_token,
            reason="generated failure",
        )
        self.status = "blocked"

    @precondition(lambda self: self.status == "blocked")
    @rule()
    def retry(self) -> None:
        retry_task(self.root, self.task_id, reason="generated retry")
        self.status = "open"

    @precondition(lambda self: self.status == "leased")
    @rule()
    def complete(self) -> None:
        complete_task(
            self.root,
            self.task_id,
            agent="worker.test",
            fencing_token=self.fencing_token,
            output_refs=["artifact:test"],
            summary="generated completion",
            idempotency_key="completion.test",
        )
        self.status = "submitted"

    @rule()
    def observe(self) -> None:
        load_task(self.root, self.task_id)

    @invariant()
    def artifact_and_status_are_unique(self) -> None:
        paths = [
            task_path(self.root, self.task_id, status)
            for status in STATUS_TO_DIR
            if task_path(self.root, self.task_id, status).exists()
        ]
        assert len(paths) == 1
        task, path, status = load_task(self.root, self.task_id)
        assert path == paths[0]
        assert status == self.status
        assert task["status"] == self.status
        if self.status == "leased":
            assert int(task["lease"]["fencing_token"]) == self.fencing_token

    def teardown(self) -> None:
        self.temporary.cleanup()


TestTaskLifecycle = TaskLifecycleMachine.TestCase
