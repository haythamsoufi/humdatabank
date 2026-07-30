"""Render publication-quality dashboards via HTML/SVG + Playwright."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .font_faces import inject_chart_fonts
from .payload import build_payload
from .line_chart import inject_line_chart_js

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Playwright

TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"
_PLACEHOLDER = "__DASHBOARD_JSON__"


def chromium_launch_options() -> dict[str, Any]:
    """Headless Chromium options for Linux containers (Azure App Service, Docker).

    Without ``--no-sandbox``, ``chromium.launch()`` typically fails immediately on
    Azure Linux because the process cannot create a new sandbox namespace.
    """
    options: dict[str, Any] = {"headless": True}
    if sys.platform == "win32":
        return options
    options["args"] = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    return options


class PlaywrightScreenshotSession:
    """Reuse one Chromium instance for many HTML-to-PNG screenshots."""

    def __init__(self, scale: float = 2.0) -> None:
        self.scale = scale
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def __enter__(self) -> PlaywrightScreenshotSession:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(**chromium_launch_options())
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    @property
    def browser(self) -> Browser:
        if self._browser is None:
            raise RuntimeError("PlaywrightScreenshotSession is not active")
        return self._browser

    def screenshot_html(
        self,
        html: str,
        selector: str,
        output_path: Path,
        *,
        width: int,
        height: int,
    ) -> Path:
        if self._browser is None:
            raise RuntimeError("PlaywrightScreenshotSession is not active")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        page = self._browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=self.scale,
        )
        try:
            page.set_content(html, wait_until="load")
            page.evaluate("async () => { await document.fonts.ready; }")
            page.wait_for_function("() => document.body.getAttribute('data-ready') === 'true'")
            page.locator(selector).screenshot(path=str(output_path), type="png")
        finally:
            page.close()
        return output_path


def _build_html(payload: dict) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if _PLACEHOLDER not in template:
        raise ValueError(f"Template missing placeholder {_PLACEHOLDER}")
    data_json = json.dumps(payload, ensure_ascii=False)
    html = template.replace(_PLACEHOLDER, data_json)
    html = inject_chart_fonts(html)
    return inject_line_chart_js(html)


def _dashboard_height(payload: dict) -> int:
    """Estimate pixel height for viewport sizing."""
    base = 130  # title + headers + footnote
    for item in payload["cumulative"]:
        if item.get("unavailable"):
            base += 96
        elif item.get("ns_table_mode") in {"implementing_count", "ns_unit"}:
            base += 130
        elif item.get("show_ns_breakdown") is False:
            base += 119
        else:
            base += 155
    for pair in payload.get("donut_pairs", []):
        base += 90
    for _item in payload.get("donuts", []):
        base += 90
    return max(base, 400)


def render_dashboard_html(
    model,
    section: str,
    *,
    language: str = "English",
    output_path: Path | None = None,
    scale: float = 2.0,
    session: PlaywrightScreenshotSession | None = None,
    mapping=None,
) -> Path:
    """Render dashboard to PNG using HTML/SVG layout engine."""
    payload = build_payload(model, section, language, mapping=mapping)
    html = _build_html(payload)
    width = int(payload.get("width", 827))
    height = _dashboard_height(payload)

    if output_path is None:
        raise ValueError("output_path is required for HTML renderer")

    screenshot = (
        session.screenshot_html(html, "#dashboard", output_path, width=width, height=height)
        if session is not None
        else _screenshot_once(html, "#dashboard", output_path, width=width, height=height, scale=scale)
    )
    return screenshot


def _screenshot_once(
    html: str,
    selector: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    scale: float,
) -> Path:
    with PlaywrightScreenshotSession(scale=scale) as session:
        return session.screenshot_html(html, selector, output_path, width=width, height=height)


def render_dashboard_svg(
    model,
    section: str,
    *,
    language: str = "English",
    output_path: Path | None = None,
) -> Path:
    """Optional: save standalone HTML preview alongside PNG."""
    payload = build_payload(model, section, language)
    html = _build_html(payload)
    if output_path is None:
        raise ValueError("output_path is required")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
