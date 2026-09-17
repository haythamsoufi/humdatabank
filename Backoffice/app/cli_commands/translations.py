"""CLI for catalog import, provenance recovery, glossary seed, and gold-set sampling."""

from __future__ import annotations

import json
from pathlib import Path

import click
from flask.cli import with_appcontext


def register_translation_commands(app):
    @app.cli.group("translations")
    def translations_cli():
        """Translation catalog, glossary, and evaluation commands."""

    @translations_cli.command("import-catalog")
    @with_appcontext
    def import_catalog():
        from app.services.translation.catalog_service import PROVENANCE_UNKNOWN, import_from_po_files

        counts = import_from_po_files(provenance=PROVENANCE_UNKNOWN)
        click.echo(f"Imported catalog rows: {counts}")

    @translations_cli.command("recover-provenance")
    @with_appcontext
    def recover_provenance():
        from app.services.translation.catalog_service import recover_human_edits_from_audit

        n = recover_human_edits_from_audit()
        click.echo(f"Recovered human-approved rows: {n}")

    @translations_cli.command("seed-glossary")
    @with_appcontext
    def seed_glossary():
        from app.services.translation.glossary_seed import seed_from_indicator_bank

        result = seed_from_indicator_bank()
        click.echo(f"Glossary seed: {result}")

    @translations_cli.command("sample-gold-set")
    @click.option("--per-locale", default=400, type=int)
    @click.option(
        "--output",
        default="Backoffice/tests/fixtures/translation_gold_set.json",
        type=click.Path(),
    )
    @with_appcontext
    def sample_gold_set(per_locale, output):
        from app.services.translation.gold_eval import sample_gold_set as sample

        path = Path(output)
        payload = sample(per_locale=per_locale)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        click.echo(f"Wrote {path} with {payload.get('count')} segments (gold fields empty — commission humans).")

    @translations_cli.command("compile-catalog")
    @click.option("--locale", default=None, help="Rebuild one locale instead of all supported ones.")
    @with_appcontext
    def compile_catalog(locale):
        """Rebuild .po/.mo artifacts from messages.pot and translation_string.

        Run at container boot so the artifacts do not need to survive a
        deployment; the database does.
        """
        from app.services.translation.catalog_service import (
            materialize_catalogs,
            read_catalog_version,
            write_materialized_version,
        )

        counts = materialize_catalogs([locale] if locale else None)
        version = read_catalog_version()
        if version is not None:
            write_materialized_version(version)
        click.echo(
            f"Materialized catalog artifacts from DB (catalog version {version}): {counts}"
        )

    @translations_cli.command("hygiene")
    def hygiene():
        from app.services.translation.catalog_hygiene import hygiene_report

        click.echo(json.dumps(hygiene_report(), indent=2))

    @translations_cli.command("prune-dead-locales")
    def prune_dead():
        from app.services.translation.catalog_hygiene import prune_dead_locales

        removed = prune_dead_locales()
        click.echo(f"Removed dead gettext locales: {removed or 'none present'}")
