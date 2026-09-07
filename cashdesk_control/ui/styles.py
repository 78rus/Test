"""Backwards-compatible alias for the theme module.

``APP_QSS`` used to be a single hard-coded dark stylesheet. The application now
ships three themes, so the constant resolves to the default one and everything
new should use :func:`cashdesk_control.ui.themes.qss_for`.
"""

from __future__ import annotations

from .themes import APP_QSS, DARK, GRAY, LIGHT, THEMES, Theme, build_qss, get_theme, qss_for

__all__ = ["APP_QSS", "DARK", "GRAY", "LIGHT", "THEMES", "Theme", "build_qss", "get_theme", "qss_for"]
