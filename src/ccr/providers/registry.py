# SPDX-License-Identifier: Apache-2.0
"""Provider registry."""

from __future__ import annotations

from ccr.providers.base import Provider
from ccr.providers.http import HttpProvider
from ccr.providers.pic import PicProvider


def list_providers() -> list[Provider]:
    """Return provider instances."""

    return [PicProvider(), HttpProvider()]


def get_provider(name: str) -> Provider:
    """Return a provider by name."""

    for provider in list_providers():
        if provider.provider_name == name:
            return provider
    raise KeyError(name)
