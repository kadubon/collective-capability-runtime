# SPDX-License-Identifier: Apache-2.0
"""Optional PIC verifier provider adapter."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from ccr.adapters.base import BaseVerifierProvider
from ccr.ids import stable_id
from ccr.io import json_file_name
from ccr.packets.distill import packet_summary_text
from ccr.time import now_iso

# Security: PIC CLI execution uses shell=False, fixed argv, and a timeout.
PIC_PROFILES = {"development", "research", "controlled", "federated", "production", "adversarial"}


class PicVerifierProvider(BaseVerifierProvider):
    """PIC adapter with dry-run planning by default."""

    provider_name = "pic"

    def availability(self) -> dict[str, Any]:
        """Return PIC availability without importing it as a hard dependency."""

        executable = shutil.which("pic")
        module_available = importlib.util.find_spec("percolation_inversion_compiler") is not None
        return {
            "available": bool(executable or module_available),
            "executable": executable,
            "module_available": module_available,
            "provider": self.provider_name,
        }

    def plan_verify(
        self, packet: dict[str, Any], *, profile: str, packet_path: str
    ) -> dict[str, Any]:
        """Build a PIC dry-run plan. The command is never executed here."""

        if profile not in PIC_PROFILES:
            raise ValueError(f"unknown PIC profile: {profile}")
        text = packet_summary_text(packet)
        argv = ["pic", "agent", "check", "--compact", "--text", text, "--profile", profile]
        return {
            "dry_run": True,
            "expected_import_location": "reports/pic/",
            "packet_id": packet.get("packet_id"),
            "packet_path": packet_path,
            "provider": self.provider_name,
            "recommended_alternate_argv": ["pic", "packet", "inspect", "--packet", packet_path],
            "verification_argv": argv,
        }

    def execute_verify(
        self,
        packet: dict[str, Any],
        *,
        profile: str,
        packet_path: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        """Execute PIC through subprocess with no shell expansion."""

        availability = self.availability()
        executable = availability.get("executable")
        if not executable:
            return {
                "availability": availability,
                "error": (
                    "PIC executable 'pic' is unavailable; install PIC or run dry-run planning."
                ),
                "ok": False,
                "provider": self.provider_name,
            }
        plan = self.plan_verify(packet, profile=profile, packet_path=packet_path)
        argv = [str(executable), *plan["verification_argv"][1:]]
        # argv is fixed, shell=False, and the process is timeout-bound.
        completed = subprocess.run(  # nosec B603
            argv,
            capture_output=True,
            check=False,
            shell=False,
            text=True,
            timeout=timeout_seconds,
        )
        stdout_json: dict[str, Any] | None = None
        try:
            parsed = json.loads(completed.stdout)
            if isinstance(parsed, dict):
                stdout_json = parsed
        except json.JSONDecodeError:
            stdout_json = None
        return {
            "argv": argv,
            "created_at": now_iso(),
            "ok": completed.returncode == 0,
            "packet_id": packet.get("packet_id"),
            "packet_path": packet_path,
            "profile": profile,
            "provider": self.provider_name,
            "returncode": completed.returncode,
            "stderr": completed.stderr,
            "stdout": completed.stdout,
            "stdout_json": stdout_json,
        }

    def normalize_report(self, report: dict[str, Any]) -> dict[str, Any]:
        """Normalize PIC-like report fields into CCR status and residual inputs."""

        source = (
            report.get("stdout_json") if isinstance(report.get("stdout_json"), dict) else report
        )
        if not isinstance(source, dict):
            source = report
        workflow_usable = bool(source.get("workflow_usable", False))
        accepted = bool(source.get("accepted", workflow_usable))
        settled = bool(source.get("settled", False))
        candidate_only_reasons = _combine_lists(
            source,
            "candidate_only_reasons",
            "candidate_only",
        )
        settled_blockers = _combine_lists(source, "settled_blockers", "blockers")
        missing_obligations = _combine_lists(source, "missing_obligations")
        cannot_promote_because = _combine_lists(source, "cannot_promote_because")
        residuals = _combine_lists(source, "residuals", "residual_ledger")
        safe_commands = _combine_lists(source, "safe_commands", "next_safe_actions")
        reasons = _as_list(source.get("reasons", []))
        blocking_residuals = [
            item
            for item in residuals
            if isinstance(item, dict) and bool(item.get("blocking", False))
        ]
        status_blockers = (
            candidate_only_reasons
            + settled_blockers
            + missing_obligations
            + cannot_promote_because
            + blocking_residuals
        )
        unsafe = any(
            token in " ".join(str(item).lower() for item in reasons + settled_blockers)
            for token in ("unsafe", "hazard", "authority", "malformed")
        )
        if not accepted:
            ccr_status = "quarantined" if unsafe else "rejected"
        elif settled and not status_blockers:
            ccr_status = "checked"
        elif status_blockers:
            ccr_status = "provisional"
        else:
            ccr_status = "checked"

        packet_id = source.get("packet_id", report.get("packet_id"))
        profile = source.get("profile", report.get("profile", "development"))
        import_id = stable_id("pic-import", report)
        return {
            "accepted": accepted,
            "bottlenecks": _as_list(source.get("bottlenecks", [])),
            "candidate_only_reasons": candidate_only_reasons,
            "ccr_status": ccr_status,
            "cannot_promote_because": cannot_promote_because,
            "import_id": import_id,
            "missing_obligations": missing_obligations,
            "notes": (
                "PIC accepted output imported as checked/provisional, not settled. "
                "Final CCR settlement requires CCR gates."
            ),
            "packet_id": packet_id,
            "phase_gap_vector": source.get("phase_gap_vector"),
            "pic_profile": profile,
            "pic_report_type": str(source.get("report_type", source.get("type", "PICReport"))),
            "residuals": residuals,
            "safe_commands": safe_commands,
            "schema_version": "ccr.pic_import.v0.1",
            "sdk_calls": _as_list(source.get("sdk_calls", [])),
            "settled": settled,
            "settled_blockers": settled_blockers,
            "settled_candidate": bool(accepted and settled),
            "workflow_usable": workflow_usable,
        }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _combine_lists(source: dict[str, Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        values.extend(_as_list(source.get(key)))
    return values


def report_output_path(root: Path, report_id: str) -> Path:
    """Return PIC report output path."""

    return root / "reports" / "pic" / json_file_name(report_id)
