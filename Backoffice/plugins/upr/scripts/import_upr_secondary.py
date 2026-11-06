"""CLI for UPR secondary snapshot imports.

Examples:
  python -m plugins.upr.scripts.import_upr_secondary population
  python -m plugins.upr.scripts.import_upr_secondary poverty
  python -m plugins.upr.scripts.import_upr_secondary income-groups
  python -m plugins.upr.scripts.import_upr_secondary hdi
  python -m plugins.upr.scripts.import_upr_secondary inform-risk
  python -m plugins.upr.scripts.import_upr_secondary inform-severity
  python -m plugins.upr.scripts.import_upr_secondary inform-climate
  python -m plugins.upr.scripts.import_upr_secondary income-groups path/to/file.xlsx
  python -m plugins.upr.scripts.import_upr_secondary hdi path/to/file.xlsx
  python -m plugins.upr.scripts.import_upr_secondary inform-risk path/to/file.xlsx
  python -m plugins.upr.scripts.import_upr_secondary multilateral P27 path/to/file.csv
  python -m plugins.upr.scripts.import_upr_secondary eas-sprm-ops P27 path/to/file.csv --year 2027
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import UPR secondary reference data")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("population", help="Refresh World Bank population (latest year)")
    sub.add_parser("poverty", help="Refresh World Bank poverty (latest year)")

    income = sub.add_parser("income-groups", help="Refresh World Bank income groups (or import a local file)")
    income.add_argument("file", type=Path, nargs="?", default=None)

    hdi = sub.add_parser("hdi", help="Refresh UNDP HDR HDI (or import a local file)")
    hdi.add_argument("file", type=Path, nargs="?", default=None)

    for name, help_text in (
        ("inform-risk", "Fetch latest INFORM Risk Excel (or import a local file)"),
        ("inform-severity", "Fetch latest INFORM Severity Excel (or import a local file)"),
        ("inform-climate", "Fetch INFORM Climate Change Excel (or import a local file)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("file", type=Path, nargs="?", default=None)
        if name == "inform-risk":
            p.add_argument("--edition", default=None)

    multi = sub.add_parser("multilateral", help="Import multilateral support for a round")
    multi.add_argument("round")
    multi.add_argument("file", type=Path)
    multi.add_argument("--year", type=int, default=None)

    eas = sub.add_parser("eas-sprm-ops", help="Import EAs SPRM/OPS for a round")
    eas.add_argument("round")
    eas.add_argument("file", type=Path)
    eas.add_argument("--year", type=int, default=None)

    args = parser.parse_args(argv)

    from app import create_app

    app = create_app()
    with app.app_context():
        from plugins.upr.secondary import imports as imp

        if args.cmd == "population":
            result = imp.refresh_population()
        elif args.cmd == "poverty":
            result = imp.refresh_poverty()
        elif args.cmd == "income-groups":
            if args.file:
                result = imp.import_income_groups(args.file.name, args.file.read_bytes())
            else:
                result = imp.refresh_income_groups()
        elif args.cmd == "hdi":
            if args.file:
                result = imp.import_hdi(args.file.name, args.file.read_bytes())
            else:
                result = imp.refresh_hdi()
        elif args.cmd == "inform-risk":
            if args.file:
                result = imp.import_inform_risk(args.file.name, args.file.read_bytes(), edition=args.edition)
            else:
                result = imp.refresh_inform_risk()
        elif args.cmd == "inform-severity":
            if args.file:
                result = imp.import_inform_severity(args.file.name, args.file.read_bytes())
            else:
                result = imp.refresh_inform_severity()
        elif args.cmd == "inform-climate":
            if args.file:
                result = imp.import_inform_climate(args.file.name, args.file.read_bytes())
            else:
                result = imp.refresh_inform_climate()
        elif args.cmd == "multilateral":
            result = imp.import_multilateral(args.round, args.file.name, args.file.read_bytes(), year=args.year)
        elif args.cmd == "eas-sprm-ops":
            result = imp.import_eas_sprm_ops(args.round, args.file.name, args.file.read_bytes(), year=args.year)
        else:
            parser.error(f"unknown command {args.cmd}")
            return 2
        print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
