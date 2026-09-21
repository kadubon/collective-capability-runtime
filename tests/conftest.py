from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from ccr.io import read_json
from ccr.runtime.init import init_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def native_test_clock(request: Any, monkeypatch: Any) -> Any:
    """Finite synthetic time only in native tests; keep real storage transactions.

    This removes checker-speed dependence from five-second native contracts.
    Database locking, rollback, CAS, outbox and independent clients remain real.
    """
    if not request.path.name.startswith("test_native_"):
        return None
    from contextlib import contextmanager
    from datetime import datetime, timezone

    from ccr.storage.control import ControlStore

    clock = {"now": datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
    original = ControlStore.edit_many

    @contextmanager
    def controlled(self: Any, *args: Any, **kwargs: Any) -> Any:
        with original(self, *args, **kwargs) as (objects, _):
            yield objects, clock["now"]

    monkeypatch.setattr(ControlStore, "now", lambda _: clock["now"])
    monkeypatch.setattr(ControlStore, "edit_many", controlled)
    return clock


@pytest.fixture
def runtime_root(tmp_path: Path) -> Path:
    init_runtime(tmp_path)
    return tmp_path


def example_json(relative: str) -> dict[str, Any]:
    data = read_json(REPO_ROOT / relative)
    assert isinstance(data, dict)
    return copy.deepcopy(data)


def cli_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src if not existing else f"{src}{os.pathsep}{existing}"
    return env
