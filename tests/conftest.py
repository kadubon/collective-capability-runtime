from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from ccr.io import read_json
from ccr.runtime.init import init_runtime

REPO_ROOT = Path(__file__).resolve().parents[1]


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
