# SPDX-License-Identifier: Apache-2.0
"""PIC provider wrapper for the v1 provider API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.adapters.pic import PicVerifierProvider
from ccr.packets.store import load_packet
from ccr.providers.base import Provider


class PicProvider(Provider):
    """Provider wrapper around the optional PIC adapter."""

    provider_name = "pic"

    def __init__(self) -> None:
        self._adapter = PicVerifierProvider()

    def capabilities(self) -> dict[str, Any]:
        return {
            "actions": ["verify_packet", "phase_plan"],
            "default_mode": "dry_run",
            "executes_shell": False,
            "expected_pic_commands": [
                "pic agent check --compact",
                "pic packet inspect",
                "pic phase plan --compact",
                "pic runtime collective-certify",
            ],
            "interop_boundary": [
                "PIC is optional and never a hard dependency.",
                "PIC accepted/workflow_usable/settled fields never settle CCR directly.",
                "PIC safe_commands are imported as task hints only.",
            ],
            "provider": self.provider_name,
            "supported_import_fields": [
                "accepted",
                "workflow_usable",
                "settled",
                "candidate_only_reasons",
                "settled_blockers",
                "safe_commands",
                "phase_gap_vector",
                "bottlenecks",
                "missing_obligations",
                "residuals",
                "cannot_promote_because",
            ],
        }

    def health(self) -> dict[str, Any]:
        return self._adapter.availability()

    def plan(self, *, action: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
        if action == "verify_packet":
            packet_id = str(payload["packet_id"])
            packet, packet_path, _status = load_packet(root, packet_id)
            return self._adapter.plan_verify(
                packet,
                profile=str(payload.get("profile", "development")),
                packet_path=str(packet_path),
            )
        if action == "phase_plan":
            profile = str(payload.get("profile", "development"))
            return {
                "dry_run": True,
                "provider": self.provider_name,
                "recommended_argv": [
                    "pic",
                    "phase",
                    "plan",
                    "--compact",
                    "--profile",
                    profile,
                ],
                "safe_command_policy": "task_hints_only",
            }
        raise ValueError(f"unsupported PIC provider action: {action}")

    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        root: Path,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if action != "verify_packet":
            return {
                "error": "PIC provider execution is implemented only for verify_packet.",
                "ok": False,
                "provider": self.provider_name,
            }
        packet_id = str(payload["packet_id"])
        packet, packet_path, _status = load_packet(root, packet_id)
        return self._adapter.execute_verify(
            packet,
            profile=str(payload.get("profile", "development")),
            packet_path=str(packet_path),
            timeout_seconds=int(config.get("timeout_seconds", 60)),
        )

    def normalize(self, report: dict[str, Any]) -> dict[str, Any]:
        return self._adapter.normalize_report(report)
