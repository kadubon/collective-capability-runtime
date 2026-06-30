from __future__ import annotations

from ccr.adapters.pic import PicVerifierProvider
from ccr.residuals.model import build_residual, to_packet_residual


def test_pic_candidate_only_reasons_are_normalized_as_residual_inputs():
    report = {
        "accepted": True,
        "candidate_only_reasons": ["external source not checked"],
        "packet_id": "packet.example",
        "settled": False,
    }
    normalized = PicVerifierProvider().normalize_report(report)
    assert normalized["ccr_status"] == "provisional"
    assert normalized["candidate_only_reasons"] == ["external source not checked"]


def test_packet_residual_conversion_preserves_blocking_and_description():
    residual = build_residual(
        kind="candidate_only_reason",
        description="Candidate-only reason",
        blocking=False,
        object_type="packet",
        object_id="packet.example",
    )
    embedded = to_packet_residual(residual)
    assert embedded["kind"] == "other"
    assert embedded["description"] == "Candidate-only reason"
    assert embedded["blocking"] is False
