from __future__ import annotations

from ccr.phase.baseline import compare_observation_to_baseline


def test_baseline_resource_mismatch_preserves_blocking_residual():
    baseline = {
        "baseline_id": "baseline.test",
        "metrics": {"positive_packet_count": 1},
        "resource_envelope": {"agent_count": 1, "profile": "development"},
    }
    observation = {
        "observation_id": "observation.test",
        "positive_packet_count": 2,
        "resource_envelope": {"agent_count": 2, "profile": "development"},
        "residual_debt": 0.0,
    }

    comparison = compare_observation_to_baseline(baseline, observation)

    assert comparison["accepted"] is False
    assert comparison["resource_matched"] is False
    assert comparison["residual_ready"]["blocking"] is True
    assert comparison["residual_ready"]["kind"] == "settlement_blocker"
