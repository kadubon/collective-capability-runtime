# SPDX-License-Identifier: Apache-2.0
"""Derive installed source/schema hashes from previously verified release wheels."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel_directory", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = root / "examples/native_interchange"
    artifacts = json.loads((directory / "artifacts.json").read_text(encoding="utf-8"))
    pins = {}
    for producer in artifacts:
        wheel = next(a for a in producer["artifacts"] if a["filename"].endswith(".whl"))
        path = args.wheel_directory / wheel["filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != wheel["sha256"]:
            raise ValueError("release wheel hash mismatch: " + path.name)
        with zipfile.ZipFile(path) as archive:
            files = {
                name: hashlib.sha256(archive.read(name)).hexdigest()
                for name in sorted(archive.namelist())
                if name.endswith((".py", ".json", "/METADATA"))
            }
        pins[producer["producer"]] = {
            "package": producer["package"],
            "version": producer["version"],
            "wheel_sha256": wheel["sha256"],
            "files": files,
        }
    (directory / "installed-pins.json").write_text(
        json.dumps(pins, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
