"""CLI commands owned by the FDRS plugin (discovered by app.plugins.cli_discovery)."""
import click
from flask.cli import with_appcontext


def register_cli(app):
    from plugins.fdrs.cli_societies import register_fdrs_society_commands

    register_fdrs_society_commands(app)

    @app.cli.command("fdrs-public-export")
    @with_appcontext
    def fdrs_public_export():
        """Rebuild the daily public FDRS CSV and Excel snapshot now."""
        from plugins.fdrs.services.fdrs_public_export_cache import build_public_export_snapshot

        summary = build_public_export_snapshot()
        click.echo(
            f"Snapshot {summary['snapshot_date']}: {summary['row_count']} rows, "
            f"{len(summary['societies'])} societies."
        )
