"""CLI: flask emergency-operations-sync"""

from __future__ import annotations

import click
from flask.cli import with_appcontext


def register_cli(app):
    @app.cli.command("emergency-operations-sync")
    @click.option(
        "--include-closed",
        is_flag=True,
        expose_value=False,
        help="Accepted for compatibility. Closed operations are always included.",
    )
    @with_appcontext
    def emergency_operations_monitoring_sync():
        """Pull every approved DREF stage from the public GO dref3 API."""
        from plugins.emergency_operations_monitoring.services.go_sync import GoSyncBusy, sync_from_go

        try:
            summary = sync_from_go()
        except GoSyncBusy:
            click.echo("A GO sync is already running.")
            return
        click.echo(
            f"created={summary['created']} updated={summary['updated']} appeals={summary['appeals']}"
        )

    @app.cli.command("emergency-operations-backfill-projects")
    @with_appcontext
    def emergency_operations_monitoring_backfill_projects():
        """Create a project for every synced operation, and cycles where the plan is validated."""
        from plugins.emergency_operations_monitoring.services.project_link import backfill_projects

        summary = backfill_projects()
        click.echo(
            f"projects={summary['projects']} cycles={summary['cycles']} skipped={summary['skipped']}"
        )
