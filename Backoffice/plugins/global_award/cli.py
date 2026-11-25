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

    @app.cli.command("global-award-sectoral-import")
    @click.argument("path", required=False, type=click.Path(exists=True, dir_okay=False))
    @click.option("--dry-run", is_flag=True, help="Parse and match without saving.")
    @with_appcontext
    def global_award_sectoral_import(path, dry_run):
        """Import Sectoral Interventions: sectors, PMER focal points, project managers and users.

        PATH defaults to the newest sectoral workbook at the repository root. Run the logframe
        import first so every country has a project.
        """
        from plugins.global_award.importer.files import SLOT_SECTORAL, repo_workbooks
        from plugins.global_award.importer.sectoral_apply import import_sectoral

        source = path
        if source is None:
            found = repo_workbooks(SLOT_SECTORAL)
            if not found:
                raise click.ClickException("No Sectoral Interventions workbook at the repository root. Pass a PATH.")
            source = found[0]
            click.echo(f"Using {source.name}")
        report = import_sectoral(source, dry_run=dry_run)
        users = report["users"]
        click.echo(
            f"dry_run={report['dry_run']} countries={report['countries']} "
            f"projects_updated={report['projects_updated']} "
            f"users_created={len(users['created'])} users_existing={len(users['existing'])} "
            f"group={users['group_name']}{' (created)' if users['group_created'] else ''} "
            f"country_access_added={users['country_access_added']}"
        )
        for label, key in (
            ("PMER focal point from the region office", "pmer_regional"),
            ("project manager from the region office", "managers_regional"),
        ):
            if report[key]:
                click.echo(f"{label}: " + ", ".join(report[key]))
        for warning in report["warnings"]:
            click.echo(f"warning: {warning}")
        for row in users["created"]:
            click.echo(f"  new user {row['email']} ({row['name']}) {', '.join(row['roles'])}")
        # Last, so it is not lost above the user list.
        if users["existing"]:
            click.echo("")
            click.echo(f"{len(users['existing'])} users already existed and were not created again:")
            for row in users["existing"]:
                notes = []
                notes.append("added to the group" if row["joined_group"] else "already in the group")
                if row["countries_added"]:
                    notes.append(f"{row['countries_added']} countries added")
                if not row["active"]:
                    notes.append("INACTIVE account")
                click.echo(f"  {row['email']} ({row['name']}): {', '.join(notes)}")
        else:
            click.echo("No user existed before this import.")
