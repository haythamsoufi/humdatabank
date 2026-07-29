"""Quick smoke test for IFRC Indicator Bank compat routes."""
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
from _bootstrap import setup_cli_paths

setup_cli_paths(__file__)

from app import create_app

KEY = sys.argv[1] if len(sys.argv) > 1 else ""
PATHS = [
    "list-home",
    "Sector",
    "Subsector",
    "Indicator/tags",
    "CommonWord",
    "Indicator?Limit=2",
    "Indicator/search?filter=volunteer",
    "Excel",
]


def main():
    app = create_app()
    client = app.test_client()
    headers = {"X-Language": "en"}
    if KEY:
        headers["X-API-Key"] = KEY
    failed = False
    with app.app_context():
        for path in PATHS:
            resp = client.get(f"/{path}", headers=headers)
            ok = 200 <= resp.status_code < 300
            print(f"{'OK' if ok else 'FAIL'} {resp.status_code} GET /{path}")
            if not ok:
                failed = True
                print(resp.get_data(as_text=True)[:200])
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
