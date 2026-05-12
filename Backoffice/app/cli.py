import click
import secrets
from flask.cli import with_appcontext
from .extensions import db
from app.utils.transactions import atomic
from app.utils.sequence_utils import get_tables_with_id_column, reset_table_sequence


def reset_table_sequence_verbose(
    table_name: str, schema: str = "public", verbose: bool = False
) -> tuple[bool, str]:
    """Wrapper that logs errors when verbose=True (for CLI)."""
    ok, reason = reset_table_sequence(table_name, schema=schema)
    if not ok and verbose:
        click.echo(f"  [{table_name}] {reason}", err=True)
    return (ok, reason)


def reset_form_data_sequence_helper() -> bool:
    """Convenience helper to reset form_data sequence."""
    ok, _reason = reset_table_sequence("form_data")
    return ok

def register_commands(app):
    """Register CLI commands with the app."""
    # Keep CLI implementations in small modules to avoid an oversized file
    from app.cli_commands.indicatorbank_sync import register_indicatorbank_commands
    register_indicatorbank_commands(app)

    # AI regression testing
    from app.cli_commands.ai_regression import ai_regression_cli
    app.cli.add_command(ai_regression_cli)

    @app.cli.command('sync-indicator-embeddings')
    @click.option('--batch-size', type=int, default=100, help='Batch size for embedding API calls')
    @with_appcontext
    def sync_indicator_embeddings(batch_size):
        """Build or refresh vector embeddings for Indicator Bank (semantic indicator resolution). Run once after migration, then when indicators change."""
        from app.services.indicator_resolution_service import IndicatorResolutionService
        try:
            svc = IndicatorResolutionService()
            count, cost = svc.sync_all(batch_size=batch_size)
            click.echo(f'Synced {count} indicator embeddings (cost ${cost:.4f} USD).')
        except Exception as e:
            click.echo(f'Error: {e}', err=True)
            raise

    # NOTE: RBAC seeding commands are defined below under `flask rbac ...`.
    # Do not register a second RBAC CLI group from another module, as Click
    # would otherwise create conflicting commands/groups (non-deterministic).

    @app.cli.command('generate-api-key')
    @click.argument('email')
    @with_appcontext
    def generate_api_key_command(email):
        """Generate an API key for a user."""
        from .models import User

        user = User.query.filter_by(email=email).first()
        if not user:
            click.echo(f'User with email {email} not found.')
            return

        # Generate a secure API key
        api_key = secrets.token_hex(32)
        user.api_key = api_key
        with atomic(remove_session=True):
            db.session.add(user)

        click.echo(f'API key generated for {email}: {api_key}')

    @app.cli.command('reset-activity-sequence')
    @with_appcontext
    def reset_activity_sequence():
        """Reset the user_activity_log id sequence to max(id).

        SECURITY: Uses hardcoded table name, no user input - safe from injection.
        """
        try:
            ok, reason = reset_table_sequence_verbose("user_activity_log", schema="public", verbose=True)
            if ok:
                click.echo("Reset sequence for user_activity_log successfully.")
            else:
                click.echo(f"Skipped user_activity_log ({reason})", err=False)
        except Exception as exc:
            click.echo(f'Failed to reset sequence: {exc}', err=True)
            raise

    @app.cli.command('reset-form-data-sequence')
    @with_appcontext
    def reset_form_data_sequence():
        """Reset the form_data id sequence to max(id)."""
        try:
            ok, reason = reset_table_sequence_verbose("form_data", schema="public", verbose=True)
            if ok:
                click.echo('Reset sequence for form_data successfully.')
            else:
                click.echo(f"Skipped form_data ({reason})", err=False)
        except Exception as exc:
            click.echo(f'Failed to reset sequence: {exc}', err=True)
            raise

    @app.cli.command('reset-all-sequences')
    @click.option('--schema', default='public', help='PostgreSQL schema (default: public)')
    @click.option('--list-tables', is_flag=True, help='List tables in schema that have an id column (diagnostic)')
    @click.option('--verbose', '-v', is_flag=True, help='Show error for each skipped table')
    @with_appcontext
    def reset_all_sequences(schema, list_tables, verbose):
        """Reset all table sequences to their max(id) values.

        Scans all tables in the schema that have an id column and resets
        any serial/identity sequence to MAX(id). Use after loading a DB dump.
        """
        # Optional: list tables in schema that have id column (diagnostic)
        if list_tables:
            try:
                names = get_tables_with_id_column(schema=schema)
                click.echo(f"Tables in schema '{schema}' with 'id' column ({len(names)}):")
                for n in names:
                    click.echo(f"  {n}")
                if not names:
                    click.echo("  (none)")
                return
            except Exception as e:
                click.echo(f"Could not list tables: {e}", err=True)
                return

        tables = get_tables_with_id_column(schema=schema)

        success_count = 0
        for table in tables:
            try:
                ok, reason = reset_table_sequence_verbose(table, schema=schema, verbose=verbose)
                if ok:
                    click.echo(f"[OK] Reset sequence for {schema}.{table}")
                    success_count += 1
                else:
                    click.echo(f"[SKIP] {schema}.{table} ({reason})")
            except Exception as exc:
                click.echo(f"[FAIL] {schema}.{table}: {exc}", err=True)
        click.echo(f'\nReset sequences for {success_count} tables successfully.')
        if success_count == 0:
            click.echo(
                '\nNo tables were reset. Run:  flask reset-all-sequences --list-tables  '
                'to see which tables exist in this schema.',
                err=True
            )

    # ========================================================================
    # Workflow Documentation Commands
    # ========================================================================

    @app.cli.group('workflows')
    def workflows_group():
        """Manage workflow documentation for the chatbot."""
        pass

    @workflows_group.command('sync')
    @with_appcontext
    def sync_workflows():
        """Sync workflow documentation to the vector store.

        This indexes all workflow markdown files from docs/workflows/
        for semantic search by the chatbot.

        Example:
            flask workflows sync
        """
        try:
            from app.services.workflow_docs_service import WorkflowDocsService

            click.echo('Loading workflow documentation...')
            service = WorkflowDocsService()
            service.reload()

            workflows = service.get_all_workflows()
            click.echo(f'Found {len(workflows)} workflow documents')

            if not workflows:
                click.echo('No workflows found in docs/workflows/')
                return

            click.echo('Syncing to vector store...')
            results = service.sync_to_vector_store()

            click.echo(f'\n✓ Synced: {results.get("synced", 0)} new workflows')
            click.echo(f'✓ Updated: {results.get("updated", 0)} existing workflows')

            if results.get('errors'):
                click.echo(f'\n⚠ Errors ({len(results["errors"])}):')
                for error in results['errors']:
                    click.echo(f'  - {error}')

            if results.get('total_cost', 0) > 0:
                click.echo(f'\nEmbedding cost: ${results["total_cost"]:.4f}')

            click.echo('\nWorkflow sync complete!')

        except ImportError as e:
            click.echo(f'Error: Could not import WorkflowDocsService: {e}', err=True)
            raise
        except Exception as e:
            click.echo(f'Error syncing workflows: {e}', err=True)
            raise

    @workflows_group.command('list')
    @with_appcontext
    def list_workflows():
        """List all available workflow documents.

        Example:
            flask workflows list
        """
        try:
            from app.services.workflow_docs_service import WorkflowDocsService

            service = WorkflowDocsService()
            workflows = service.get_all_workflows()

            if not workflows:
                click.echo('No workflows found in docs/workflows/')
                return

            click.echo(f'\nFound {len(workflows)} workflow documents:\n')

            # Group by category
            by_category = {}
            for w in workflows:
                cat = w.category or 'uncategorized'
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(w)

            for category, wfs in sorted(by_category.items()):
                click.echo(f'{category.upper()}:')
                for w in wfs:
                    roles = ', '.join(w.roles)
                    steps = len(w.steps)
                    click.echo(f'  - {w.id}: {w.title} ({steps} steps) [{roles}]')
                click.echo()

        except Exception as e:
            click.echo(f'Error listing workflows: {e}', err=True)
            raise

    @workflows_group.command('show')
    @click.argument('workflow_id')
    @with_appcontext
    def show_workflow(workflow_id):
        """Show details of a specific workflow.

        Example:
            flask workflows show add-user
        """
        try:
            from app.services.workflow_docs_service import WorkflowDocsService

            service = WorkflowDocsService()
            workflow = service.get_workflow_by_id(workflow_id)

            if not workflow:
                click.echo(f'Workflow "{workflow_id}" not found')
                return

            click.echo(f'\n{workflow.title}')
            click.echo('=' * len(workflow.title))
            click.echo(f'\nID: {workflow.id}')
            click.echo(f'Category: {workflow.category}')
            click.echo(f'Roles: {", ".join(workflow.roles)}')
            click.echo(f'Pages: {", ".join(workflow.pages)}')
            click.echo(f'\nDescription: {workflow.description}')

            if workflow.prerequisites:
                click.echo('\nPrerequisites:')
                for prereq in workflow.prerequisites:
                    click.echo(f'  - {prereq}')

            click.echo(f'\nSteps ({len(workflow.steps)}):')
            for step in workflow.steps:
                click.echo(f'  {step.step_number}. {step.title}')
                click.echo(f'     Page: {step.page}')
                click.echo(f'     Selector: {step.selector}')

            if workflow.tips:
                click.echo('\nTips:')
                for tip in workflow.tips:
                    click.echo(f'  - {tip}')

        except Exception as e:
            click.echo(f'Error showing workflow: {e}', err=True)
            raise

    # ========================================================================
    # RBAC Commands
    # ========================================================================

    @app.cli.group('rbac')
    def rbac_group():
        """Manage RBAC permissions and roles."""
        pass

    @rbac_group.command('seed')
    @with_appcontext
    def seed_rbac():
        """Seed RBAC permissions and baseline roles (idempotent)."""
        from app.services.rbac_seed_service import seed_rbac_permissions_and_roles

        stats = seed_rbac_permissions_and_roles()
        click.echo("RBAC seed complete.")
        click.echo(
            f"- Permissions: {stats.get('created_permissions', 0)} created, {stats.get('updated_permissions', 0)} updated"
        )
        click.echo(
            f"- Roles: {stats.get('created_roles', 0)} created, {stats.get('updated_roles', 0)} updated"
        )
        click.echo(
            f"- Role-permission links: {stats.get('created_role_permission_links', 0)} created, {stats.get('deleted_role_permission_links', 0)} deleted"
        )

    # ========================================================================
    # Email / Notification Template Seeding
    # ========================================================================

    @app.cli.command('seed-email-templates')
    @click.option('--force', is_flag=True, help='Overwrite existing template values.')
    @with_appcontext
    def seed_email_templates_cmd(force):
        """Seed default email & notification templates (unified) into the database."""
        from scripts.seed_email_templates import seed_templates

        click.echo("\n=== Seeding Email & Notification Templates (unified) ===\n")
        stats = seed_templates(force=force)
        click.echo(
            f"\nDone!  Email content: {stats['email']['seeded']} seeded, "
            f"{stats['email']['skipped']} skipped.  "
            f"Pre-fill metadata: {stats['metadata']['seeded']} seeded, "
            f"{stats['metadata']['skipped']} skipped.\n"
        )
