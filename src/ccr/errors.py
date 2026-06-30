# SPDX-License-Identifier: Apache-2.0
"""CCR error types and exit codes."""

from __future__ import annotations

from typing import Any

EXIT_SUCCESS = 0
EXIT_POLICY_FAILURE = 1
EXIT_MISSING = 2
EXIT_INTERNAL = 3


class CCRException(Exception):
    """Base exception carrying a stable machine-readable payload."""

    def __init__(self, message: str, *, exit_code: int, payload: dict[str, Any] | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.payload = payload or {"ok": False, "error": message}


class CCRValidationError(CCRException):
    """Validation or policy failure."""

    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message, exit_code=EXIT_POLICY_FAILURE, payload=payload)


class CCRMissingError(CCRException):
    """Missing file, task, packet, or provider."""

    def __init__(self, message: str, payload: dict[str, Any] | None = None):
        super().__init__(message, exit_code=EXIT_MISSING, payload=payload)
