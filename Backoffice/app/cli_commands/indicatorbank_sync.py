import logging

import click
from flask.cli import with_appcontext

logger = logging.getLogger(__name__)
from contextlib import suppress, nullcontext


def register_indicatorbank_commands(app):
    """Register temporary Indicator Bank sync commands."""

    @app.cli.group("indicatorbank")
    def indicatorbank_group():
        """Temporary tools to sync Indicator Bank from external platform."""

    @indicatorbank_group.command("sync-remote")
    @click.option(
        "--api-url",
        default="https://ifrc-indicatorbank.azurewebsites.net/api/indicator",
        show_default=True,
        help="Remote IFRC Indicator Bank API endpoint returning JSON array.",
    )
    @click.option(
        "--api-key",
        envvar="IFRC_INDICATORBANK_API_KEY",
        required=False,
        help="Remote API key. Prefer setting env IFRC_INDICATORBANK_API_KEY.",
    )
    @click.option(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for number of indicators to process (useful for testing).",
    )
    @click.option(
        "--apply/--dry-run",
        default=False,
        show_default=True,
        help="Apply changes to DB (default is dry-run).",
    )
    @click.option(
        "--overwrite-comments",
        is_flag=True,
        default=False,
        help="Deprecated. Comments are always set to remote comments only.",
    )
    @with_appcontext
    def sync_indicator_bank_remote(api_url, api_key, limit, apply, overwrite_comments):
        """Sync indicators from the current production Indicator Bank platform.

        Matches local records by:
        1) Primary key: local `IndicatorBank.id` == remote `indicatorId`
        2) Fallback: exact `IndicatorBank.name` match (remote `title`)

        Creates/updates:
        - `Sector` and `SubSector` records by name (and links subsectors to sector when possible)
        - `IndicatorBank` records with sector/subsector JSON fields storing local IDs.
        """
        from app.services.indicatorbank_remote_sync_service import sync_remote_indicator_bank

        if not api_key:
            raise click.ClickException(
                "Missing API key. Provide `--api-key` or set env var `IFRC_INDICATORBANK_API_KEY`.\n"
                "PowerShell: `$env:IFRC_INDICATORBANK_API_KEY=\"<key>\"`\n"
                "cmd.exe: `set IFRC_INDICATORBANK_API_KEY=<key>`"
            )

        # NOTE: We intentionally do NOT store any sync marker in comments.
        # The local primary key is remote `indicatorId`, so ID matching is sufficient.

        def get_text_list(items):
            out = []
            if not items:
                return out
            for it in items:
                with suppress(Exception):
                    txt = it.get("text") if isinstance(it, dict) else None
                    if txt and str(txt).strip():
                        out.append(str(txt).strip())
            seen = set()
            deduped = []
            for x in out:
                if x not in seen:
                    seen.add(x)
                    deduped.append(x)
            return deduped

        def is_emergency(item: dict) -> bool:
            try:
                val = (item.get("emergency") or "").strip().lower()
                if val == "emergency":
                    return True
            except Exception as e:
                logger.debug("is_emergency fallback: %s", e)
            tags = get_text_list(item.get("tags"))
            return any(t.strip().lower() == "emergency" for t in tags)

        def normalize_type(type_of_measurement: str | None) -> str:
            t = (type_of_measurement or "").strip()
            if not t:
                return "Number"
            allowed = {"Number", "Percentage", "Text", "YesNo", "Date"}
            if t in allowed:
                return t
            tl = t.lower()
            if tl in ("number", "numeric", "count"):
                return "Number"
            if tl in ("percentage", "percent", "%"):
                return "Percentage"
            if tl in ("text", "string"):
                return "Text"
            if tl in ("yesno", "yes/no", "boolean", "bool"):
                return "YesNo"
            if tl in ("date", "datetime"):
                return "Date"
            return "Number"

        click.echo(f"Fetching remote indicators from: {api_url}")
        stats = sync_remote_indicator_bank(
            api_url=api_url,
            api_key=api_key,
            limit=limit,
            apply=bool(apply),
        )

        click.echo("\nSync summary:")
        click.echo(f"- sectors created: {stats['sectors_created']}")
        click.echo(f"- subsectors created: {stats['subsectors_created']}")
        click.echo(f"- indicators created: {stats['indicators_created']}")
        click.echo(f"- indicators updated: {stats['indicators_updated']}")
        if "name_translations_cleared" in stats or "definition_translations_cleared" in stats:
            click.echo(f"- name translations cleared: {stats.get('name_translations_cleared', 0)}")
            click.echo(f"- definition translations cleared: {stats.get('definition_translations_cleared', 0)}")
        if "name_id_mismatches" in stats:
            click.echo(f"- name/id mismatches merged by name: {stats.get('name_id_mismatches', 0)}")
        click.echo(f"- skipped: {stats['skipped']}")
        click.echo("\nApplied changes to DB." if apply else "\nDry-run only (no DB changes applied). Use --apply to write.")
