"""Chromium launch options for containerized builds."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pb_figures.render_html import chromium_launch_options  # noqa: E402


class TestChromiumLaunchOptions:
    def test_linux_includes_container_sandbox_flags(self) -> None:
        with patch.object(sys, "platform", "linux"):
            options = chromium_launch_options()
        assert options["headless"] is True
        assert "--no-sandbox" in options["args"]
        assert "--disable-dev-shm-usage" in options["args"]

    def test_windows_uses_default_headless_only(self) -> None:
        with patch.object(sys, "platform", "win32"):
            options = chromium_launch_options()
        assert options == {"headless": True}
