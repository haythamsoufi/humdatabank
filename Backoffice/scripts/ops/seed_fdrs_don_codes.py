"""Fill national_societies FDRS fields from the legacy entities/ns list.

The SSH shell does not receive FDRS_DATA_API_KEY. This reads it from the running
gunicorn process, then updates National Society rows. Dry run unless --apply.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, "/app")


def _load_container_env() -> None:
    wanted = {
        "FDRS_DATA_API_KEY",
        "FDRS_DATA_API_BASE",
        "DATABASE_URL",
        "FLASK_APP",
        "FLASK_CONFIG",
        "SECRET_KEY",
    }
    paths = ["/proc/1/environ"]
    for cmdline in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            raw = open(cmdline, "rb").read().replace(b"\0", b" ")
        except OSError:
            continue
        if b"gunicorn" in raw and b"run:app" in raw:
            pid = cmdline.split("/")[2]
            paths.append(f"/proc/{pid}/environ")
            break
    for path in paths:
        try:
            data = open(path, "rb").read().split(b"\0")
        except OSError:
            continue
        for item in data:
            if b"=" not in item:
                continue
            key, value = item.split(b"=", 1)
            name = key.decode()
            if name in wanted and not os.environ.get(name):
                os.environ[name] = value.decode()


def _coverage():
    from app.models import NationalSociety

    total = NationalSociety.query.count()
    with_don = NationalSociety.query.filter(NationalSociety.fdrs_don_code.isnot(None)).count()
    return total, with_don


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--rebuild-export",
        action="store_true",
        help="After --apply, rebuild the public CSV/Excel snapshot.",
    )
    args = parser.parse_args()
    _load_container_env()
    if not os.environ.get("FDRS_DATA_API_KEY"):
        print("FDRS_DATA_API_KEY is not in the container environment.", file=sys.stderr)
        return 1
    print("FDRS_DATA_API_KEY present; base =", os.environ.get("FDRS_DATA_API_BASE") or "https://data-api.ifrc.org")

    from app import create_app
    from plugins.fdrs.services.fdrs_society_import import fetch_entities, upsert_societies

    app = create_app(os.environ.get("FLASK_CONFIG"))
    with app.app_context():
        before_total, before_don = _coverage()
        print(f"before: national_societies={before_total} with_don_code={before_don}")
        entities = fetch_entities(
            app.config.get("FDRS_DATA_API_BASE"),
            app.config.get("FDRS_DATA_API_KEY"),
        )
        stats = upsert_societies(entities, apply=args.apply)
        after_total, after_don = _coverage()
        print(f"after: national_societies={after_total} with_don_code={after_don}")
        if args.apply and args.rebuild_export:
            from plugins.fdrs.services.fdrs_public_export_cache import build_public_export_snapshot

            summary = build_public_export_snapshot()
            print(
                f"export snapshot {summary.get('snapshot_date')}: "
                f"rows={summary.get('row_count')} societies={len(summary.get('societies') or [])}"
            )
    print(
        f"{'Applied' if args.apply else 'Dry run'}: created={stats['created']} "
        f"updated={stats['updated']} unchanged={stats['unchanged']} "
        f"skipped={stats['skipped']} without_country={len(stats['unlinked'])}"
    )
    if stats["unlinked"]:
        print("No country match for: " + ", ".join(sorted(stats["unlinked"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
