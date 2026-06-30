from __future__ import annotations

from ccr.packets.store import submit_packet
from ccr.phase.certify import build_certificate_candidate
from ccr.phase.graph import build_effective_graph
from ccr.phase.observe import build_phase_observation
from ccr.residuals.model import build_residual
from ccr.residuals.store import save_residual
from tests.conftest import example_json


def _load_phase_example_packets(root):
    for relative in [
        "examples/phase_formation/packets/checked/packet.phase.seed.json",
        "examples/phase_formation/packets/checked/packet.phase.integrator.json",
        "examples/phase_formation/packets/candidate/packet.phase.duplicate.json",
    ]:
        submit_packet(root, example_json(relative))


def test_effective_graph_excludes_candidate_duplicate_volume(runtime_root):
    _load_phase_example_packets(runtime_root)

    graph = build_effective_graph(runtime_root)

    assert graph["accepted_packet_capital"] == 2
    assert graph["candidate_only_packets"] == 1
    assert graph["positive_edge_count"] >= 1
    duplicate = next(
        node for node in graph["nodes"] if node["packet_id"] == "packet.phase.duplicate"
    )
    assert duplicate["positive_contribution"] is False
    assert duplicate["candidate_only"] is True


def test_execution_available_path_does_not_imply_executed_path(runtime_root):
    _load_phase_example_packets(runtime_root)

    observation = build_phase_observation(runtime_root)

    assert observation["execution_available_path_count"] == 2
    assert observation["execution_available_path_density"] > 0
    assert observation["executed_path_count"] == 0
    assert observation["proves_real_asi"] is False


def test_blocking_residual_prevents_certificate_acceptance(runtime_root):
    _load_phase_example_packets(runtime_root)
    residual = build_residual(
        kind="settlement_blocker",
        description="Unresolved baseline review blocks certificate acceptance.",
        blocking=True,
        object_type="phase",
        object_id="phase.example",
        source="test",
    )
    save_residual(runtime_root, residual)

    certificate = build_certificate_candidate(runtime_root)

    assert certificate["accepted"] is False
    assert certificate["certificate_status"] == "abstain"
    assert certificate["settled"] is False
    assert any(defect["defect_type"] == "blocking_residual" for defect in certificate["defects"])
