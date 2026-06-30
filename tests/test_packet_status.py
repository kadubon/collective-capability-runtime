from __future__ import annotations

from ccr.packets.store import submit_packet
from tests.conftest import example_json


def test_packet_submit_stores_candidate(runtime_root):
    packet = example_json("examples/minimal/packet.json")
    path = submit_packet(runtime_root, packet)
    assert path.exists()
    assert path.parent.name == "candidate"
