"""
Form Builder Module - Template, Section, and Form Item Management

Modular package exposing the ``form_builder`` Flask blueprint.  Route handlers
are split across sub-modules (templates, kobo, sections, items, versions) and
private helper functions live in ``helpers``.
"""

from contextlib import suppress

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, session
from flask_login import current_user
from flask_babel import _
from flask_wtf import FlaskForm
from werkzeug.datastructures import ImmutableMultiDict
from app import db, csrf
from app.models import (
    FormTemplate, FormSection, FormItem, FormItemType, FormPage, IndicatorBank,
    QuestionType, Sector, SubSector, LookupList, LookupListRow,
    TemplateShare, User, FormTemplateVersion, AssignedForm
)
from app.models.core import Country
from app.models.organization import NationalSociety
from app.forms.form_builder import (
    FormTemplateForm, FormSectionForm, IndicatorForm, QuestionForm, DocumentFieldForm
)
from app.routes.admin.shared import (
    admin_required,
    admin_permission_required,
    permission_required,
    system_manager_required,
    get_localized_sector_name,
    get_localized_subsector_name,
    check_template_access,
)
from app.utils.request_utils import is_json_request
from app.services.security.api_authentication import get_user_allowed_template_ids
from app.services.user_analytics_service import log_admin_action
from app.services.template_excel_service import TemplateExcelService
from app.services.kobo_xls_import_service import KoboXlsImportService
from app.services.kobo_data_import_service import KoboDataImportService
from app.utils.error_handling import handle_view_exception, handle_json_view_exception
from app.services.section_duplication_service import SectionDuplicationService
from app.services.item_duplication_service import ItemDuplicationService
from flask import send_file
from werkzeug.utils import secure_filename
from sqlalchemy import func, cast, String, select, inspect, literal
from config.config import Config
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_forbidden, json_bad_request, json_not_found, json_ok, json_server_error, json_form_errors
from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from app.utils.advanced_validation import validate_upload_extension_and_mime
from app.utils.file_parsing import EXCEL_EXTENSIONS
from datetime import datetime
import json
import re

bp = Blueprint("form_builder", __name__, url_prefix="/admin")


def _parse_version_translations_from_form(json_key: str, explicit_prefix: str) -> dict:
    """
    Parse version translations from form: JSON hidden field + explicit code inputs.

    Args:
        json_key: Form key for JSON (e.g. 'name_translations', 'description_translations')
        explicit_prefix: Prefix for code-based inputs (e.g. 'name', 'description') -> name_fr, description_fr

    Returns:
        Dict mapping ISO language code -> translated string.
    """
    translations_by_code = {}
    supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))

    with suppress((TypeError, json.JSONDecodeError)):
        raw_json = request.form.get(json_key)
        if raw_json:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            translations_by_code[code] = v.strip()

    for code in supported_codes:
        if code == 'en':
            continue
        raw_val = request.form.get(f'{explicit_prefix}_{code}')
        if isinstance(raw_val, str) and raw_val.strip():
            translations_by_code[code] = raw_val.strip()

    return translations_by_code


def _handle_version_translations(version, form):
    """Normalize and save version name translations using ISO codes (e.g., 'fr')."""
    translations_by_code = _parse_version_translations_from_form('name_translations', 'name')
    version.name_translations = translations_by_code if translations_by_code else None


def _handle_version_description_translations(version, form):
    """Normalize and save version description translations using ISO codes (e.g., 'fr')."""
    translations_by_code = _parse_version_translations_from_form('description_translations', 'description')
    version.description_translations = translations_by_code if translations_by_code else None

def _populate_version_translations(form, version):
    """Populate WTForm fields from stored ISO code keyed translations in version."""
    return

def _populate_version_description_translations(form, version):
    """Populate WTForm description fields from stored ISO code keyed translations in version."""
    return

def get_translation_value(translations_dict, language_key, default=''):
    """Helper function to get translation value from a translations dictionary"""
    if translations_dict and hasattr(translations_dict, 'get'):
        return translations_dict.get(language_key, default)
    return default


# Register route sub-modules (import triggers @bp.route decorators)
from . import templates, kobo, sections, items, versions  # noqa: E402, F401
