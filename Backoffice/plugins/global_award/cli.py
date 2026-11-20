"""CLI: flask global-award-import"""

from __future__ import annotations

import click
from flask.cli import with_appcontext


def register_cli(app):
    @app.cli.command("global-award-import")
    @click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False))
    @click.option("--dry-run", is_flag=True, help="Parse and match without saving.")
    @with_appcontext
    def global_award_import(path, dry_run):
        """Import the MARC logframe into the Global Award template and projects.

        PATH defaults to the newest logframe workbook at the repository root.
        """
        from plugins.global_award.importer.apply import import_logframe
        from plugins.global_award.importer.files import repo_workbooks

        source = path
        if source is None:
            found = repo_workbooks()
            if not found:
                raise click.ClickException("No logframe workbook at the repository root. Pass a PATH.")
            source = found[0]
            click.echo(f"Using {source.name}")
        report = import_logframe(source, dry_run=dry_run)
        click.echo(
            f"dry_run={report['dry_run']} template_id={report['template_id']} "
            f"sections={report['sections']} linked={report['linked']} "
            f"questions={report['questions']} projects={report['projects_upserted']} "
            f"cycles={report.get('cycles_per_project') or 0} "
            f"({report.get('award_start') or 'no start'} to {report.get('award_end') or 'no end'})"
        )
        if report["unmatched_countries"]:
            click.echo("unmatched countries: " + ", ".join(report["unmatched_countries"]))
        for row in report["links"]:
            note = f" — {row['note']}" if row.get("note") else ""
            click.echo(f"  bank {row['method']} #{row['bank_id']} {row['code']}: {row['label'][:80]}{note}")
        for row in report["created_questions"]:
            note = f" — {row['note']}" if row.get("note") else ""
            click.echo(f"  question {row['question_type']} {row['code']}: {row['label'][:80]}{note}")
        for warning in report["warnings"]:
            click.echo(f"warning: {warning}")
