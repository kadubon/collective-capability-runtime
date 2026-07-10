# SPDX-License-Identifier: Apache-2.0
"""Opt-in OpenTelemetry events with sensitive-field suppression."""

from __future__ import annotations

import importlib
import os
from typing import Any

_SENSITIVE_TOKENS = ("prompt", "secret", "password", "token", "cookie", "authorization", "pii")


def emit_event_span(name: str, attributes: dict[str, Any]) -> None:
    """Emit a short event span only when telemetry is explicitly enabled."""

    if os.environ.get("CCR_OTEL_ENABLED") != "1":
        return
    try:
        trace = importlib.import_module("opentelemetry.trace")
    except ImportError:
        return
    sanitized = {
        key: value
        for key, value in attributes.items()
        if not any(token in key.casefold() for token in _SENSITIVE_TOKENS)
        and isinstance(value, str | int | float | bool)
    }
    tracer = trace.get_tracer("collective-capability-runtime")
    with tracer.start_as_current_span(name, attributes=sanitized):
        pass
