# SPDX-License-Identifier: Apache-2.0
"""Small HTML renderer for workbench reports."""

from __future__ import annotations

from html import escape
from typing import Any

from ccr.workbench.markdown import render_markdown_report


def render_html_report(report: dict[str, Any]) -> str:
    """Render a simple preformatted HTML report."""

    body = escape(render_markdown_report(report))
    return f'<!doctype html><meta charset="utf-8"><pre>{body}</pre>\n'
