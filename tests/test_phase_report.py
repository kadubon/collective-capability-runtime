from __future__ import annotations

from ccr.reports.json_report import phase_report


def test_phase_report_is_deterministic(runtime_root):
    first = phase_report(runtime_root)
    second = phase_report(runtime_root)
    assert first == second
    assert "CCR does not detect real ASI." in first["non_claims"]
