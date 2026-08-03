"""One-off script to split organization.py into a package."""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC_ORG = os.path.join(ROOT, "app", "routes", "admin", "organization.py")
ORG_PKG = os.path.join(ROOT, "app", "routes", "admin", "organization")
FORMS_PKG = os.path.join(ROOT, "app", "forms", "organization")

with open(SRC_ORG, "r", encoding="utf-8") as f:
    lines = f.readlines()


def slice_lines(start, end):
    return "".join(lines[start - 1 : end])


os.makedirs(ORG_PKG, exist_ok=True)
os.makedirs(FORMS_PKG, exist_ok=True)

helpers_body = slice_lines(172, 219)
collect_body = slice_lines(221, 521)
translation_helpers = (
    '"""Shared translation helpers for organization WTForms and routes."""\n'
    "import json\n"
    "from contextlib import suppress\n"
    "from typing import Any, Dict\n\n"
    "from flask import current_app, has_app_context\n"
    "from wtforms import StringField\n"
    "from wtforms.validators import Optional, Length\n\n"
    "from config.config import Config\n\n"
    + helpers_body
    + collect_body
)

with open(os.path.join(FORMS_PKG, "translation_helpers.py"), "w", encoding="utf-8") as f:
    f.write(translation_helpers)

forms_body = slice_lines(525, 678)
forms_py = (
    '"""WTForms for organization admin CRUD."""\n'
    "from flask_wtf import FlaskForm\n"
    "from wtforms import StringField, TextAreaField, BooleanField, IntegerField, SelectField, DateField\n"
    "from wtforms.validators import DataRequired, Optional, Length\n\n"
    "from app.models.organization import SecretariatRegionalOffice\n"
    "from app.services.organization.secretariat_regional_office_service import ensure_secretariat_regional_offices\n"
    "from app.forms.organization.translation_helpers import add_translation_fields\n\n"
    + forms_body.replace("_add_translation_fields", "add_translation_fields")
)

with open(os.path.join(FORMS_PKG, "forms.py"), "w", encoding="utf-8") as f:
    f.write(forms_py)

forms_init = '''"""Organization admin WTForms."""
from app.forms.organization.forms import (
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
)
from app.forms.organization.translation_helpers import (
    add_translation_fields,
    collect_translations,
    clear_translation_fields,
    populate_translation_fields,
    count_missing_name_translations,
    normalize_translations_dict,
    regional_office_translation_fields,
    resolve_field_translation,
    entity_translation_field_pairs,
    commit_translation_entity,
    count_missing_translations_for_fields,
    secretariat_translation_fields,
    secretariat_translation_jobs,
    stream_entity_translation_events,
    get_translation_languages,
    get_translation_codes,
)

__all__ = [
    "CountryForm",
    "NationalSocietyForm",
    "NSBranchForm",
    "NSSubBranchForm",
    "NSLocalUnitForm",
    "SecretariatDivisionForm",
    "SecretariatDepartmentForm",
    "SecretariatRegionalOfficeForm",
    "SecretariatClusterOfficeForm",
    "add_translation_fields",
    "collect_translations",
    "clear_translation_fields",
    "populate_translation_fields",
    "count_missing_name_translations",
    "normalize_translations_dict",
    "regional_office_translation_fields",
    "resolve_field_translation",
    "entity_translation_field_pairs",
    "commit_translation_entity",
    "count_missing_translations_for_fields",
    "secretariat_translation_fields",
    "secretariat_translation_jobs",
    "stream_entity_translation_events",
    "get_translation_languages",
    "get_translation_codes",
]
'''

th_path = os.path.join(FORMS_PKG, "translation_helpers.py")
with open(th_path, "r", encoding="utf-8") as f:
    th = f.read()
renames = [
    ("def _get_translation_languages", "def get_translation_languages"),
    ("def _get_translation_codes", "def get_translation_codes"),
    ("def _add_translation_fields", "def add_translation_fields"),
    ("def _collect_translations", "def collect_translations"),
    ("def _clear_translation_fields", "def clear_translation_fields"),
    ("def _populate_translation_fields", "def populate_translation_fields"),
    ("def _count_missing_name_translations", "def count_missing_name_translations"),
    ("def _normalize_translations_dict", "def normalize_translations_dict"),
    ("def _regional_office_translation_fields", "def regional_office_translation_fields"),
    ("def _resolve_field_translation", "def resolve_field_translation"),
    ("def _entity_translation_field_pairs", "def entity_translation_field_pairs"),
    ("def _commit_translation_entity", "def commit_translation_entity"),
    ("def _count_missing_translations_for_fields", "def count_missing_translations_for_fields"),
    ("def _secretariat_translation_fields", "def secretariat_translation_fields"),
    ("def _secretariat_translation_jobs", "def secretariat_translation_jobs"),
    ("def _stream_entity_translation_events", "def stream_entity_translation_events"),
    ("_get_translation_languages()", "get_translation_languages()"),
    ("_get_translation_codes()", "get_translation_codes()"),
    ("_normalize_translations_dict(", "normalize_translations_dict("),
    ("_entity_translation_field_pairs(", "entity_translation_field_pairs("),
    ("_resolve_field_translation(", "resolve_field_translation("),
    ("_commit_translation_entity(", "commit_translation_entity("),
]
for old, new in renames:
    th = th.replace(old, new)
with open(th_path, "w", encoding="utf-8") as f:
    f.write(th)

with open(os.path.join(FORMS_PKG, "__init__.py"), "w", encoding="utf-8") as f:
    f.write(forms_init)

COMMON_ROUTE_IMPORTS = '''import io
import json
import os
from datetime import datetime

import pandas as pd
from flask import render_template, redirect, url_for, request, flash, current_app, send_file
from flask_wtf import FlaskForm

from app.models import db
from app.models.core import Country
from app.models.organization import (
    NationalSociety,
    NSBranch,
    NSSubBranch,
    NSLocalUnit,
    SecretariatDivision,
    SecretariatDepartment,
    SecretariatRegionalOffice,
    SecretariatClusterOffice,
)
from app.services.organization.country_service import (
    assign_country_fds_member_user,
    countries_with_fds_member_query,
    fds_member_user_display_name,
    parse_fds_member_user_id,
    resolve_fds_member_user_id_from_import,
)
from app.services.organization.secretariat_regional_office_service import (
    assign_country_secretariat_regional_office,
)
from app.routes.admin.shared import (
    admin_permission_required,
    admin_permission_required_any,
    permission_required,
    permission_required_any,
)
from app.utils.request_utils import is_json_request
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.transactions import no_auto_transaction, request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_formatting import choices_from_query
from app.utils.api_responses import (
    json_bad_request,
    json_error,
    json_ok,
    json_select_options,
    json_server_error,
    require_json_data,
    require_json_keys,
)
from app.utils.error_handling import handle_json_view_exception
from config.config import Config
from app.forms.organization import (
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
    collect_translations,
    clear_translation_fields,
    populate_translation_fields,
    count_missing_name_translations,
    count_missing_translations_for_fields,
    secretariat_translation_fields,
    secretariat_translation_jobs,
    regional_office_translation_fields,
    stream_entity_translation_events,
    commit_translation_entity,
)
from . import bp

'''


def fix_helper_calls(body):
    replacements = [
        ("_collect_translations", "collect_translations"),
        ("_clear_translation_fields", "clear_translation_fields"),
        ("_populate_translation_fields", "populate_translation_fields"),
        ("_count_missing_name_translations", "count_missing_name_translations"),
        ("_count_missing_translations_for_fields", "count_missing_translations_for_fields"),
        ("_secretariat_translation_fields", "secretariat_translation_fields"),
        ("_secretariat_translation_jobs", "secretariat_translation_jobs"),
        ("_regional_office_translation_fields", "regional_office_translation_fields"),
        ("_stream_entity_translation_events", "stream_entity_translation_events"),
        ("_commit_translation_entity", "commit_translation_entity"),
    ]
    for old, new in replacements:
        body = body.replace(old, new)
    return body


countries_body = fix_helper_calls(slice_lines(679, 1053))
with open(os.path.join(ORG_PKG, "countries.py"), "w", encoding="utf-8") as f:
    f.write('"""Organization dashboard and country CRUD routes."""\n' + COMMON_ROUTE_IMPORTS + countries_body)

import_export_body = fix_helper_calls(slice_lines(1056, 1646))
with open(os.path.join(ORG_PKG, "import_export.py"), "w", encoding="utf-8") as f:
    f.write('"""Excel import/export routes for countries and national societies."""\n' + COMMON_ROUTE_IMPORTS + import_export_body)

ns_parts = [
    slice_lines(1331, 1425),
    slice_lines(1649, 2051),
    slice_lines(2446, 2503),
    slice_lines(2874, 3009),
]
ns_body = fix_helper_calls("".join(ns_parts))
ns_imports = COMMON_ROUTE_IMPORTS.replace(
    "from flask import render_template, redirect, url_for, request, flash, current_app, send_file",
    "from flask import render_template, redirect, url_for, request, flash, current_app\n"
    "from app.extensions import limiter\n"
    "from app.routes.admin.shared import rbac_guard_audit_exempt",
)
with open(os.path.join(ORG_PKG, "ns_structure.py"), "w", encoding="utf-8") as f:
    f.write('"""National Society and NS structure routes and APIs."""\n' + ns_imports + ns_body)

sec_parts = [
    slice_lines(2054, 2431),
    slice_lines(2434, 2441),
    slice_lines(2506, 2871),
]
sec_body = fix_helper_calls("".join(sec_parts))
with open(os.path.join(ORG_PKG, "secretariat.py"), "w", encoding="utf-8") as f:
    f.write('"""Secretariat structure routes and translation APIs."""\n' + COMMON_ROUTE_IMPORTS + sec_body)

init_body = slice_lines(59, 170)
init_py = (
    '"""\n'
    "Organization Management Routes - Unified management for all organizational entities.\n\n"
    "This blueprint provides CRUD operations for:\n"
    "- Countries\n"
    "- NS Branches, Sub-branches, and Local Units\n"
    "- Secretariat Divisions and Departments\n"
    '"""\n'
    "from flask import Blueprint, flash, redirect, url_for, request\n"
    "from flask_login import current_user\n\n"
    "from app.utils.api_responses import json_error\n\n"
    "bp = Blueprint('organization', __name__, url_prefix='/admin/organization')\n\n"
    + init_body
    + """

# Register route modules (must follow bp definition)
from app.routes.admin.organization import countries, import_export, ns_structure, secretariat  # noqa: E402, F401

# Re-export forms and helpers for backward compatibility
from app.forms.organization import (  # noqa: E402
    CountryForm,
    NationalSocietyForm,
    NSBranchForm,
    NSSubBranchForm,
    NSLocalUnitForm,
    SecretariatDivisionForm,
    SecretariatDepartmentForm,
    SecretariatRegionalOfficeForm,
    SecretariatClusterOfficeForm,
    count_missing_name_translations,
    regional_office_translation_fields,
    resolve_field_translation,
    get_translation_languages,
    get_translation_codes,
)

__all__ = [
    "bp",
    "CountryForm",
    "NationalSocietyForm",
    "NSBranchForm",
    "NSSubBranchForm",
    "NSLocalUnitForm",
    "SecretariatDivisionForm",
    "SecretariatDepartmentForm",
    "SecretariatRegionalOfficeForm",
    "SecretariatClusterOfficeForm",
    "count_missing_name_translations",
    "regional_office_translation_fields",
    "resolve_field_translation",
    "get_translation_languages",
    "get_translation_codes",
]
"""
)
with open(os.path.join(ORG_PKG, "__init__.py"), "w", encoding="utf-8") as f:
    f.write(init_py)

os.remove(SRC_ORG)
print("Organization package created successfully")
