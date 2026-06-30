# SPDX-License-Identifier: Apache-2.0
"""Base verifier provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseVerifierProvider(ABC):
    """Common interface for optional verifier providers."""

    provider_name: str

    @abstractmethod
    def availability(self) -> dict[str, Any]:
        """Return provider availability data."""

    @abstractmethod
    def plan_verify(
        self, packet: dict[str, Any], *, profile: str, packet_path: str
    ) -> dict[str, Any]:
        """Return a dry-run verification plan."""

    @abstractmethod
    def execute_verify(
        self,
        packet: dict[str, Any],
        *,
        profile: str,
        packet_path: str,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        """Execute verification only after explicit operator request."""

    @abstractmethod
    def normalize_report(self, report: dict[str, Any]) -> dict[str, Any]:
        """Normalize a provider report into CCR structures."""
