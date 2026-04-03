import logging
import os
from logging.config import fileConfig

from flask import current_app, has_app_context

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')


def _normalize_database_uri(uri):
    """Normalize database URI to ensure Postgres works across providers."""
    if not uri:
        return uri
    # Normalize scheme
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    # Ensure driver is explicit
    if uri.startswith("postgresql://") and "+psycopg2" not in uri:
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    return uri


def get_engine():
    """Get database engine from Flask app context if available."""
    if has_app_context():
        try:
            # this works with Flask-SQLAlchemy<3 and Alchemical
            return current_app.extensions['migrate'].db.get_engine()
        except (TypeError, AttributeError):
            # this works with Flask-SQLAlchemy>=3
            return current_app.extensions['migrate'].db.engine
    return None


def get_engine_url():
    """Get database URL from Flask app context or environment variable."""
    # Try to get URL from Flask app context first
    if has_app_context():
        try:
            engine = get_engine()
            if engine:
                try:
                    return engine.url.render_as_string(hide_password=False).replace('%', '%%')
                except AttributeError:
                    return str(engine.url).replace('%', '%%')
        except Exception as e:
            logger.warning(f"Failed to get engine URL from Flask app context: {e}")

    # Fall back to reading DATABASE_URL from environment
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        logger.info("Using DATABASE_URL from environment variable")
        normalized_url = _normalize_database_uri(database_url)
        return normalized_url.replace('%', '%%') if normalized_url else database_url.replace('%', '%%')

    # Last resort: try to get from Flask config if app context exists
    if has_app_context():
        try:
            db_url = current_app.config.get('SQLALCHEMY_DATABASE_URI')
            if db_url:
                logger.info("Using SQLALCHEMY_DATABASE_URI from Flask config")
                normalized_url = _normalize_database_uri(db_url)
                return normalized_url.replace('%', '%%') if normalized_url else db_url.replace('%', '%%')
        except Exception as e:
            logger.warning(f"Failed to get database URL from Flask config: {e}")

    raise RuntimeError(
        "Could not determine database URL. "
        "Please set DATABASE_URL environment variable or ensure Flask app context is available."
    )


def get_target_db():
    """Get target database from Flask app context if available."""
    if has_app_context():
        try:
            return current_app.extensions['migrate'].db
        except (TypeError, AttributeError, KeyError):
            pass
    return None


# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
database_url = get_engine_url()
config.set_main_option('sqlalchemy.url', database_url)
target_db = get_target_db()

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_metadata():
    """Get database metadata from Flask app context if available."""
    if target_db:
        if hasattr(target_db, 'metadatas'):
            return target_db.metadatas[None]
        return target_db.metadata

    # If we can't get metadata from Flask app, we need to import models
    # This is a fallback for when Flask app context is not available
    try:
        from app import create_app
        from app.extensions import db

        # Create a minimal app context to get metadata
        app = create_app()
        with app.app_context():
            if hasattr(db, 'metadatas'):
                return db.metadatas[None]
            return db.metadata
    except Exception as e:
        logger.warning(f"Failed to get metadata from Flask app: {e}")
        # Return empty metadata as last resort
        from sqlalchemy import MetaData
        return MetaData()


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url, target_metadata=get_metadata(), literal_binds=True
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    # Get configure_args from Flask app context if available
    conf_args = {}
    if has_app_context():
        try:
            conf_args = current_app.extensions['migrate'].configure_args.copy()
            if conf_args.get("process_revision_directives") is None:
                conf_args["process_revision_directives"] = process_revision_directives
        except (TypeError, AttributeError, KeyError):
            pass

    # If we couldn't get conf_args from Flask app, use defaults
    if not conf_args:
        conf_args = {"process_revision_directives": process_revision_directives}

    # Try to get engine from Flask app context, otherwise create from URL
    connectable = get_engine()
    if connectable is None:
        # Create engine directly from database URL
        from sqlalchemy import create_engine
        database_url = config.get_main_option("sqlalchemy.url")
        connectable = create_engine(database_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=get_metadata(),
            **conf_args
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
