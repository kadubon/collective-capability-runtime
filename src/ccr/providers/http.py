# SPDX-License-Identifier: Apache-2.0
"""Explicit HTTP provider with dry-run default."""

from __future__ import annotations

import ipaddress
import json
import socket
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ccr.ids import stable_id
from ccr.providers.base import Provider
from ccr.strict import strict_bool
from ccr.time import now_iso


class HttpProvider(Provider):
    """HTTP provider that requires explicit configuration before network IO."""

    provider_name = "http"
    allowed_methods: ClassVar[set[str]] = {"GET", "POST"}

    def capabilities(self) -> dict[str, Any]:
        return {
            "actions": ["webhook", "import_report"],
            "default_mode": "dry_run",
            "executes_network": True,
            "provider": self.provider_name,
            "requires_config": True,
        }

    def health(self) -> dict[str, Any]:
        return {
            "available": True,
            "provider": self.provider_name,
            "requires_explicit_config": True,
        }

    def plan(self, *, action: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
        return {
            "action": action,
            "dry_run": True,
            "network_call_performed": False,
            "payload_digest": stable_id("payload", payload),
            "provider": self.provider_name,
            "required_config_fields": [
                "endpoint",
                "method",
                "allow_execute",
                "timeout_seconds",
                "byte_limit",
            ],
        }

    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        root: Path,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            allow_execute = strict_bool(
                config.get("allow_execute"), field="allow_execute", default=False
            )
        except ValueError as exc:
            return _failure(str(exc))
        if not allow_execute:
            return {
                "error": "HTTP provider execution requires allow_execute=true in config.",
                "network_call_performed": False,
                "ok": False,
                "provider": self.provider_name,
            }
        endpoint = str(config.get("endpoint", ""))
        method = str(config.get("method", "POST")).upper()
        timeout_seconds = config.get("timeout_seconds", 30)
        byte_limit = config.get("byte_limit", 1048576)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 1 <= timeout_seconds <= 60
        ):
            return _failure("timeout_seconds must be an integer from 1 through 60")
        if (
            isinstance(byte_limit, bool)
            or not isinstance(byte_limit, int)
            or not 1 <= byte_limit <= 10_000_000
        ):
            return _failure("byte_limit must be an integer from 1 through 10000000")
        parsed_endpoint = urlsplit(endpoint)
        if parsed_endpoint.scheme != "https" or not parsed_endpoint.hostname:
            return _failure("HTTP provider endpoint must use HTTPS.")
        allowed_hosts = config.get("allowed_hosts")
        if not isinstance(allowed_hosts, list) or parsed_endpoint.hostname not in {
            str(item).lower() for item in allowed_hosts
        }:
            return _failure("HTTP provider hostname is not in allowed_hosts.")
        try:
            _validate_public_hostname(parsed_endpoint.hostname, parsed_endpoint.port or 443)
        except (OSError, ValueError) as exc:
            return _failure(f"HTTP provider endpoint rejected: {exc}")
        if method not in self.allowed_methods:
            return {
                "error": f"HTTP method not allowed: {method}",
                "network_call_performed": False,
                "ok": False,
                "provider": self.provider_name,
            }
        headers = {
            str(key): str(value)
            for key, value in dict(config.get("headers", {})).items()
            if key.lower() not in {"authorization", "cookie"}
        }
        body = None
        if method == "POST":
            body = json.dumps(payload, sort_keys=True).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        request = Request(endpoint, data=body, headers=headers, method=method)
        opener = build_opener(_NoRedirect())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:  # nosec B310
                raw = response.read(byte_limit + 1)
                truncated = len(raw) > byte_limit
                raw = raw[:byte_limit]
                text = raw.decode("utf-8", errors="replace")
                parsed: Any = None
                with suppress(json.JSONDecodeError):
                    parsed = json.loads(text)
                return {
                    "action": action,
                    "created_at": now_iso(),
                    "http_status": response.status,
                    "network_call_performed": True,
                    "ok": 200 <= response.status < 300,
                    "provider": self.provider_name,
                    "response_json": parsed if isinstance(parsed, dict) else None,
                    "response_text": text if parsed is None else "",
                    "truncated": truncated,
                }
        except (HTTPError, URLError) as exc:
            return {
                "action": action,
                "created_at": now_iso(),
                "error": _redact_error(str(exc)),
                "network_call_performed": True,
                "ok": False,
                "provider": self.provider_name,
            }

    def normalize(self, report: dict[str, Any]) -> dict[str, Any]:
        response_json = report.get("response_json")
        source: dict[str, Any] = response_json if isinstance(response_json, dict) else report
        accepted = strict_bool(
            source.get("accepted"),
            field="accepted",
            default=strict_bool(report.get("ok"), field="ok", default=False),
        )
        settled = strict_bool(source.get("settled"), field="settled", default=False)
        ccr_status = "checked" if accepted else "rejected"
        return {
            "accepted": accepted,
            "candidate_only_reasons": _as_list(source.get("candidate_only_reasons", [])),
            "ccr_status": ccr_status,
            "import_id": stable_id("http-import", report),
            "packet_id": source.get("packet_id"),
            "provider": self.provider_name,
            "safe_commands": _as_list(source.get("safe_commands", [])),
            "schema_version": "ccr.provider_import.v1",
            "settled": settled,
            "settled_blockers": _as_list(source.get("settled_blockers", [])),
        }


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _validate_public_hostname(hostname: str, port: int) -> None:
    addresses = {item[4][0] for item in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)}
    if not addresses:
        raise ValueError("hostname did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("hostname resolves to a non-public address")


def _failure(error: str) -> dict[str, Any]:
    return {
        "error": error,
        "network_call_performed": False,
        "ok": False,
        "provider": "http",
    }


def _redact_error(message: str) -> str:
    return message.split("?", 1)[0][:500]
