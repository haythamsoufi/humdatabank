import click
from flask.cli import with_appcontext


def register_rbac_commands(app) -> None:
    """Register RBAC CLI commands."""

    @app.cli.group("rbac")
    def rbac_group():
        """RBAC utilities (seed permissions, etc.)."""
        pass

    @rbac_group.command("seed")
    @with_appcontext
    def rbac_seed():
        """Seed RBAC permissions and baseline role-permission links (idempotent).

        Delegates to the canonical rbac_seed_service so that the CLI and the
        app-startup auto-seed always apply exactly the same permission catalog
        and role definitions.
        """
        from app.services.rbac_seed_service import seed_rbac_permissions_and_roles
        result = seed_rbac_permissions_and_roles(use_advisory_lock=False)
        if result.get("skipped_due_to_lock"):
            click.echo("RBAC seed skipped (advisory lock held by another process).")
            return
        click.echo("RBAC seed complete.")
        click.echo(f"- Permissions: {result.get('created_permissions', 0)} created, {result.get('updated_permissions', 0)} updated")
        click.echo(f"- Roles: {result.get('created_roles', 0)} created, {result.get('updated_roles', 0)} updated")
        click.echo(f"- Role-permission links: {result.get('created_role_permission_links', 0)} created, {result.get('deleted_role_permission_links', 0)} deleted")
