"""
AUTO-GENERATED — merged activity catalog from per-blueprint partials.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec, merge_activity_specs

from app.utils.activity_endpoint_catalog.generated.partials.admin_notifications import SPECS as _S_admin_notifications
from app.utils.activity_endpoint_catalog.generated.partials.ai_documents import SPECS as _S_ai_documents
from app.utils.activity_endpoint_catalog.generated.partials.ai_management import SPECS as _S_ai_management
from app.utils.activity_endpoint_catalog.generated.partials.ai_v2 import SPECS as _S_ai_v2
from app.utils.activity_endpoint_catalog.generated.partials.analytics import SPECS as _S_analytics
from app.utils.activity_endpoint_catalog.generated.partials.assignment_management import SPECS as _S_assignment_management
from app.utils.activity_endpoint_catalog.generated.partials.auth import SPECS as _S_auth
from app.utils.activity_endpoint_catalog.generated.partials.content_management import SPECS as _S_content_management
from app.utils.activity_endpoint_catalog.generated.partials.data_exploration import SPECS as _S_data_exploration
from app.utils.activity_endpoint_catalog.generated.partials.embed_management import SPECS as _S_embed_management
from app.utils.activity_endpoint_catalog.generated.partials.excel import SPECS as _S_excel
from app.utils.activity_endpoint_catalog.generated.partials.form_builder import SPECS as _S_form_builder
from app.utils.activity_endpoint_catalog.generated.partials.forms import SPECS as _S_forms
from app.utils.activity_endpoint_catalog.generated.partials.forms_api import SPECS as _S_forms_api
from app.utils.activity_endpoint_catalog.generated.partials.main import SPECS as _S_main
from app.utils.activity_endpoint_catalog.generated.partials.monitoring import SPECS as _S_monitoring
from app.utils.activity_endpoint_catalog.generated.partials.notifications import SPECS as _S_notifications
from app.utils.activity_endpoint_catalog.generated.partials.organization import SPECS as _S_organization
from app.utils.activity_endpoint_catalog.generated.partials.plugin_management import SPECS as _S_plugin_management
from app.utils.activity_endpoint_catalog.generated.partials.public import SPECS as _S_public
from app.utils.activity_endpoint_catalog.generated.partials.rbac_management import SPECS as _S_rbac_management
from app.utils.activity_endpoint_catalog.generated.partials.security import SPECS as _S_security
from app.utils.activity_endpoint_catalog.generated.partials.settings import SPECS as _S_settings
from app.utils.activity_endpoint_catalog.generated.partials.system_admin import SPECS as _S_system_admin
from app.utils.activity_endpoint_catalog.generated.partials.template_special import SPECS as _S_template_special
from app.utils.activity_endpoint_catalog.generated.partials.user_management import SPECS as _S_user_management
from app.utils.activity_endpoint_catalog.generated.partials.utilities import SPECS as _S_utilities

GENERATED_ACTIVITY_SPECS: dict[tuple[str, str], ActivityEndpointSpec] = merge_activity_specs(
    _S_admin_notifications,
    _S_ai_documents,
    _S_ai_management,
    _S_ai_v2,
    _S_analytics,
    _S_assignment_management,
    _S_auth,
    _S_content_management,
    _S_data_exploration,
    _S_embed_management,
    _S_excel,
    _S_form_builder,
    _S_forms,
    _S_forms_api,
    _S_main,
    _S_monitoring,
    _S_notifications,
    _S_organization,
    _S_plugin_management,
    _S_public,
    _S_rbac_management,
    _S_security,
    _S_settings,
    _S_system_admin,
    _S_template_special,
    _S_user_management,
    _S_utilities,
    allow_override=False,
)

