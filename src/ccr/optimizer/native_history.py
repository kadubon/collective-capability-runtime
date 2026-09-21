# SPDX-License-Identifier: Apache-2.0
"""Visible native observations derived only from authenticated CCR outcomes."""

from __future__ import annotations

from typing import Any

from ccr.optimizer import growth_ledger


def cpcf_history(run: dict[str, Any], contract: str) -> list[dict[str, Any]]:
    """Reconstruct the registered observation channel, never a hidden model branch.

    The channel is a synthetic, preregistered interpretation of signed result
    statuses. It is not an empirical identification of CPCF's hidden models.
    Unmapped outcomes prohibit continuation rather than guessing a symbol.
    """
    growth_ledger.replay(run, run["created_at"])
    bindings = run["native_registration"]["bindings"]
    history = []
    for event in run["growth_events"]:
        if event["kind"] != "outcome":
            continue
        outcome = event["payload"]
        binding = bindings.get(outcome["action_id"])
        if (
            outcome["group"] != "training"
            or binding is None
            or binding["producer"] != "cpcf"
            or binding["contract_sha256"] != contract
        ):
            continue
        symbol = binding.get("observations", {}).get(outcome["status"])
        if symbol is None or not outcome["qualified"]:
            raise ValueError("CPCF outcome has no qualified registered observation")
        history.append(
            {
                "action_id": binding["source_action"],
                "observation": symbol,
                "entry": False,
                "comparison_history_length": 0,
            }
        )
    return history
