from __future__ import annotations

from ccr.schemas.validation import validate_instance
from tests.conftest import example_json


def test_schema_validates_example_packet(runtime_root):
    packet = example_json("examples/minimal/packet.json")
    result = validate_instance("packet", packet, root=runtime_root)
    assert result.ok, [issue.to_json() for issue in result.errors]


def test_schema_rejects_missing_scope(runtime_root):
    packet = example_json("examples/minimal/packet.json")
    packet.pop("scope")
    result = validate_instance("packet", packet, root=runtime_root)
    assert not result.ok
    assert any(issue.path == "$" and "scope" in issue.message for issue in result.errors)


def test_schema_validates_example_task(runtime_root):
    task = example_json("examples/minimal/task.json")
    result = validate_instance("task", task, root=runtime_root)
    assert result.ok, [issue.to_json() for issue in result.errors]


def test_schema_validates_phase_formation_examples(runtime_root):
    cases = [
        ("packet", "examples/phase_formation/packets/checked/packet.phase.seed.json"),
        ("packet", "examples/phase_formation/packets/checked/packet.phase.integrator.json"),
        ("packet", "examples/phase_formation/packets/candidate/packet.phase.duplicate.json"),
        ("packet", "examples/pic_interop/packet_for_pic.json"),
        ("baseline", "examples/phase_formation/baseline.json"),
        ("asi-proxy-threshold", "examples/phase_formation/threshold.json"),
    ]
    for kind, path in cases:
        result = validate_instance(kind, example_json(path), root=runtime_root)
        assert result.ok, (kind, path, [issue.to_json() for issue in result.errors])
