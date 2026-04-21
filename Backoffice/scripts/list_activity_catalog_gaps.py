#!/usr/bin/env python3
"""
List (method, endpoint) pairs from the Flask url_map that automatic activity logging
could record but are missing from the merged activity endpoint catalog.

Run from Backoffice:
  python scripts/list_activity_catalog_gaps.py

Exit code 0 always; prints nothing when there are no gaps.
"""

from __future__ import annotations

import os
import sys

_BACKOFFICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKOFFICE_ROOT not in sys.path:
    sys.path.insert(0, _BACKOFFICE_ROOT)

os.chdir(_BACKOFFICE_ROOT)
if not os.environ.get("FLASK_APP"):
    os.environ["FLASK_APP"] = "run.py"


def main() -> None:
    from app import create_app
    from app.utils.activity_logging_skip import (
        should_exclude_from_activity_catalog,
        should_skip_activity_path,
    )
    from app.utils.activity_endpoint_overrides import (
        resolve_delete_activity_type,
        resolve_post_activity_type,
    )
    from app.utils.activity_endpoint_catalog import ENDPOINT_ACTIVITY_SPECS
    from app.utils.activity_endpoint_catalog.spec import lookup_activity_endpoint_spec

    app = create_app()
    expected: set[tuple[str, str]] = set()
    with app.app_context():
        for rule in app.url_map.iter_rules():
            ep = rule.endpoint
            if not ep:
                continue
            if should_skip_activity_path(str(rule.rule or "")):
                continue
            if ep == "forms.enter_data":
                continue
            if ep in ("favicon", "test_static_file"):
                continue
            methods = set(rule.methods or ()) - {"HEAD", "OPTIONS", "TRACE"}
            for method in sorted(methods):
                if should_exclude_from_activity_catalog(method, ep):
                    continue
                if ep == "main.dashboard" and method == "POST":
                    continue
                if method == "POST" and resolve_post_activity_type(ep):
                    continue
                if method == "DELETE" and resolve_delete_activity_type(ep):
                    continue
                expected.add((method, ep))

    missing: list[tuple[str, str]] = []
    for key in sorted(expected):
        if lookup_activity_endpoint_spec(key[0], key[1], ENDPOINT_ACTIVITY_SPECS) is None:
            missing.append(key)

    if missing:
        print("Missing catalog entries (method, endpoint):")
        for m, e in missing:
            print(f"  {m} {e}")
    else:
        print("No gaps — merged catalog covers all candidate routes.")


if __name__ == "__main__":
    main()
