"""
User Management Module - User CRUD operations and role management.

This package splits the user-management admin blueprint into submodules:

- helpers:  shared private helper functions
- crud:     HTML/form-based CRUD routes
- api:      JSON API endpoints
- entities: entity permission management routes
"""

from flask import Blueprint

bp = Blueprint("user_management", __name__, url_prefix="/admin")

# Import submodules to register routes on ``bp``.
# These MUST come after ``bp`` is defined to avoid circular imports.
from app.routes.admin.user_management import crud, api, entities  # noqa: E402, F401
