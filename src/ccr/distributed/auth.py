# SPDX-License-Identifier: Apache-2.0
"""OIDC access-token and RFC 9449 DPoP verification."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import time
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ccr.ids import canonical_bytes
from ccr.storage.base import RuntimeStore


class AuthError(ValueError):
    pass


def verify_oidc_dpop(
    *,
    authorization: str | None,
    dpop_proof: str | None,
    method: str,
    url: str,
    config: dict[str, Any],
    store: RuntimeStore,
) -> dict[str, Any]:
    """Verify OIDC claims, proof-of-possession, and one-time DPoP jti."""

    if not authorization or not authorization.startswith("DPoP "):
        raise AuthError("Authorization must use the DPoP scheme")
    if not dpop_proof:
        raise AuthError("DPoP proof is required")
    credential = authorization.removeprefix("DPoP ").strip()
    jose = _jose()
    jwks = config.get("jwks")
    if not isinstance(jwks, dict):
        raise AuthError("OIDC jwks configuration is required")
    key_set = jose.JsonWebKey.import_key_set(jwks)
    claims = jose.JsonWebToken(["RS256", "ES256", "EdDSA"]).decode(
        credential,
        key_set,
        claims_options={
            "iss": {"essential": True, "value": config.get("issuer")},
            "aud": {"essential": True, "value": config.get("audience")},
            "exp": {"essential": True},
            "sub": {"essential": True},
        },
    )
    claims.validate(now=int(time.time()), leeway=30)
    proof_header = _jwt_header(dpop_proof)
    proof_jwk = proof_header.get("jwk")
    if proof_header.get("typ") != "dpop+jwt" or not isinstance(proof_jwk, dict):
        raise AuthError("DPoP header must contain typ=dpop+jwt and a public jwk")
    if proof_jwk.get("d") is not None:
        raise AuthError("DPoP proof must not expose a private key")
    proof = jose.JsonWebToken(["ES256", "EdDSA", "RS256"]).decode(dpop_proof, proof_jwk)
    proof.validate(now=int(time.time()), leeway=30)
    normalized_url = _normalized_htu(url)
    if proof.get("htm") != method.upper() or proof.get("htu") != normalized_url:
        raise AuthError("DPoP method or target URI does not match the request")
    issued_at = proof.get("iat")
    if not isinstance(issued_at, int) or abs(int(time.time()) - issued_at) > 300:
        raise AuthError("DPoP proof is outside the allowed time window")
    jti = proof.get("jti")
    if not isinstance(jti, str) or not jti:
        raise AuthError("DPoP proof requires jti")
    if proof.get("ath") != _access_token_hash(credential):
        raise AuthError("DPoP access-token hash does not match")
    confirmation = claims.get("cnf")
    if not isinstance(confirmation, dict) or confirmation.get("jkt") != _jwk_thumbprint(proof_jwk):
        raise AuthError("OIDC token is not bound to the DPoP key")
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    if not store.consume_dpop_jti(jti=jti, expires_at=expires_at):
        raise AuthError("DPoP proof replay detected")
    return dict(claims)


def identity_class(claims: dict[str, Any], config: dict[str, Any]) -> str:
    subject = str(claims.get("sub", ""))
    worker_prefix = str(config.get("worker_subject_prefix", "worker:"))
    human_prefix = str(config.get("human_subject_prefix", "human:"))
    if subject.startswith(worker_prefix):
        return "worker"
    if subject.startswith(human_prefix):
        return "human"
    raise AuthError("OIDC subject is neither an allowed worker nor human identity")


def _jose() -> Any:
    try:
        deprecate = importlib.import_module("authlib.deprecate")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", deprecate.AuthlibDeprecationWarning)
            return importlib.import_module("authlib.jose")
    except ImportError as exc:
        raise RuntimeError("API authentication requires the 'distributed' extra") from exc


def _jwt_header(token: str) -> dict[str, Any]:
    try:
        segment = token.split(".", 1)[0]
        decoded = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
        header = json.loads(decoded)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("invalid JWT header") from exc
    if not isinstance(header, dict):
        raise AuthError("invalid JWT header")
    return header


def _access_token_hash(token: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(token.encode()).digest()).rstrip(b"=").decode()


def _jwk_thumbprint(jwk: dict[str, Any]) -> str:
    members_by_type = {
        "EC": ("crv", "kty", "x", "y"),
        "OKP": ("crv", "kty", "x"),
        "RSA": ("e", "kty", "n"),
    }
    keys = members_by_type.get(str(jwk.get("kty")))
    if keys is None or any(key not in jwk for key in keys):
        raise AuthError("unsupported or incomplete DPoP jwk")
    public = {key: jwk[key] for key in keys}
    return (
        base64.urlsafe_b64encode(hashlib.sha256(canonical_bytes(public)).digest())
        .rstrip(b"=")
        .decode()
    )


def _normalized_htu(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
