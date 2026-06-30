# SPDX-License-Identifier: Apache-2.0
"""Module entry point for ``python -m ccr``."""

from __future__ import annotations

from ccr.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
