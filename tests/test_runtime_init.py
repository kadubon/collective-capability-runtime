from __future__ import annotations

from ccr.runtime.init import init_runtime


def test_ccr_init_is_idempotent(tmp_path):
    first = init_runtime(tmp_path)
    second = init_runtime(tmp_path)
    assert first["ok"] is True
    assert second["ok"] is True
    assert (tmp_path / "blackboard" / "events.jsonl").exists()
    assert (tmp_path / "ccr.config.json").exists()
    assert "ccr.config.json" in second["existing"]
