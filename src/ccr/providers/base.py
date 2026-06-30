# SPDX-License-Identifier: Apache-2.0
"""Provider interface for optional external integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Provider(ABC):
    """Explicit provider interface.

    Providers must be dry-run by default and must not hide network or command
    execution behind planning calls.
    """

    provider_name: str

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Return provider capabilities."""

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return provider availability and configuration status."""

    @abstractmethod
    def plan(self, *, action: str, payload: dict[str, Any], root: Path) -> dict[str, Any]:
        """Return a non-mutating provider plan."""

    @abstractmethod
    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        root: Path,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute an explicitly configured provider action."""

    @abstractmethod
    def normalize(self, report: dict[str, Any]) -> dict[str, Any]:
        """Normalize provider output into CCR report shape."""
