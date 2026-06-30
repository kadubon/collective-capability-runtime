from __future__ import annotations

from ccr.io import read_json, write_json_atomic
from ccr.tasks.lease import lease_task
from ccr.tasks.model import task_path
from ccr.tasks.store import submit_task
from tests.conftest import example_json


def test_task_lease_changes_location_and_status(runtime_root):
    task = example_json("examples/minimal/task.json")
    submit_task(runtime_root, task)
    result = lease_task(runtime_root, task["task_id"], ttl="30m", agent="agent.a")
    assert result["ok"] is True
    assert not task_path(runtime_root, task["task_id"], "open").exists()
    leased = read_json(task_path(runtime_root, task["task_id"], "leased"))
    assert leased["status"] == "leased"
    assert leased["lease"]["leased_by"] == "agent.a"


def test_expired_lease_can_be_reclaimed(runtime_root):
    task = example_json("examples/minimal/task.json")
    submit_task(runtime_root, task)
    lease_task(runtime_root, task["task_id"], ttl="1m", agent="agent.a")
    path = task_path(runtime_root, task["task_id"], "leased")
    leased = read_json(path)
    leased["lease"]["leased_at"] = "2000-01-01T00:00:00Z"
    write_json_atomic(path, leased)
    result = lease_task(runtime_root, task["task_id"], ttl="30m", agent="agent.b")
    assert result["ok"] is True
    assert result["reclaimed"] is True
    assert result["task"]["lease"]["leased_by"] == "agent.b"
