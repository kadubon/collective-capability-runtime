# SPDX-License-Identifier: Apache-2.0
"""Cryptographic physical-observation verifier boundary."""

from __future__ import annotations

import base64
import importlib
from datetime import datetime, timezone
from typing import Any

from ccr.ids import canonical_bytes, sha256_bytes, sha256_json


def verify_physical_observation(
    *, plan: dict[str, Any], observation: dict[str, Any]
) -> tuple[bool, str | None]:
    """Verify Ed25519 evidence bound to observation, scope, and time window."""

    report = observation.get("verifier_report")
    if not isinstance(report, dict):
        return False, "physical_outcome_verifier_report_missing"
    if (
        report.get("schema_version") != "ccr.observation_verification_report.v1"
        or report.get("accepted") is not True
        or report.get("signature_alg") != "ed25519"
    ):
        return False, "physical_outcome_verifier_report_invalid"
    payload = report.get("signed_payload")
    if not isinstance(payload, dict):
        return False, "physical_outcome_signed_payload_missing"
    public_key = _decode(report.get("public_key_base64"))
    signature = _decode(report.get("signature_base64"))
    if public_key is None or signature is None or len(public_key) != 32:
        return False, "physical_outcome_signature_encoding_invalid"
    trusted = plan.get("trusted_verifier_key_digests")
    if not isinstance(trusted, list) or sha256_bytes(public_key) not in {
        str(item) for item in trusted
    }:
        return False, "physical_outcome_verifier_key_untrusted"
    observation_payload = {
        key: value for key, value in observation.items() if key != "verifier_report"
    }
    if payload.get("observation_sha256") != sha256_json(observation_payload):
        return False, "physical_outcome_observation_digest_mismatch"
    if not _scope_matches(plan, payload.get("scope")):
        return False, "physical_outcome_verifier_scope_mismatch"
    observed_at = _time(observation.get("observed_at"))
    valid_from = _time(payload.get("valid_from"))
    valid_until = _time(payload.get("valid_until"))
    if (
        observed_at is None
        or valid_from is None
        or valid_until is None
        or not valid_from <= observed_at <= valid_until
    ):
        return False, "physical_outcome_verifier_window_invalid"
    try:
        ed25519 = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        key = ed25519.Ed25519PublicKey.from_public_bytes(public_key)
        key.verify(signature, canonical_bytes(payload))
    except ImportError:
        return False, "physical_outcome_verifier_crypto_unavailable"
    except Exception:
        return False, "physical_outcome_signature_invalid"
    return True, None


def _scope_matches(plan: dict[str, Any], scope: Any) -> bool:
    if not isinstance(scope, dict) or not scope:
        return False
    domains = [
        operation.get("validity_domain")
        for operation in plan.get("operations", [])
        if isinstance(operation, dict) and isinstance(operation.get("validity_domain"), dict)
    ]
    return scope in domains


def _decode(value: Any) -> bytes | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        return None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)
