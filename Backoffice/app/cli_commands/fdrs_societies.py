import json

import click
from flask import current_app
from flask.cli import with_appcontext


def register_fdrs_society_commands(app):
    """``flask fdrs-societies ...``: the DON-code reference the FDRS public adapter reads."""

    @app.cli.group("fdrs-societies")
    def fdrs_societies_group():
        """Manage the FDRS society reference (DON code, zone, coordinates)."""

    @fdrs_societies_group.command("import")
    @click.option(
        "--file",
        "file_path",
        type=click.Path(exists=True, dir_okay=False),
        help="JSON file holding the legacy GET /api/entities/ns array.",
    )
    @click.option(
        "--from-api",
        is_flag=True,
        help="Download entities/ns from FDRS_DATA_API_BASE (default https://data-api.ifrc.org) with FDRS_DATA_API_KEY.",
    )
    @click.option("--overwrite", is_flag=True, help="Replace values on existing rows (default: fill blanks only).")
    @click.option("--apply/--dry-run", default=False, show_default=True, help="Write changes to the database.")
    @with_appcontext
    def import_societies(file_path, from_api, overwrite, apply):
        """Fill FDRS DON code, zone and profile fields on national_societies."""
        from plugins.fdrs.services.fdrs_society_import import fetch_entities, upsert_societies

        if bool(file_path) == bool(from_api):
            raise click.ClickException("Pass exactly one of --file or --from-api.")
        if from_api:
            entities = fetch_entities(
                current_app.config.get("FDRS_DATA_API_BASE"),
                current_app.config.get("FDRS_DATA_API_KEY"),
            )
        else:
            with open(file_path, encoding="utf-8") as handle:
                entities = json.load(handle)
            if not isinstance(entities, list):
                raise click.ClickException("The file must contain a JSON array.")

        stats = upsert_societies(entities, apply=apply, overwrite=overwrite)
        verb = "Applied" if apply else "Dry run"
        click.echo(
            f"{verb}: created={stats['created']} updated={stats['updated']} "
            f"unchanged={stats['unchanged']} skipped={stats['skipped']} "
            f"without_country={len(stats['unlinked'])}"
        )
        if stats["unlinked"]:
            click.echo("No country.iso3/iso2 match for: " + ", ".join(sorted(stats["unlinked"])))
        if not apply:
            click.echo("Nothing written. Re-run with --apply.")

    @fdrs_societies_group.command("link")
    @with_appcontext
    def link_societies():
        """List National Societies that still have no FDRS DON code."""
        from app.models import NationalSociety

        missing = [
            society.name
            for society in NationalSociety.query.filter(NationalSociety.fdrs_don_code.is_(None))
            .order_by(NationalSociety.name.asc())
            .all()
        ]
        click.echo(f"{len(missing)} national society row(s) have no FDRS DON code.")
        if missing:
            click.echo("Import entities/ns to fill a match. Still without a code: " + ", ".join(missing))
