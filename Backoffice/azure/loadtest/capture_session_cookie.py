"""Open a browser, let the user complete B2C login, and capture the Flask session cookie.

Usage
-----
  python capture_session_cookie.py
  python capture_session_cookie.py --host https://databank.ifrc.org

Requires playwright (installed separately from load-test engine dependencies)::

  pip install playwright
  playwright install chromium

How it works
------------
1. A visible Chromium window opens and navigates to the target host.
2. The B2C login redirect happens normally — the user completes the flow interactively.
3. Once we are back on the target host domain AND a ``session`` cookie is present,
   the cookie value is printed to **stdout** and the browser closes.
4. All status/progress messages go to **stderr** so the PowerShell caller can capture
   stdout cleanly (the cookie string) while still seeing progress in the terminal.

Exit codes
----------
0  — cookie captured; cookie string on stdout.
1  — failed (playwright missing, browser closed early, timeout, navigation error).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import urlsplit

DEFAULT_HOST = "https://databank-stage.ifrc.org"

# Flask default session cookie name. Add entries here if the app uses a custom name.
SESSION_COOKIE_NAMES = ("session",)

TIMEOUT_SECONDS = 300  # 5 minutes


def _netloc(url: str) -> str:
    """Return the bare hostname (no port, no scheme) from a URL string."""
    raw = urlsplit(url).netloc or url
    return raw.lower().split(":")[0]


def capture(host: str) -> str:
    """Open a browser, wait for B2C login, return the session cookie string."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[error] playwright is not installed.\n"
            "        Install: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    target = _netloc(host)
    print(f"[login] Opening browser → {host}", file=sys.stderr)
    print("[login] Complete the B2C sign-in in the browser that opens.", file=sys.stderr)
    print("[login] Your session cookie will be captured automatically after login.", file=sys.stderr)
    print(
        f"[login] Waiting up to {TIMEOUT_SECONDS // 60} min — "
        "close the browser to cancel.",
        file=sys.stderr,
    )

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        except Exception as exc:
            print(
                f"[error] Cannot launch Chromium: {exc}\n"
                "        Run: playwright install chromium",
                file=sys.stderr,
            )
            sys.exit(1)

        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        try:
            page.goto(host, wait_until="commit", timeout=30_000)
        except Exception as exc:
            print(f"[error] Navigation to {host} failed: {exc}", file=sys.stderr)
            browser.close()
            sys.exit(1)

        deadline = time.monotonic() + TIMEOUT_SECONDS
        session_value: str | None = None

        while time.monotonic() < deadline:
            try:
                current_url = page.url
            except Exception:
                # Browser was closed by the user.
                break

            # Only look for the session cookie once we are back on the target domain.
            # This avoids false positives from cookies set by the B2C tenant domain.
            if target in _netloc(current_url):
                hits = context.cookies(urls=[host])
                for name in SESSION_COOKIE_NAMES:
                    match = next(
                        (c for c in hits if c["name"] == name and c.get("value")), None
                    )
                    if match:
                        raw = f"{name}={match['value']}"
                        # HTTP Cookie headers must be latin-1 safe.
                        # Reject the value and keep waiting if it contains
                        # non-ASCII characters (can happen if the browser
                        # captures a partially-set or corrupted cookie).
                        try:
                            raw.encode("latin-1")
                            session_value = raw
                        except UnicodeEncodeError:
                            print(
                                "[login] Captured cookie contains non-ASCII characters "
                                "— ignoring and waiting for a clean value.",
                                file=sys.stderr,
                            )
                        break

            if session_value:
                print("[login] Session cookie captured — closing browser.", file=sys.stderr)
                break

            time.sleep(0.5)

        try:
            browser.close()
        except Exception:
            pass

    if not session_value:
        print(
            "[error] Browser closed or timed out before login completed.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Only the cookie string goes to stdout so the caller can capture it cleanly.
    print(session_value)
    return session_value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=(os.getenv("LOADTEST_HOST") or DEFAULT_HOST).rstrip("/"),
        help="Target host URL (default: LOADTEST_HOST env var or staging)",
    )
    args = parser.parse_args()
    capture(args.host)


if __name__ == "__main__":
    main()
