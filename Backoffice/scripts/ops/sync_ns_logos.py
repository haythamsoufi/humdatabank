#!/usr/bin/env python3
"""Download FDRS National Society logos (ISO3 filenames) onto NS records.

Source files live at:
  https://github.com/FDRS-ifrc/general/tree/main/ns_logos
  e.g. https://raw.githubusercontent.com/FDRS-ifrc/general/main/ns_logos/BGD.png

Each ``{ISO3}.png`` is matched to National Societies whose country.iso3 matches,
then stored under system/ns/ and set as ``national_societies.logo_filename``.

Local (from Backoffice/, DATABASE_URL / FLASK_CONFIG as usual):

    python scripts/ops/sync_ns_logos.py --dry-run
    python scripts/ops/sync_ns_logos.py --iso3 BGD
    python scripts/ops/sync_ns_logos.py --overwrite

Production (App Service SSH — container root is /app, not Backoffice/):

    flask sync-ns-logos --dry-run
    flask sync-ns-logos
    flask sync-ns-logos --iso3 BGD --overwrite

Or via the repo azure-webapp tunnel (non-interactive):

    . .\\azure-webapp\\azure_webapp_config.ps1
    $t = Resolve-AzureWebAppEnvironment -Name PROD
    .\\azure-webapp\\azure_webapp_run.ps1 -WebApp $t.WebApp -ResourceGroup $t.ResourceGroup `
        -Port $t.Port -Label $t.Label `
        -Command "cd /app && python scripts/ops/sync_ns_logos.py --dry-run"

Kudu / Azure Portal SSH fallback: copy this file to /tmp if needed; the
bootstrap below still loads the app from /app.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Support upload to /tmp on Azure (bootstrap resolves from /app when __file__ is /tmp/...).
for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

from app import create_app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List ISO3 matches without downloading or writing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace logos that are already stored on National Societies.",
    )
    parser.add_argument(
        "--iso3",
        default=None,
        help="Sync a single country ISO3 code (e.g. BGD).",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from app.services.organization.ns_logo_service import sync_ns_logos_from_github

        result = sync_ns_logos_from_github(
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            iso3=args.iso3,
        )

    action = "would_update" if result.get("dry_run") else "updated"
    print(json.dumps(result, indent=2, default=str))
    print(
        f"{action}={result.get('updated')} github_files={result.get('github_files')} "
        f"countries_with_ns={result.get('countries_with_ns')} "
        f"skipped={result.get('skipped')} no_national_society={result.get('no_national_society')} "
        f"errors={len(result.get('errors') or [])}"
    )
    if result.get("errors"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
