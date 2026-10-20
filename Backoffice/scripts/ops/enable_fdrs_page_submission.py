#!/usr/bin/env python3
"""Turn on per-page save and submit for every FDRS assignment (template 21).

This is a data update, not a schema migration. ``assigned_form.enable_page_submission``
already exists. Assignments that already have the flag are left unchanged, including
their ``assignment_page_status`` rows.

Dry run (default) prints a JSON backup of current flags and writes nothing:

    python scripts/ops/enable_fdrs_page_submission.py

Write on the database this process is connected to:

    python scripts/ops/enable_fdrs_page_submission.py --apply

Turning the flag on seeds one page-status row per participating page, copied from
each entity's current assignment status. That is the same path as the assignment
editor. It is not the FDRS section workflow (KPI_NSGS / KPI_NSFP / KPI_NSR).
Those KPIs still roll up to the whole assignment until the page-status import
described in docs/runbooks/fdrs-page-submission.md is built.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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

from app import create_app
from app.extensions import db
from app.models.assignments import AssignedForm
from app.services.assignments.page_submission_service import (
    apply_page_submission_mode_change,
    participating_page_ids,
    load_published_sections,
)
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID


def _assignment_snapshot(assignment: AssignedForm) -> dict:
    return {
        "id": int(assignment.id),
        "period_name": assignment.period_name,
        "is_active": bool(assignment.is_active),
        "enable_page_submission": bool(assignment.enable_page_submission),
        "entity_count": int(assignment.entity_statuses.count()),
    }


def _page_count(assignment: AssignedForm) -> int:
    return len(participating_page_ids(load_published_sections(assignment)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write enable_page_submission and seed missing page-status rows.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        assignments = (
            AssignedForm.query.filter_by(template_id=FDRS_TEMPLATE_ID)
            .order_by(AssignedForm.period_name, AssignedForm.id)
            .all()
        )
        snapshot = [_assignment_snapshot(row) for row in assignments]
        pending = [row for row in assignments if not row.enable_page_submission]
        already = [row for row in assignments if row.enable_page_submission]
        pages = _page_count(pending[0]) if pending else (_page_count(already[0]) if already else 0)

        report = {
            "template_id": FDRS_TEMPLATE_ID,
            "apply": bool(args.apply),
            "participating_pages": pages,
            "backup": snapshot,
            "already_enabled": [row["period_name"] for row in snapshot if row["enable_page_submission"]],
            "to_enable": [row["period_name"] for row in snapshot if not row["enable_page_submission"]],
            "entities_to_seed": sum(row["entity_count"] for row in snapshot if not row["enable_page_submission"]),
        }
        print(json.dumps(report, indent=2))

        if not args.apply:
            print("Dry run only. Re-run with --apply to write.")
            return 0

        summaries = []
        for assignment in pending:
            assignment.enable_page_submission = True
            summary = apply_page_submission_mode_change(assignment, True, None)
            summaries.append(
                {
                    "id": int(assignment.id),
                    "period_name": assignment.period_name,
                    **summary,
                }
            )
        db.session.commit()

        after = (
            AssignedForm.query.filter_by(template_id=FDRS_TEMPLATE_ID)
            .order_by(AssignedForm.period_name, AssignedForm.id)
            .all()
        )
        still_off = [row.period_name for row in after if not row.enable_page_submission]
        print(
            json.dumps(
                {
                    "applied": summaries,
                    "still_off": still_off,
                },
                indent=2,
            )
        )
        return 1 if still_off else 0


if __name__ == "__main__":
    raise SystemExit(main())
