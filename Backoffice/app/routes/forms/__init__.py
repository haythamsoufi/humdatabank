"""Forms blueprint package.

Modularized from the monolithic forms.py for maintainability.
Each submodule registers its routes onto the shared ``bp`` blueprint.
"""
from flask import Blueprint, current_app

bp = Blueprint("forms", __name__, url_prefix="/forms")

# Register additional route modules (validation summary was already separate)
from app.routes.forms_validation_summary import register_validation_summary_routes  # noqa: E402
register_validation_summary_routes(bp)

# Template global for getting frontend URL
@bp.app_template_global()
def get_frontend_url_global():
    """Template global for getting frontend URL."""
    try:
        from app.services.app_settings_service import get_frontend_url as _get_frontend_url
        url = _get_frontend_url()
        if url is None:
            return "#"
        return url
    except Exception as e:
        current_app.logger.debug("get_frontend_url failed: %s", e)
        return "#"


# Re-export helpers and key functions so existing imports like
# ``from app.routes.forms import process_existing_data_for_template``
# continue to work.
from .helpers import (  # noqa: E402, F401
    calculate_section_completion_status,
    debug_numeric_value,
    map_unified_item_to_original,
    process_existing_data_for_template,
    process_numeric_value,
)

from app.services.form_processing_service import slugify_age_group  # noqa: E402, F401
from app.utils.route_helpers import get_unified_form_url, get_unified_form_item_id  # noqa: E402, F401

# Register routes from submodules
from .entry import register_entry_routes, handle_assignment_form, _preview_template_impl  # noqa: E402, F401
register_entry_routes(bp)

from .submission import register_submission_routes, handle_public_submission_form  # noqa: E402, F401
register_submission_routes(bp)

from .documents import register_document_routes  # noqa: E402
register_document_routes(bp)

from .export import register_export_routes, _export_excel_impl, _import_excel_impl  # noqa: E402, F401
register_export_routes(bp)

# Re-export for backward-compatible test imports
export_focal_data_excel = _export_excel_impl
handle_excel_import = _import_excel_impl

from .matrix_api import register_matrix_api_routes  # noqa: E402
register_matrix_api_routes(bp)

# Make preview_template importable at package level (used by tests)
preview_template = _preview_template_impl
