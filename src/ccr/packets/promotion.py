# SPDX-License-Identifier: Apache-2.0
"""Deterministic packet promotion rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ccr.blackboard.events import make_event
from ccr.blackboard.store import append_event
from ccr.packets.status import can_attempt_promotion
from ccr.packets.store import load_packet, save_packet_at_status, validate_packet
from ccr.residuals.model import build_residual, to_packet_residual
from ccr.residuals.store import linked_open_blocking_residuals, save_residual
from ccr.time import now_iso


def _required_verifier_accepts(packet: dict[str, Any]) -> bool:
    required = [item for item in packet.get("verifiers", []) if item.get("required")]
    if not required:
        return False
    reports = packet.get("verifier_reports", [])
    for verifier in required:
        provider = verifier.get("provider")
        verifier_id = verifier.get("verifier_id")
        for report in reports:
            if not report.get("accepted"):
                continue
            if report.get("provider") == provider or report.get("report_id") == verifier_id:
                return True
    return False


def _no_authority_bypass(packet: dict[str, Any]) -> bool:
    risk = packet.get("risk", {})
    if risk.get("authority_level") == "external_side_effect":
        return False
    execution = packet.get("execution_availability", {})
    if isinstance(execution, dict):
        policy = str(execution.get("side_effect_policy", "none")).lower()
        if policy not in {"none", "dry_run_only", "not_applicable"}:
            return False
    return True


def _scope_declared(packet: dict[str, Any]) -> bool:
    scope = packet.get("scope", {})
    return bool(scope.get("validity_domain")) and bool(scope.get("profiles"))


def _settlement_meta(packet: dict[str, Any]) -> dict[str, Any]:
    extensions = packet.get("extensions", {})
    if not isinstance(extensions, dict):
        return {}
    meta = extensions.get("settlement", {})
    return meta if isinstance(meta, dict) else {}


def _settlement_target_satisfied(packet: dict[str, Any]) -> bool:
    meta = _settlement_meta(packet)
    return meta.get("target_satisfied") is True


def _lineage_closed(packet: dict[str, Any]) -> bool:
    meta = _settlement_meta(packet)
    return meta.get("lineage_closed") is True


def _integration_policy_passed(packet: dict[str, Any]) -> bool:
    meta = _settlement_meta(packet)
    return meta.get("integration_policy_passed") is True


def _risk_in_envelope(packet: dict[str, Any]) -> bool:
    risk = packet.get("risk", {})
    if risk.get("authority_level") == "external_side_effect":
        return False
    return all(
        risk.get(key) != "critical" for key in ("hazard_level", "misuse_risk", "overclaim_risk")
    )


def _blocking_residuals(root: Path, packet: dict[str, Any]) -> list[dict[str, Any]]:
    packet_blockers = [
        residual
        for residual in packet.get("residuals", [])
        if isinstance(residual, dict) and residual.get("blocking")
    ]
    ledger_blockers = linked_open_blocking_residuals(root, str(packet["packet_id"]))
    return packet_blockers + ledger_blockers


def evaluate_promotion(
    root: Path, packet: dict[str, Any], *, target: str
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Evaluate promotion and return ok, reasons, residuals to preserve."""

    status_before = str(packet.get("status", "candidate"))
    reasons: list[str] = []
    residuals: list[dict[str, Any]] = []

    if not can_attempt_promotion(status_before, target):
        reasons.append(f"invalid status transition {status_before}->{target}")

    if target == "checked":
        validation = validate_packet(packet, root=root)
        if not validation.ok:
            reasons.append("packet schema is invalid")
        if not _required_verifier_accepts(packet):
            reasons.append("no required verifier has accepted the packet")
        if "residuals" not in packet:
            reasons.append("residual ledger is missing")
        if not _no_authority_bypass(packet):
            reasons.append("authority bypass or side-effectful execution request is present")

    if target == "settled":
        validation = validate_packet(packet, root=root)
        if not validation.ok:
            reasons.append("packet schema is invalid")
        blockers = _blocking_residuals(root, packet)
        if blockers:
            reasons.append("blocking residuals prevent settlement")
        if not _settlement_target_satisfied(packet):
            reasons.append("settlement target is not satisfied")
        if not _lineage_closed(packet):
            reasons.append("lineage is not closed")
        if not _scope_declared(packet):
            reasons.append("scope is not declared")
        if not _risk_in_envelope(packet):
            reasons.append("risk is outside the declared envelope")
        if not _integration_policy_passed(packet):
            reasons.append("integration policy has not passed")

    if target in {"quarantined", "deprecated"}:
        return True, [], []

    if reasons:
        residual_kind = "settlement_blocker" if target == "settled" else "unverified_claim"
        if any("authority" in reason for reason in reasons):
            residual_kind = "authority_gap"
        residuals.append(
            build_residual(
                kind=residual_kind,
                description=f"Promotion to {target} failed: {'; '.join(reasons)}",
                blocking=True,
                object_type="packet",
                object_id=str(packet["packet_id"]),
                refs=[str(packet["packet_id"])],
                source="ccr.packet.promote",
                repair_hint="Satisfy the listed promotion gates and retry promotion.",
            )
        )
    return not reasons, reasons, residuals


def promote_packet(
    root: Path, packet_id: str, *, target: str, actor: str = "ccr"
) -> dict[str, Any]:
    """Promote a packet, preserving residuals on failure."""

    packet, old_path, status_before = load_packet(root, packet_id)
    ok, reasons, residuals = evaluate_promotion(root, packet, target=target)
    residual_ids: list[str] = []
    for residual in residuals:
        save_residual(root, residual, overwrite=True)
        residual_ids.append(str(residual["residual_id"]))
        embedded = to_packet_residual(residual)
        packet.setdefault("residuals", [])
        already_embedded = any(
            item.get("residual_id") == embedded["residual_id"] for item in packet["residuals"]
        )
        if not already_embedded:
            packet["residuals"].append(embedded)

    if ok:
        packet["updated_at"] = now_iso()
        save_packet_at_status(root, packet, status=target, old_path=old_path)
        append_event(
            root,
            make_event(
                action="packet.promote",
                actor=actor,
                object_type="packet",
                object_id=packet_id,
                status_before=status_before,
                status_after=target,
                residuals=residual_ids,
            ),
        )
        return {
            "ok": True,
            "packet_id": packet_id,
            "residuals": residual_ids,
            "status_after": target,
            "status_before": status_before,
        }

    save_packet_at_status(root, packet, status=status_before, old_path=old_path)
    append_event(
        root,
        make_event(
            action="packet.promote.failed",
            actor=actor,
            object_type="packet",
            object_id=packet_id,
            status_before=status_before,
            status_after=status_before,
            residuals=residual_ids,
            note="; ".join(reasons),
        ),
    )
    return {
        "ok": False,
        "packet_id": packet_id,
        "reasons": reasons,
        "residuals": residual_ids,
        "status_after": status_before,
        "status_before": status_before,
    }
