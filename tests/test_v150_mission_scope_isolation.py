from __future__ import annotations

from pathlib import Path

from ccr.mission.init import initialize_mission
from ccr.mission.status import mission_status


def test_mission_status_exposes_runtime_and_empty_mission_task_counts(runtime_root: Path) -> None:
    init = initialize_mission(runtime_root, name="scope")

    report = mission_status(runtime_root, mission_id=str(init["mission_id"]))

    assert "task_counts" not in report
    assert report["mission_task_counts"] == {}
    assert set(report["runtime_task_counts"]) >= {"open", "leased", "verified"}
