# SPDX-License-Identifier: Apache-2.0
"""Require all native modules and 95% statements / 90% branch coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    expected = {
        p.name
        for p in (Path(__file__).resolve().parents[1] / "src/ccr/optimizer").glob("native_*.py")
    }
    rows = {
        Path(name.replace("\\", "/")).name: value["summary"]
        for name, value in report["files"].items()
        if Path(name.replace("\\", "/")).name in expected
    }
    totals = {
        key: sum(row[key] for row in rows.values())
        for key in ("covered_lines", "num_statements", "covered_branches", "num_branches")
    }
    statements = 100 * totals["covered_lines"] / max(totals["num_statements"], 1)
    branches = 100 * totals["covered_branches"] / max(totals["num_branches"], 1)
    missing = sorted(expected - rows.keys())
    underqualified = {
        name: {
            "statement_percent": 100 * row["covered_lines"] / max(row["num_statements"], 1),
            "branch_percent": 100 * row["covered_branches"] / row["num_branches"]
            if row["num_branches"]
            else 100,
        }
        for name, row in rows.items()
        if row["covered_lines"] < 0.95 * row["num_statements"]
        or row["covered_branches"] < 0.90 * row["num_branches"]
    }
    ok = (
        not missing
        and not underqualified
        and statements >= 95
        and branches >= 90
        and totals["num_branches"] > 0
    )
    print(
        json.dumps(
            {
                "ok": ok,
                "missing_modules": missing,
                "underqualified_modules": underqualified,
                "statement_percent": statements,
                "branch_percent": branches,
                **totals,
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
