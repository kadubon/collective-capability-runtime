# SPDX-License-Identifier: Apache-2.0
"""Explicit HTTP provider with dry-run default."""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar
from urllib.error import URLError
from urllib.request import Request, urlopen

from ccr.ids import stable_id
from ccr.providers.base import Provider
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
        if not config.get("allow_execute"):
            return {
                "error": "HTTP provider execution requires allow_execute=true in config.",
                "network_call_performed": False,
                "ok": False,
                "provider": self.provider_name,
            }
        endpoint = str(config.get("endpoint", ""))
        method = str(config.get("method", "POST")).upper()
        timeout_seconds = int(config.get("timeout_seconds", 30))
        byte_limit = int(config.get("byte_limit", 1048576))
        if not endpoint.startswith(("https://", "http://")):
            return {
                "error": "HTTP provider endpoint must be http or https.",
                "network_call_performed": False,
                "ok": False,
                "provider": self.provider_name,
            }
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
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
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
        except URLError as exc:
            return {
                "action": action,
                "created_at": now_iso(),
                "error": str(exc),
                "network_call_performed": True,
                "ok": False,
                "provider": self.provider_name,
            }

    def normalize(self, report: dict[str, Any]) -> dict[str, Any]:
        response_json = report.get("response_json")
        source: dict[str, Any] = response_json if isinstance(response_json, dict) else report
        accepted = bool(source.get("accepted", report.get("ok", False)))
        settled = bool(source.get("settled", False))
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
