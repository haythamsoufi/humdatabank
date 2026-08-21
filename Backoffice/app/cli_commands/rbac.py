import click
from flask.cli import with_appcontext


def register_rbac_commands(app) -> None:
    """Register RBAC CLI commands."""

    @app.cli.group("rbac")
    def rbac_group():
        """RBAC utilities (seed permissions, etc.)."""
        pass

    @rbac_group.command("seed")
    @click.option(
        "--wait-timeout",
        type=float,
        default=30.0,
        show_default=True,
        help="Seconds to wait for the RBAC seed advisory lock before giving up.",
    )
    @with_appcontext
    def rbac_seed(wait_timeout):
        """Seed RBAC permissions and baseline role-permission links (idempotent).

        Delegates to the canonical rbac_seed_service so that the CLI, the
        deploy-time entrypoint, and the app-startup auto-seed always apply
        exactly the same permission catalog and role definitions.
        """
        from app.services.organization.rbac_seed_service import (
            RbacSeedLockMode,
            get_missing_baseline_role_codes,
            seed_rbac_permissions_and_roles,
        )
        # Operator-initiated: wait (briefly) rather than instantly losing to a
        # gunicorn worker's background auto-seed and reporting a misleading
        # "0 created, 0 updated" for a catalog that's actually out of sync.
        result = seed_rbac_permissions_and_roles(
            lock_mode=RbacSeedLockMode.WAIT,
            wait_timeout_seconds=wait_timeout,
        )
        if result.get("skipped_due_to_lock"):
            click.echo(
                f"RBAC seed skipped (advisory lock still held by another process "
                f"after waiting {wait_timeout:g}s; re-run to try again)."
            )
            return
        click.echo("RBAC seed complete.")
        click.echo(f"- Permissions: {result.get('created_permissions', 0)} created, {result.get('updated_permissions', 0)} updated")
        click.echo(f"- Roles: {result.get('created_roles', 0)} created, {result.get('updated_roles', 0)} updated")
        click.echo(f"- Role-permission links: {result.get('created_role_permission_links', 0)} created, {result.get('deleted_role_permission_links', 0)} deleted")
        missing = get_missing_baseline_role_codes()
        if missing:
            click.echo(f"WARNING: still missing role(s): {', '.join(missing)}")
