# SPDX-License-Identifier: Apache-2.0
"""Offline source and schema verification against exact released wheel bytes."""

from __future__ import annotations

import hashlib
import json
from importlib import metadata, resources
from pathlib import Path
from typing import Any, cast

from ccr.ids import sha256_json


def manifest() -> dict[str, Any]:
    from ccr.schemas.loader import _repository_resource_path

    relative = "examples/native_interchange/installed-pins.json"
    repository = _repository_resource_path(relative)
    text = (
        repository.read_text(encoding="utf-8")
        if repository is not None
        else resources.files("ccr.data").joinpath(relative).read_text(encoding="utf-8")
    )
    return cast(dict[str, Any], json.loads(text))


def verify(producer: str) -> str:
    pin = manifest()[producer]
    distribution = metadata.distribution(pin["package"])
    if distribution.version != pin["version"]:
        raise ValueError("native checker installation version mismatch")
    for relative, expected in pin["files"].items():
        actual = hashlib.sha256(
            Path(str(distribution.locate_file(relative))).read_bytes()
        ).hexdigest()
        if actual != expected:
            raise ValueError("native checker source/schema hash mismatch: " + relative)
    return sha256_json(pin)
