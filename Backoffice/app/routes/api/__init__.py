# Backoffice/app/routes/api/__init__.py
"""
API Module - Centralized registration of all API blueprints
"""

from flask import Blueprint

# Create main API blueprint
api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

# Register all sub-blueprints
def register_api_blueprints(app):
    """Register all API blueprints with the main application"""
    # IMPORT ALL MODULES FIRST to register their routes with api_bp
    # This must happen BEFORE registering the blueprint with the app
    # The routes are registered directly to api_bp, so we just need to import them
    from app.routes.api import submissions  # noqa: F401
    from app.routes.api import data  # noqa: F401
    from app.routes.api import templates  # noqa: F401
    from app.routes.api import countries  # noqa: F401
    from app.routes.api import resources  # noqa: F401
    from app.routes.api import indicators  # noqa: F401
    from app.routes.api import users  # noqa: F401
    from app.routes.api import assignments  # noqa: F401
    from app.routes.api import documents  # noqa: F401
    from app.routes.api import quiz  # noqa: F401
    from app.routes.api import common  # noqa: F401
    from app.routes.api import variables  # noqa: F401
    from app.routes.api import error_log  # noqa: F401
    from app.routes.api import embed_content  # noqa: F401
    from app.routes.api import indicator_bank_compat  # noqa: F401
    from app.routes.api import data_quality  # noqa: F401
    from app.routes.api import validation_questions  # noqa: F401
    from app.routes.api import public_integrations  # noqa: F401

    # NOW register the blueprint with all routes already added
    # All modules above register their routes directly to api_bp during import
    app.register_blueprint(api_bp)

    @app.after_request
    def _harden_query_string_api_key_responses(response):
        """Keys sent as ``?api_key=`` leak via URLs, logs and Referer; make that visible and limit it."""
        from flask import g

        if getattr(g, 'api_key_via_query', False):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Warning'] = (
                '299 - "API key sent in the query string is deprecated; '
                'send it in the Authorization: Bearer header"'
            )
        return response
