"""Pytest configuration: make the desktop shell testable on a headless runner."""

from __future__ import annotations

import os

# Qt needs a platform plugin. On a machine without a display the offscreen
# plugin is the only option, and it is enough to build and drive real widgets.
if not os.environ.get("QT_QPA_PLATFORM") and not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
