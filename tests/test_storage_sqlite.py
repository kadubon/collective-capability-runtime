from __future__ import annotations

import sqlite3
from contextlib import closing

from ccr.packets.store import submit_packet
from ccr.storage.sqlite import database_path, index_runtime
from tests.conftest import example_json


def test_sqlite_init_and_index_preserves_json_runtime(runtime_root):
    assert database_path(runtime_root).exists()
    packet = example_json("examples/minimal/packet.json")
    submit_packet(runtime_root, packet)

    result = index_runtime(runtime_root)

    assert result["objects_indexed"] >= 1
    assert (runtime_root / "packets" / "candidate" / "packet.minimal.json").exists()
    with closing(sqlite3.connect(database_path(runtime_root))) as connection:
        row = connection.execute(
            "SELECT status, path FROM objects WHERE object_type = ? AND object_id = ?",
            ("packet", "packet.minimal"),
        ).fetchone()
    assert row is not None
    assert row[0] == "candidate"
    assert row[1].endswith("packet.minimal.json")
