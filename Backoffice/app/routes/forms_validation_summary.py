"""Backward-compatible import path.

The validation summary routes live in ``app.routes.forms.validation_summary``.
"""

from app.routes.forms.validation_summary import register_validation_summary_routes

__all__ = ["register_validation_summary_routes"]
