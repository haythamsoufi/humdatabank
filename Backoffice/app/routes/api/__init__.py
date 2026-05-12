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

    # NOW register the blueprint with all routes already added
    # All modules above register their routes directly to api_bp during import
    app.register_blueprint(api_bp)
