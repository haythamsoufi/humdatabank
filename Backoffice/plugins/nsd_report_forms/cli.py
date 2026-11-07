"""CLI commands owned by the NSD report forms plugin (discovered by app.plugins.cli_discovery)."""
import click
from flask.cli import with_appcontext


def register_cli(app):
    @app.cli.command("nsd-migrate-projects")
    @click.option("--dry-run", is_flag=True, help="Simulate AES remaps without writing them.")
    @with_appcontext
    def nsd_migrate_projects(dry_run):
        """Backfill core projects and remap legacy NSD report AES onto shared slots."""
        from plugins.nsd_report_forms.migrate import run_migration

        result = run_migration(dry_run=dry_run)
        click.echo(f"dry_run={result['dry_run']}")
        click.echo(f"projects: {result['projects']}")
        click.echo(f"remap: {result['remap']}")

    @app.cli.command("nsd-migrate-slots")
    @click.option("--dry-run", is_flag=True, help="Count remaps without writing them.")
    @with_appcontext
    def nsd_migrate_slots(dry_run):
        """Repoint shared NSD CBF slots onto per-project cycle assignments."""
        from plugins.nsd_report_forms.migrate_slots import run_slot_migration

        result = run_slot_migration(dry_run=dry_run)
        click.echo(f"dry_run={result['dry_run']}")
        click.echo(f"slots: {result['slots']}")
