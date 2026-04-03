from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app, send_file, send_from_directory
from flask_login import login_required, current_user
from app.models import db, User, AssignedForm, Country, FormTemplate, FormTemplateVersion, FormData, PublicSubmission, PublicSubmissionStatus, SubmittedDocument, FormSection, FormItem, FormItemType, QuestionType, Notification, EntityActivityLog, CountryAccessRequest, UserSessionLog # Import necessary models - legacy Indicator, Question, DocumentField models removed
from app.models.documents import submitted_document_countries
from app.models.system import CountryAccessRequestStatus
from app.models.assignments import AssignmentEntityStatus
from app.models.core import UserEntityPermission
from app.models.rbac import RbacUserRole, RbacRole
from app.models.enums import EntityType
from app.services.entity_service import EntityService
from sqlalchemy import and_, or_, func, case, cast, literal
from sqlalchemy.types import Boolean
from sqlalchemy.orm import aliased, joinedload
from app.services import get_assignments_for_country, get_user_countries
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY, SELF_REPORT_PERIOD_NAME
from app.utils.form_localization import get_localized_country_name, get_localized_national_society_name as _get_localized_national_society_name, get_localized_template_name as _get_localized_template_name
from datetime import datetime
from app.utils.notifications import get_country_recent_activities
from app.forms.shared import DeleteForm
from app.forms.assignments import ReopenAssignmentForm, ApproveAssignmentForm
from app.forms.auth_forms import RequestCountryAccessForm
from io import BytesIO
import os
from flask_babel import get_locale, _
from config import Config
import json
import re
from app.utils.entity_groups import get_allowed_entity_type_codes, get_enabled_entity_groups
from contextlib import suppress
from app.utils.datetime_helpers import utcnow
from app.utils.transactions import request_transaction_rollback
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_forbidden, json_ok, json_server_error
from app.utils.error_handling import handle_json_view_exception
from app.utils.app_settings import is_organization_email, user_has_ai_beta_access
from app.extensions import limiter
bp = Blueprint("main", __name__)


# Template helper for RBAC permission checks in UI
@bp.app_context_processor
def inject_rbac_helpers():
    """Inject RBAC helper functions into all templates"""
    from app.services.authorization_service import AuthorizationService

    def has_permission(permission_code, scope=None):
        """Check if current user has a specific RBAC permission"""
        try:
            return AuthorizationService.has_rbac_permission(current_user, permission_code, scope=scope)
        except Exception as e:
            current_app.logger.debug("has_rbac_permission failed: %s", e)
            return False

    def can_approve_assignment(aes):
        """Check if current user can approve an assignment"""
        try:
            return AuthorizationService.can_approve_assignment(aes, current_user)
        except Exception as e:
            current_app.logger.debug("can_approve_assignment failed: %s", e)
            return False

    def can_reopen_assignment(aes):
        """Check if current user can reopen an assignment"""
        try:
            return AuthorizationService.can_reopen_assignment(aes, current_user)
        except Exception as e:
            current_app.logger.debug("can_reopen_assignment failed: %s", e)
            return False

    def can_reopen_closed_assignment(assignment):
        """Check if current user can reopen a closed assignment (admin only)."""
        if not assignment:
            return False
        try:
            if AuthorizationService.is_system_manager(current_user):
                return True
            return AuthorizationService.has_rbac_permission(current_user, "admin.assignments.edit")
        except Exception as e:
            current_app.logger.debug("can_reopen_closed_assignment failed: %s", e)
            return False

    return dict(
        has_permission=has_permission,
        can_approve_assignment=can_approve_assignment,
        can_reopen_assignment=can_reopen_assignment,
        can_reopen_closed_assignment=can_reopen_closed_assignment
    )


@bp.route("/documents", methods=["GET", "POST"])
@login_required
def documents_submit():
    """
    Non-admin document library for focal users: documents for the **selected entity**
    (same session keys as the dashboard), including uploads by any user on that entity's
    assignments and standalone library rows linked to that entity.
    """
    from app.services.authorization_service import AuthorizationService
    from app.utils.app_settings import get_document_types
    from app.routes.admin.content_management import _row_with_focal_entity_access

    if AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(
        current_user, "admin.documents.manage"
    ):
        return redirect(url_for("content_management.manage_documents"))

    if not AuthorizationService.has_rbac_permission(current_user, "assignment.documents.upload"):
        flash(_("Access denied."), "warning")
        return redirect(url_for("main.dashboard"))

    document_types = get_document_types(default=Config.DOCUMENT_TYPES)
    current_app.config["DOCUMENT_TYPES"] = document_types
    with suppress(Exception):
        current_app.jinja_env.globals["DOCUMENT_TYPES"] = document_types

    user_entities, user_countries, allowed_entity_types = _build_user_nav_entities(current_user)
    if not user_entities:
        flash(_("Your user account is not associated with any enabled entities. Please contact an administrator."), "warning")
        return redirect(url_for("main.dashboard"))

    enabled_entity_groups = get_enabled_entity_groups()
    countries_group_enabled = "countries" in enabled_entity_groups

    if request.method == "POST" and "entity_select" in request.form:
        entity_select_value = request.form.get("entity_select", "")
        if entity_select_value and ":" in entity_select_value:
            try:
                selected_type, selected_id_str = entity_select_value.split(":", 1)
                selected_id = int(selected_id_str)
                user_entity_pairs = {(e["entity_type"], e["entity_id"]) for e in user_entities}
                if (selected_type, selected_id) in user_entity_pairs or current_user.has_entity_access(
                    selected_type, selected_id
                ):
                    session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_type
                    session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_id
                    with suppress(Exception):
                        related_country = EntityService.get_country_for_entity(selected_type, selected_id)
                        if related_country:
                            session[SELECTED_COUNTRY_ID_SESSION_KEY] = related_country.id
                else:
                    session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                    session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                    flash(_("Invalid entity selection or entity not assigned to you."), "warning")
            except ValueError:
                flash(_("Invalid entity ID format."), "warning")
        else:
            flash(_("Invalid entity selection."), "warning")
        return redirect(url_for("main.documents_submit"))

    selected_entity, selected_entity_type, selected_entity_id, _selected_country = _resolve_selected_entity_for_focal_nav(
        current_user,
        user_entities,
        user_countries,
        allowed_entity_types,
        countries_group_enabled=countries_group_enabled,
    )
    if not selected_entity or selected_entity_type is None or selected_entity_id is None:
        flash(_("Unable to determine which entity to show documents for."), "warning")
        return redirect(url_for("main.dashboard"))

    sel_type = selected_entity_type
    sel_id = int(selected_entity_id)

    aes_id_subq = db.session.query(AssignmentEntityStatus.id).filter(
        AssignmentEntityStatus.entity_type == sel_type,
        AssignmentEntityStatus.entity_id == sel_id,
    )

    assignment_raw = (
        db.session.query(
            SubmittedDocument,
            SubmittedDocument.status.label("status"),
            User,
            SubmittedDocument.uploaded_at.label("uploaded_at"),
            AssignedForm.period_name.label("assignment_period"),
            AssignmentEntityStatus,
        )
        .join(User, SubmittedDocument.uploaded_by_user_id == User.id)
        .join(AssignmentEntityStatus, SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id)
        .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(SubmittedDocument.assignment_entity_status_id.in_(aes_id_subq))
        .order_by(SubmittedDocument.uploaded_at.desc())
        .all()
    )

    assignment_tuples = []
    for doc, status, user, uploaded_at, assignment_period, aes in assignment_raw:
        resolved_country = aes.country
        assignment_tuples.append((doc, status, resolved_country, user, uploaded_at, assignment_period))

    standalone_clauses = [
        and_(
            SubmittedDocument.linked_entity_type == sel_type,
            SubmittedDocument.linked_entity_id == sel_id,
        ),
        SubmittedDocument.storage_path.like(f"{sel_type}/{sel_id}/%"),
    ]
    if sel_type == EntityType.country.value:
        m2m_for_country = db.session.query(submitted_document_countries.c.submitted_document_id).filter(
            submitted_document_countries.c.country_id == sel_id
        )
        standalone_clauses.extend(
            [
                SubmittedDocument.country_id == sel_id,
                SubmittedDocument.id.in_(m2m_for_country),
            ]
        )

    standalone_docs_query = (
        db.session.query(
            SubmittedDocument,
            SubmittedDocument.status.label("status"),
            Country,
            User,
            SubmittedDocument.uploaded_at.label("uploaded_at"),
            literal(None).label("assignment_period"),
        )
        .join(User, SubmittedDocument.uploaded_by_user_id == User.id)
        .outerjoin(Country, SubmittedDocument.country_id == Country.id)
        .filter(
            SubmittedDocument.assignment_entity_status_id.is_(None),
            SubmittedDocument.public_submission_id.is_(None),
            or_(*standalone_clauses),
        )
        .order_by(SubmittedDocument.uploaded_at.desc())
    )

    by_doc_id = {}
    for t in assignment_tuples:
        by_doc_id[t[0].id] = t
    standalone_query_rows = standalone_docs_query.all()
    for t in standalone_query_rows:
        if t[0].id not in by_doc_id:
            by_doc_id[t[0].id] = t

    merged = sorted(by_doc_id.values(), key=lambda row: row[4] or datetime.min, reverse=True)
    documents = [_row_with_focal_entity_access(r) for r in merged]

    show_entity_select = len(user_entities) > 1
    documents_entity_repo_label = None
    if not show_entity_select:
        try:
            documents_entity_repo_label = "{} — {}".format(
                EntityService.get_localized_entity_name(sel_type, sel_id, include_hierarchy=True),
                _("Document repository"),
            )
        except Exception:
            documents_entity_repo_label = None
    log_pfx = "[documents_submit]"
    current_app.logger.info(
        "%s user_id=%s entity=%s:%s assignment_rows=%s standalone_rows=%s merged=%s final_rows=%s show_entity_select=%s",
        log_pfx,
        getattr(current_user, "id", None),
        sel_type,
        sel_id,
        len(assignment_raw),
        len(standalone_query_rows),
        len(merged),
        len(documents),
        show_entity_select,
    )

    next_url = url_for("main.documents_submit")

    # Upload modal: country list = nav entities' countries plus any legacy user.countries assignments
    modal_country_ids = {c.id for c in user_countries}
    countries_for_modal = list(user_countries)
    try:
        for c in current_user.countries.all():
            if c.id not in modal_country_ids:
                modal_country_ids.add(c.id)
                countries_for_modal.append(c)
    except Exception:
        pass

    document_entity_types = [
        {"value": et.value, "label": EntityService.get_entity_type_label(et.value)}
        for et in EntityType
    ]

    documents_modal_entity_choices = _document_modal_entity_choice_rows(user_entities) if show_entity_select else None

    return render_template(
        "admin/documents/documents.html",
        documents=documents,
        countries=countries_for_modal,
        # Focal page already scopes by entity (selector above grid); omit redundant Entity column.
        show_country_column=False,
        title=_("Submit Documents"),
        page_title=_("Submit Documents"),
        next_url=next_url,
        upload_action_url=url_for("content_management.upload_document", next=next_url),
        user_entities=user_entities,
        show_entity_select=show_entity_select,
        documents_entity_repo_label=documents_entity_repo_label,
        selected_entity=selected_entity,
        selected_entity_type=selected_entity_type,
        selected_entity_id=selected_entity_id,
        document_entity_types=document_entity_types,
        standalone_entity_options_url=url_for("content_management.standalone_document_entity_options"),
        documents_repo_team_pending_edit=True,
        documents_modal_lock_entity_to_nav=True,
        documents_modal_entity_choices=documents_modal_entity_choices,
    )


@bp.route("/flags/<language>.svg")
@limiter.exempt
def language_flag_svg(language):
    """Serve a flag SVG for a language code from same-origin.

    Windows often renders regional-indicator flag emojis as letters (e.g., "JP").
    To make flags reliable, we serve a small SVG (Twemoji) via this endpoint so
    CSP img-src 'self' continues to work without allowing external image hosts.
    """
    from flask import make_response, send_from_directory
    from app.utils.language_flags import (
        normalize_language_code,
        language_to_country_flag_code,
    )

    lang = normalize_language_code(language or "") or "en"
    cc = language_to_country_flag_code(lang) or "un"

    # Flags MUST be served from local disk only.
    # We prefetch and store flags when system settings (supported languages) change.
    cache_dir = os.path.join(current_app.instance_path, "flag_cache")
    with suppress(Exception):
        os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{cc}.svg")

    # Check if we're in development mode - disable caching in development
    is_development = current_app.config.get('DEBUG', False)

    # Serve cached flag if present
    with suppress(Exception):
        if os.path.exists(cache_path):
            resp = send_from_directory(cache_dir, f"{cc}.svg")
            resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
            if is_development:
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
            else:
                resp.headers["Cache-Control"] = "public, max-age=31536000"
            return resp

    # Local placeholder (no network fetches here)
    static_dir = os.path.join(current_app.root_path, "static")
    resp = send_from_directory(os.path.join(static_dir, "images", "flags"), "placeholder.svg")
    resp.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    if is_development:
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    else:
        resp.headers["Cache-Control"] = "public, max-age=31536000"
    return resp

def _parse_int(value, field_name, *, minimum=None) -> int:
    """Parse an integer from form inputs with optional minimum enforcement."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}")

    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return parsed

# Session keys for entity selection (multi-entity support)
SELECTED_ENTITY_TYPE_SESSION_KEY = 'selected_entity_type'
SELECTED_ENTITY_ID_SESSION_KEY = 'selected_entity_id'


def _build_user_nav_entities(current_user):
    """Build the same entity list as the dashboard (permissions + enabled entity groups)."""
    user_entities = []
    entity_permissions = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
    if entity_permissions:
        for perm in entity_permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                user_entities.append(
                    {
                        "entity_type": perm.entity_type,
                        "entity_id": perm.entity_id,
                        "entity": entity,
                    }
                )
    else:
        all_entities = EntityService.get_entities_for_user(current_user)
        for ent in all_entities:
            entity_type = None
            if isinstance(ent, Country):
                entity_type = EntityType.country.value
            else:
                for et, model_class in EntityService.ENTITY_MODEL_MAP.items():
                    if isinstance(ent, model_class):
                        entity_type = et
                        break
            if entity_type:
                eid = getattr(ent, "id", None)
                if eid is not None:
                    user_entities.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": eid,
                            "entity": ent,
                        }
                    )

    enabled_entity_groups = get_enabled_entity_groups()
    allowed_entity_types = get_allowed_entity_type_codes(enabled_entity_groups)
    if allowed_entity_types:
        user_entities = [e for e in user_entities if e["entity_type"] in allowed_entity_types]
    else:
        user_entities = []

    user_countries = [
        e["entity"]
        for e in user_entities
        if e["entity_type"] == EntityType.country.value and isinstance(e["entity"], Country)
    ]
    return user_entities, user_countries, allowed_entity_types


def _document_modal_entity_choice_rows(user_entities):
    """Rows for document modal entity <select> (focal users: assigned entities only)."""
    rows = []
    for e in user_entities or []:
        et = e.get("entity_type")
        eid = e.get("entity_id")
        if not et or eid is None:
            continue
        try:
            label = EntityService.get_localized_entity_name(et, int(eid), include_hierarchy=True)
        except Exception:
            label = f"{et} #{eid}"
        rows.append({"entity_type": et, "entity_id": int(eid), "label": label})
    EntityService.sort_document_modal_entity_choice_rows(rows)
    return rows


def _resolve_selected_entity_for_focal_nav(
    current_user,
    user_entities,
    user_countries,
    allowed_entity_types,
    *,
    countries_group_enabled: bool,
):
    """Resolve selected entity from session (shared with dashboard) or default alphabetically."""
    selected_entity = None
    selected_entity_type = None
    selected_entity_id = None
    selected_country = None

    if SELECTED_ENTITY_TYPE_SESSION_KEY in session and SELECTED_ENTITY_ID_SESSION_KEY in session:
        retrieved_entity_type = session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)
        retrieved_entity_id = session.get(SELECTED_ENTITY_ID_SESSION_KEY)
        temp_entity = EntityService.get_entity(retrieved_entity_type, retrieved_entity_id)
        if temp_entity and retrieved_entity_type in allowed_entity_types:
            if current_user.has_entity_access(retrieved_entity_type, retrieved_entity_id):
                selected_entity_type = retrieved_entity_type
                selected_entity_id = retrieved_entity_id
                selected_entity = temp_entity
                if retrieved_entity_type == EntityType.country.value:
                    selected_country = temp_entity
                    session[SELECTED_COUNTRY_ID_SESSION_KEY] = retrieved_entity_id
            else:
                session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
        else:
            session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
            session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)

    elif countries_group_enabled and SELECTED_COUNTRY_ID_SESSION_KEY in session:
        retrieved_country_id = session[SELECTED_COUNTRY_ID_SESSION_KEY]
        temp_selected_country = Country.query.get(retrieved_country_id)
        if temp_selected_country:
            user_country_ids = [c.id for c in user_countries] if user_countries else []
            if temp_selected_country.id in user_country_ids or current_user.has_entity_access(
                EntityType.country.value, temp_selected_country.id
            ):
                selected_country = temp_selected_country
                selected_entity_type = EntityType.country.value
                selected_entity_id = temp_selected_country.id
                selected_entity = temp_selected_country
                session[SELECTED_ENTITY_TYPE_SESSION_KEY] = EntityType.country.value
                session[SELECTED_ENTITY_ID_SESSION_KEY] = temp_selected_country.id
            else:
                session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)

    if selected_entity is None and user_entities:

        def get_sort_key(e):
            display_name = EntityService.get_entity_name(
                e["entity_type"],
                e["entity_id"],
                include_hierarchy=True,
            )
            return (display_name or "").lower()

        sorted_entities = sorted(user_entities, key=get_sort_key)
        first_entity = sorted_entities[0]
        selected_entity_type = first_entity["entity_type"]
        selected_entity_id = first_entity["entity_id"]
        selected_entity = first_entity["entity"]
        if selected_entity_type == EntityType.country.value:
            selected_country = selected_entity
            session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_entity.id
        session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_entity_type
        session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_entity_id

    if selected_entity and selected_entity_type and selected_entity_id:
        entity_country = EntityService.get_country_for_entity(selected_entity_type, selected_entity_id)
        if entity_country:
            selected_country = entity_country

    return selected_entity, selected_entity_type, selected_entity_id, selected_country


# Logging configuration is now handled centrally in app/__init__.py via debug_utils
# Use debug_utils functions for consistent debugging patterns

def _format_age_group_breakdown(age_groups, fmt_number_func):
    """Format age group breakdown with better visual hierarchy and clearer labels."""
    def _format_age_group_label(age_group):
        """Convert age group codes to more readable labels."""
        age_group_mapping = {
            '_5': '>5',
            '5_17': '5-17',
            '18_49': '18-49',
            '50_': '50+',
            'unknown': 'Unknown',
            'male': 'Male',
            'female': 'Female',
            'total': 'Total'
        }
        return age_group_mapping.get(age_group, age_group.replace('_', '-'))

    # Filter out zero values and sort by a logical order
    non_zero_groups = [(age_group, count) for age_group, count in age_groups.items()
                      if count and count != 0]

    if not non_zero_groups:
        return "0"

    # Sort by a logical order: total first, then by age ranges
    def sort_key(item):
        age_group, _ = item
        if age_group == 'total':
            return (0, age_group)
        elif age_group == 'unknown':
            return (999, age_group)
        elif age_group == '_5':
            return (1, age_group)
        elif age_group == '5_17':
            return (2, age_group)
        elif age_group == '18_49':
            return (3, age_group)
        elif age_group == '50_':
            return (4, age_group)
        else:
            return (100, age_group)

    non_zero_groups.sort(key=sort_key)

    parts = []
    total = None
    for age_group, count in non_zero_groups:
        label = _format_age_group_label(age_group)
        formatted_count = fmt_number_func(count)
        if age_group == 'total':
            total = formatted_count
        else:
            parts.append(f"{label}: {formatted_count}")

    detail = ", ".join(parts)
    if total and detail:
        return f"{detail} → {total}"
    elif total:
        return total
    return detail

def _parse_field_value_for_display(value, data_not_available=None, not_applicable=None, form_item_id=None):
    """Parse field value to extract meaningful information for display in activity summaries."""
    # Handle data availability flags first
    if data_not_available:
        return "Data not available"
    if not_applicable:
        return "Not applicable"

    if value is None:
        return "N/A"

    # Helper for number formatting
    def _fmt_number(n):
        try:
            return f"{int(n):,}"
        except Exception as e:
            current_app.logger.debug("_fmt_number int failed for %r: %s", n, e)
            try:
                return f"{float(n):,}"
            except Exception as e:
                current_app.logger.debug("_fmt_number failed: %s", e)
                return str(n)

    # Helper to format matrix data with row/column labels
    def _format_matrix_data(matrix_dict, form_item_id):
        """Format matrix data using actual row/column labels from FormItem config."""
        if not form_item_id:
            return None

        try:
            from app.models import FormItem
            form_item = FormItem.query.get(form_item_id)
            if not form_item or form_item.item_type != 'matrix':
                return None

            # Get matrix config
            matrix_config = None
            if form_item.config and isinstance(form_item.config, dict):
                matrix_config = form_item.config.get('matrix_config')

            if not matrix_config or not isinstance(matrix_config, dict):
                return None

            # Get rows and columns
            rows = matrix_config.get('rows', [])
            columns = matrix_config.get('columns', [])

            # Helper to get label by index
            def get_row_label(index):
                """Get row label by 0-based index."""
                with suppress(ValueError, TypeError):
                    idx = int(index) - 1  # Convert from 1-based to 0-based
                    if 0 <= idx < len(rows):
                        row = rows[idx]
                        if isinstance(row, dict):
                            return row.get('label', f'Row {index}')
                        return str(row)
                return f'Row {index}'

            def get_column_label(index):
                """Get column label by 0-based index."""
                with suppress(ValueError, TypeError):
                    idx = int(index) - 1  # Convert from 1-based to 0-based
                    if 0 <= idx < len(columns):
                        col = columns[idx]
                        if isinstance(col, dict):
                            return col.get('label', f'Column {index}')
                        return str(col)
                return f'Column {index}'

            # Format matrix data
            parts = []
            for key, val in sorted(matrix_dict.items()):
                if val is None or val == 0:
                    continue
                # Parse key like "r1_c1" or "r2_c3"
                if key.startswith('r') and '_c' in key:
                    try:
                        row_num, col_num = key[1:].split('_c', 1)
                        row_label = get_row_label(row_num)
                        col_label = get_column_label(col_num)
                        parts.append(f"{row_label} × {col_label}: {_fmt_number(val)}")
                    except (ValueError, TypeError):
                        parts.append(f"{key.replace('_', ' ')}: {_fmt_number(val)}")
                else:
                    parts.append(f"{key.replace('_', ' ')}: {_fmt_number(val)}")

            if parts:
                return ", ".join(parts)
            return None
        except Exception as e:
            current_app.logger.debug(f"Error formatting matrix data: {e}")
            return None

    # If value is a string that looks like a dict, try to parse it
    if isinstance(value, str) and value.strip().startswith('{'):
        parsed = None
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            import ast
            try:
                parsed = ast.literal_eval(value.strip())
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, dict):
            value = parsed

    if isinstance(value, dict):
        # Special handling for trimmed matrix changes coming from activity logs
        if value.get('_matrix_change'):
            # Remove sentinel and format only the changed cells
            core_items = [(k, v) for k, v in value.items() if k != '_matrix_change']
            parts = []
            for k, v in core_items:
                if v is None:
                    continue
                # Some plugins store per-cell metadata like
                # {'original': '1', 'modified': '1', 'isModified': False}.
                # For display we only care about the effective value, not the metadata.
                effective_v = v
                if isinstance(v, dict) and ('modified' in v or 'original' in v):
                    effective_v = v.get('modified', v.get('original'))
                parts.append(f"{k}: {_fmt_number(effective_v)}")
            if parts:
                return ", ".join(parts)
            return ""

        # Check if this looks like matrix data (keys match r\d+_c\d+ pattern)
        if form_item_id:
            matrix_formatted = _format_matrix_data(value, form_item_id)
            if matrix_formatted:
                return matrix_formatted
        # Handle complex field structures
        if 'mode' in value and 'values' in value:
            # Handle disaggregation fields
            mode = value.get('mode', '')
            values = value.get('values', {})
            if mode == 'total' and values:
                # For total mode, extract the direct value
                if 'direct' in values:
                    return str(values['direct'])
                elif 'total' in values:
                    return str(values['total'])
                else:
                    # Return first available value
                    for k, v in values.items():
                        if v is not None:
                            return str(v)
            elif mode == 'disaggregated' and values:
                # Show first few disaggregated values
                items = list(values.items())[:3]  # Show first 3
                result = ", ".join([f"{k}: {v}" for k, v in items])
                if len(values) > 3:
                    result += f" (+{len(values) - 3} more)"
                return result
            else:
                return str(values)
        elif 'values' in value:
            # Handle other value structures
            return str(value['values'])
        else:
            # Try to delegate to plugins for better formatting - but only if we know the field type
            # This prevents plugin formatting from being applied to non-plugin fields
            with suppress(Exception):
                if hasattr(current_app, 'plugin_manager') and isinstance(value, dict):
                    # Only try plugin formatting if we have context about the field type
                    # This is a safety check to prevent plugin formatting on regular indicator fields
                    pass  # Skip plugin formatting for now - would need field context to implement properly
            # Handle simple dictionaries like {'direct': 89} for non-disaggregated fields
            if 'direct' in value and len(value) == 1:
                direct_value = value['direct']
                # Check if direct_value is a nested dictionary (age group breakdown)
                if isinstance(direct_value, dict):
                    # Format age group breakdown with better visual hierarchy
                    return _format_age_group_breakdown(direct_value, _fmt_number)
                else:
                    return str(direct_value)
            elif 'total' in value and len(value) == 1:
                total_value = value['total']
                # Check if total_value is a nested dictionary (age group breakdown)
                if isinstance(total_value, dict):
                    # Format age group breakdown with better visual hierarchy
                    return _format_age_group_breakdown(total_value, _fmt_number)
                else:
                    return str(total_value)
            # Handle flat maps like {'direct': 10, 'indirect': 20} or other category->number
            elif all(isinstance(v, (int, float, str, type(None))) for v in value.values()):
                preferred = ['total', 'direct', 'indirect']
                keys = list(value.keys())
                ordered = [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]
                parts = []
                for k in ordered:
                    v = value.get(k)
                    if v is None or v == 0:
                        continue
                    label = k.replace('_', ' ').title()
                    parts.append(f"{label}: {_fmt_number(v)}")
                if parts:
                    return ", ".join(parts)
            # Fallback
            return str(value)
    elif isinstance(value, str):
        return value
    else:
        return str(value)

def _extract_changed_matrix_values(old_value, new_value):
    """
    For matrix-style values stored as dicts,
    return trimmed mappings that contain only the entries whose values changed.

    This is used for activity summaries so that recent activities only show the
    cells that actually changed instead of the full matrix.
    """
    def _split_flat_matrix_entries(raw_text):
        """
        Split payloads like:
          "1 A: {'original': '', 'modified': '', 'isModified': False}, 1 B: 34,345, Table: national_society"
        into top-level "key: value" chunks while preserving commas inside values.
        """
        entries = []
        if not isinstance(raw_text, str):
            return entries

        text = raw_text.strip()
        if not text:
            return entries

        start = 0
        brace_depth = 0
        quote_char = None
        i = 0
        while i < len(text):
            ch = text[i]

            if quote_char:
                if ch == quote_char and (i == 0 or text[i - 1] != "\\"):
                    quote_char = None
                i += 1
                continue

            if ch in ("'", '"'):
                quote_char = ch
                i += 1
                continue

            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == "," and brace_depth == 0:
                rest = text[i + 1 :].lstrip()
                # Separator only when the next top-level token looks like "key: value".
                # This avoids splitting thousands separators (e.g. "34,345").
                if re.match(r"[^:,{}][^:{}]*:\s*", rest):
                    token = text[start:i].strip()
                    if token:
                        entries.append(token)
                    start = i + 1
            i += 1

        tail = text[start:].strip()
        if tail:
            entries.append(tail)
        return entries

    def _parse_flat_matrix_mapping(raw_text):
        """Parse flattened matrix payload text into a dictionary."""
        parsed = {}
        for entry in _split_flat_matrix_entries(raw_text):
            if ":" not in entry:
                continue
            key, raw_val = entry.split(":", 1)
            key = str(key).strip()
            if not key:
                continue
            val_text = str(raw_val).strip()
            if not val_text:
                parsed[key] = ""
                continue
            try:
                # Prefer json.loads for numbers and JSON structures; avoid ast.literal_eval
                stripped = val_text.strip()
                if stripped.startswith(('{', '[', '"')) or (stripped and stripped[0] in '-0123456789'):
                    parsed[key] = json.loads(val_text)
                else:
                    parsed[key] = val_text
            except (json.JSONDecodeError, ValueError):
                parsed[key] = val_text
        return parsed or None

    def _safe_parse_mapping(val):
        # Already a dict
        if isinstance(val, dict):
            return val
        # Try to parse string representations of dicts
        if isinstance(val, str):
            stripped = val.strip()
            if stripped.startswith('{'):
                try:
                    return json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    pass
                import ast
                try:
                    parsed = ast.literal_eval(stripped)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, SyntaxError):
                    return None
            # Some matrix plugins store a flat "key: value, key: value" payload.
            # Parse it so we can remove metadata-only entries from activity output.
            parsed_flat = _parse_flat_matrix_mapping(stripped)
            if isinstance(parsed_flat, dict):
                return parsed_flat
        return None

    old_map = _safe_parse_mapping(old_value)
    new_map = _safe_parse_mapping(new_value)

    # --- Case 1: matrix "cell diff" payloads (per-cell metadata) ---
    # Some matrix tables store deltas as a mapping of:
    #   "<row> <col>": { "original": "...", "modified": "...", "isModified": true/false }
    # This is what was showing up on the dashboard as raw metadata. Convert it into
    # a compact old/new mapping that includes ONLY changed cells, and mark it as
    # '_matrix_change' so the template uses render_matrix_change().
    def _looks_like_cell_delta(mapping):
        try:
            if not isinstance(mapping, dict) or not mapping:
                return False
            for k, v in mapping.items():
                if k == '_matrix_change' or (isinstance(k, str) and k.startswith('_')):
                    continue
                if isinstance(v, dict) and ('original' in v or 'modified' in v or 'isModified' in v):
                    return True
            return False
        except Exception as e:
            current_app.logger.debug("template helper failed: %s", e)
            return False

    def _normalize_cell_key(key):
        """
        Normalize keys like '109 Sp1' into '109_Sp1' so render_matrix_change can
        group by row and column.
        """
        try:
            k = str(key).strip()
            if '_' in k:
                return k
            if ' ' in k:
                a, b = k.split(' ', 1)
                a = a.strip()
                b = b.strip()
                if a and b:
                    return f"{a}_{b}"
            return k
        except Exception as e:
            current_app.logger.debug("_format_change_key failed: %s", e)
            return str(key)

    delta_map = None
    if isinstance(old_map, dict) and _looks_like_cell_delta(old_map):
        delta_map = old_map
    elif isinstance(new_map, dict) and _looks_like_cell_delta(new_map):
        delta_map = new_map

    if isinstance(delta_map, dict):
        trimmed_old = {'_matrix_change': True}
        trimmed_new = {'_matrix_change': True}

        keys_to_consider = set()
        if isinstance(old_map, dict):
            keys_to_consider.update(old_map.keys())
        if isinstance(new_map, dict):
            keys_to_consider.update(new_map.keys())

        for k in keys_to_consider:
            if k == '_matrix_change' or (isinstance(k, str) and k.startswith('_')):
                continue
            nk = _normalize_cell_key(k)
            old_entry = old_map.get(k) if isinstance(old_map, dict) else None
            new_entry = new_map.get(k) if isinstance(new_map, dict) else None

            # Metadata-style entries: {'original': ..., 'modified': ..., 'isModified': ...}
            if isinstance(old_entry, dict) or isinstance(new_entry, dict):
                meta = old_entry if isinstance(old_entry, dict) else new_entry
                if not isinstance(meta, dict):
                    continue

                # Prefer explicit flag; fall back to original/modified comparison
                try:
                    is_mod = bool(meta.get('isModified'))
                except Exception as e:
                    current_app.logger.debug("isModified parse failed: %s", e)
                    is_mod = False

                original = meta.get('original')
                modified = meta.get('modified')

                if not is_mod and 'original' in meta and 'modified' in meta and original != modified:
                    is_mod = True

                if not is_mod:
                    continue

                trimmed_old[nk] = original
                trimmed_new[nk] = modified
                continue

            # Scalar entries in the same payload are treated as regular changed cells.
            # This keeps meaningful values while excluding metadata-only rows above.
            if old_entry == new_entry:
                continue
            if old_entry in (None, "") and new_entry in (None, ""):
                continue

            trimmed_old[nk] = old_entry
            trimmed_new[nk] = new_entry

        # If nothing changed, don't override caller values
        if len(trimmed_old) <= 1 and len(trimmed_new) <= 1:
            return None, None

        return trimmed_old, trimmed_new

    def _looks_like_matrix_cell_map(mapping):
        """Heuristic for flattened matrix payloads: keys like '<rowId>_<column>'."""
        if not isinstance(mapping, dict) or not mapping:
            return False
        candidate_keys = []
        for k in mapping.keys():
            if not isinstance(k, str):
                continue
            if k.startswith('_'):
                continue
            candidate_keys.append(k)
        if not candidate_keys:
            return False
        return any('_' in k for k in candidate_keys)

    # --- Case 2: flattened matrix payloads ---
    if not isinstance(old_map, dict) or not isinstance(new_map, dict):
        return None, None
    if not (_looks_like_matrix_cell_map(old_map) and _looks_like_matrix_cell_map(new_map)):
        return None, None

    # Compute keys where the value actually changed
    changed_keys = {
        key
        for key in set(old_map.keys()) | set(new_map.keys())
        if not (isinstance(key, str) and key.startswith('_'))
        and old_map.get(key) != new_map.get(key)
    }

    if not changed_keys:
        # Nothing really changed – let callers fall back to the original values
        return None, None

    # Build trimmed dicts containing only the changed entries and mark them
    # so the display layer can format them appropriately.
    trimmed_old = {'_matrix_change': True}
    trimmed_old.update({k: old_map.get(k) for k in changed_keys if k in old_map})

    trimmed_new = {'_matrix_change': True}
    trimmed_new.update({k: new_map.get(k) for k in changed_keys if k in new_map})

    return trimmed_old, trimmed_new

def _normalize_value_for_summary_display(value):
    """Simplify verbose labels like 'Total: 123' to '123' for summaries."""
    try:
        if isinstance(value, str):
            parts = value.split(':', 1)
            if len(parts) == 2:
                label = parts[0].strip()
                candidate = parts[1].strip()
                # Strip thousands separators and validate numeric
                candidate_digits = candidate.replace(',', '').replace(' ', '')
                # Only drop the label when it's a generic text label (no digits/underscores),
                # so we keep matrix-style keys like "123_EFs" intact.
                if candidate_digits.isdigit() and not any(ch.isdigit() or ch == '_' for ch in label):
                    return candidate
        return value
    except Exception as e:
        current_app.logger.debug("_format_change_value failed: %s", e)
        return value

@bp.app_template_global()
def render_matrix_change(field_label, old_value, new_value, form_item_id=None):
    """
    Jinja helper to render matrix-style field changes in a grouped, human-friendly way.

    Output format (HTML, simplified):
        [Entity Name]:
        SP1: 0 → 1
        SP5: 1 → 0
    """
    from markupsafe import escape

    try:
        if not isinstance(old_value, dict) or not isinstance(new_value, dict):
            # Fallback to simple representation if values are not the expected dicts
            return f"{escape(field_label)}: {escape(str(new_value))}"

        # Work on shallow copies so we don't mutate the original params
        old_map = dict(old_value)
        new_map = dict(new_value)

        # Remove sentinel flag if present
        old_map.pop('_matrix_change', None)
        new_map.pop('_matrix_change', None)

        if not old_map and not new_map:
            return ""

        # Collect all keys that participate in the change
        all_keys = set(old_map.keys()) | set(new_map.keys())
        if not all_keys:
            return ""

        # Helper to unwrap plugin-style metadata dicts
        def _effective_cell_value(v):
            if isinstance(v, dict) and ('modified' in v or 'original' in v):
                return v.get('modified', v.get('original'))
            return v

        # Group changes by entity (row) code
        rows = {}
        for key in sorted(all_keys):
            if key is None:
                continue
            key_str = str(key)
            if '_' in key_str:
                row_code, col_label = key_str.split('_', 1)
            else:
                row_code, col_label = key_str, ''

            old_v = _effective_cell_value(old_map.get(key))
            new_v = _effective_cell_value(new_map.get(key))

            # Skip if nothing actually changed (defensive; normally trimmed already)
            if old_v == new_v:
                continue

            rows.setdefault(row_code, []).append((col_label, old_v, new_v))

        if not rows:
            return ""

        # Resolve entity names where possible (e.g. national society id -> NS name)
        html_parts = [f"{escape(field_label)}:<br>"]

        for row_code in sorted(rows.keys(), key=lambda rc: (not str(rc).isdigit(), int(rc) if str(rc).isdigit() else str(rc))):
            entity_label = str(row_code)
            try:
                if str(row_code).isdigit():
                    country = Country.query.get(int(row_code))
                    if country:
                        # Use localized NS name when available
                        entity_label = _get_localized_national_society_name(country)
            except Exception as e:
                current_app.logger.debug("entity label lookup failed: %s", e)
                entity_label = str(row_code)

            html_parts.append(f"<span class='font-semibold'>{escape(entity_label)}</span>:<br>")

            # Sort columns for consistent ordering
            for col_label, old_v, new_v in sorted(rows[row_code], key=lambda item: str(item[0])):
                col_label_str = str(col_label).strip()

                # Treat missing/None values as 0 for typical binary/numeric matrices,
                # so we show "0 → 1" instead of "→ 1" when a checkbox is newly ticked.
                def _is_binary_like(v):
                    return v in (0, 1, "0", "1", True, False)

                if (old_v is None or old_v == "") and _is_binary_like(new_v):
                    old_disp = "0"
                else:
                    old_disp = "" if old_v is None else str(old_v)

                if (new_v is None or new_v == "") and _is_binary_like(old_v):
                    new_disp = "0"
                else:
                    new_disp = "" if new_v is None else str(new_v)

                if not old_disp and new_disp:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(new_disp)}<br>"
                    )
                elif old_disp and not new_disp:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(old_disp)} &rarr; <em>removed</em><br>"
                    )
                else:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(old_disp)} &rarr; {escape(new_disp)}<br>"
                    )

        return "".join(html_parts)
    except Exception as e:
        current_app.logger.error(f"Error rendering matrix change summary: {e}", exc_info=True)
        # Safe fallback – show the new value in a basic way
        try:
            return f"{escape(field_label)}: {escape(str(new_value))}"
        except Exception as e:
            current_app.logger.debug("format_change_display failed: %s", e)
            return ""

def _get_localized_indicator_bank_name_by_id(indicator_bank_id, fallback_name=None):
    """Resolve localized indicator name by IndicatorBank id (for dynamic indicator activities)."""
    if not indicator_bank_id:
        return fallback_name or "Unknown Indicator"
    try:
        from app.models import IndicatorBank
        from app.utils.form_localization import get_localized_indicator_name
        indicator = IndicatorBank.query.get(indicator_bank_id)
        if not indicator:
            return fallback_name or "Deleted Indicator"
        return get_localized_indicator_name(indicator) or fallback_name or indicator.name
    except Exception as e:
        current_app.logger.error(f"Error getting localized indicator bank name for ID {indicator_bank_id}: {e}")
        return fallback_name or "Unknown Indicator"


def get_localized_field_name_by_id(form_item_id, fallback_name=None):
    """Get localized field name by FormItem id for activity display."""
    if not form_item_id:
        current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: No form_item_id provided, returning fallback: {fallback_name}")
        return fallback_name or "Unknown Field"

    try:
        from app.models import FormItem
        from flask_babel import get_locale
        from app.utils.form_localization import get_translation_key, get_localized_indicator_name
        import json

        # ISO locale code for JSON translations
        translation_key = get_translation_key()  # ISO (e.g., 'fr')
        locale_code = (str(get_locale()) if get_locale() else 'en').split('_', 1)[0]
        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: form_item_id={form_item_id}, translation_key={translation_key}, locale_code={locale_code}, fallback_name={fallback_name}"
        )

        form_item = FormItem.query.get(form_item_id)
        if not form_item:
            current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: FormItem {form_item_id} not found, using fallback")
            return fallback_name or "Deleted Field"

        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: FormItem found - is_indicator={form_item.is_indicator}, label='{form_item.label}', item_type='{form_item.item_type}'"
        )

        # For indicators with indicator_bank, use the proper localization function
        if form_item.is_indicator and form_item.indicator_bank:
            current_app.logger.debug(
                f"DEBUG get_localized_field_name_by_id: Using indicator_bank localization for indicator_bank_id={form_item.indicator_bank_id}"
            )
            localized_name = get_localized_indicator_name(form_item.indicator_bank)
            current_app.logger.debug(
                f"DEBUG get_localized_field_name_by_id: indicator_bank localized name='{localized_name}'"
            )
            return localized_name

        # For other item types, read label_translations directly
        raw_trans = getattr(form_item, 'label_translations', None)
        translations_dict = {}
        if isinstance(raw_trans, dict):
            translations_dict = raw_trans
        elif isinstance(raw_trans, str):
            try:
                translations_dict = json.loads(raw_trans) or {}
            except json.JSONDecodeError:
                translations_dict = {}

        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: label_translations keys={list(translations_dict.keys()) if translations_dict else []}"
        )

        if translations_dict:
            # Try keys in order of preference
            for key in [locale_code, translation_key, 'en']:
                val = translations_dict.get(key)
                if isinstance(val, str) and val.strip():
                    current_app.logger.debug(
                        f"DEBUG get_localized_field_name_by_id: Using translation for key '{key}': '{val}'"
                    )
                    return val
        else:
            current_app.logger.debug("DEBUG get_localized_field_name_by_id: No label_translations available")

        # Fallback to default label or provided fallback
        result = fallback_name or form_item.label
        current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: Using fallback result='{result}'")
        return result

    except Exception as e:
        current_app.logger.error(f"Error getting localized field name for ID {form_item_id}: {e}")
        return fallback_name or "Unknown Field"

@bp.app_template_global()
def localized_field_name(field_id, fallback_name=None, field_id_kind=None, assignment_id=None):
    """Jinja helper to resolve localized field names in templates.

    Handles both:
    - FormItem ids (normal sections)
    - IndicatorBank ids (dynamic indicator sections), where the UI uses the IndicatorBank id
      as the DOM field id/anchor ("field-<id>").

    If field_id_kind is not provided, we try to disambiguate using assignment_id (when available).
    """
    try:
        if not field_id:
            return fallback_name or ""

        kind = (str(field_id_kind).lower().strip() if field_id_kind is not None else "")
        if kind in ("indicator_bank", "indicatorbank", "indicator_bank_id"):
            return _get_localized_indicator_bank_name_by_id(field_id, fallback_name=fallback_name)
        if kind in ("form_item", "formitem", "form_item_id"):
            return get_localized_field_name_by_id(field_id, fallback_name)

        # No explicit kind: disambiguate using assignment/template when possible.
        if assignment_id:
            with suppress(Exception):
                from app.models import AssignmentEntityStatus, FormItem
                aes = AssignmentEntityStatus.query.get(assignment_id)
                assigned_template_id = (
                    aes.assigned_form.template_id
                    if aes and getattr(aes, "assigned_form", None)
                    else None
                )
                if assigned_template_id:
                    fi = FormItem.query.get(field_id)
                    # If the FormItem exists but belongs to a different template, treat this id as an IndicatorBank id.
                    if not fi or (getattr(fi, "template_id", None) not in (None, assigned_template_id)):
                        return _get_localized_indicator_bank_name_by_id(field_id, fallback_name=fallback_name)

        # Default: treat as FormItem id
        return get_localized_field_name_by_id(field_id, fallback_name)
    except Exception as e:
        current_app.logger.debug("get_localized_field_name failed: %s", e)
        return fallback_name or ""

# EntityService is now registered as a template global in app/__init__.py

@bp.app_template_global()
def format_activity_value(value, form_item_id=None, compare_value=None):
    """Format activity values (including disaggregations) for template display.

    If compare_value is provided, returns formatted value only if it differs from compare_value.
    Returns empty string if values are the same.

    SECURITY: Output is HTML-escaped since templates use |safe filter on this function.
    """
    from markupsafe import escape as html_escape

    try:
        formatted_value = _normalize_value_for_summary_display(_parse_field_value_for_display(value, form_item_id=form_item_id))

        # If compare_value is provided, compare the formatted values
        if compare_value is not None:
            with suppress(Exception):
                formatted_compare = _normalize_value_for_summary_display(_parse_field_value_for_display(compare_value, form_item_id=form_item_id))
                # If values are the same, return empty string
                if formatted_value == formatted_compare:
                    return ""

        # SECURITY: Escape HTML to prevent XSS when used with |safe filter
        return html_escape(str(formatted_value)) if formatted_value else ""
    except Exception as e:
        current_app.logger.debug("format_answer_value failed: %s", e)
        try:
            formatted_value = str(value)
            # If compare_value is provided, compare
            if compare_value is not None:
                with suppress(Exception):
                    formatted_compare = str(compare_value)
                    if formatted_value == formatted_compare:
                        return ""
            # SECURITY: Escape HTML to prevent XSS when used with |safe filter
            return html_escape(formatted_value)
        except Exception as e2:
            current_app.logger.debug("format_answer_value fallback failed: %s", e2)
            return ""

@bp.app_template_global()
def get_localized_template_name(template):
    """Jinja helper to get localized template name in templates."""
    try:
        return _get_localized_template_name(template)
    except Exception as e:
        current_app.logger.debug("get_template_name failed: %s", e)
        return template.name if template else _("Unknown Template")

@bp.app_template_global()
def localize_status(status):
    """Jinja helper to localize assignment status strings."""
    if not status:
        return status

    status_lower = status.lower().strip()

    # Map status values to translation keys
    status_map = {
        'pending': _('Pending'),
        'in progress': _('In Progress'),
        'submitted': _('Submitted'),
        'approved': _('Approved'),
        'requires revision': _('Requires Revision'),
        'closed': _('Closed'),
    }

    return status_map.get(status_lower, status)

@bp.app_template_global()
def get_localized_national_society_name(country):
    """Jinja helper to get localized National Society name in templates."""
    try:
        return _get_localized_national_society_name(country)
    except Exception as e:
        current_app.logger.debug("get_national_society_name failed: %s", e)
        return country.name if country else _("Unknown")

@bp.app_template_global()
def render_activity_summary(activity):
    from flask_babel import _ as babel_
    from flask_babel import ngettext as babel_ngettext
    from flask_babel import get_locale

    current_locale = str(get_locale()) if get_locale() else 'en'
    current_app.logger.debug(f"DEBUG render_activity_summary: Starting render, current_locale={current_locale}")

    # Extract context
    ctx = {}
    try:
        raw = getattr(activity, 'summary_params', None)
        if isinstance(raw, dict):
            params = raw.copy()  # Make a copy to avoid modifying original
        else:
            params = {}
    except Exception as e:
        current_app.logger.debug("params parse failed: %s", e)
        params = {}

    key = getattr(activity, 'summary_key', None)
    current_app.logger.debug(f"DEBUG render_activity_summary: key='{key}', params={params}")

    # Get field_id for matrix formatting
    field_id = params.get('field_id')

    # Parse complex field values for better display
    if 'old' in params:
        params['old'] = _normalize_value_for_summary_display(_parse_field_value_for_display(params['old'], form_item_id=field_id))
    if 'new' in params:
        params['new'] = _normalize_value_for_summary_display(_parse_field_value_for_display(params['new'], form_item_id=field_id))

    # Get localized field name for single field updates
    if 'field_id' in params and 'field' in params:
        current_app.logger.debug(f"DEBUG render_activity_summary: Before localization - field_id={params['field_id']}, field='{params['field']}'")
        localized_name = localized_field_name(
            params.get('field_id'),
            fallback_name=params.get('field'),
            field_id_kind=params.get('field_id_kind'),
            assignment_id=getattr(activity, 'assignment_id', None)
        )
        current_app.logger.debug(f"DEBUG render_activity_summary: After localization - localized_field_name='{localized_name}'")
        params['field'] = localized_name

    # Determine specialized formatting for data change activities
    change_type = (params.get('change_type') or 'updated').lower()

    if key == 'activity.form_data_updated.single':
        # Neutral text without the verb; verb shown as a colored badge in the template
        if change_type == 'added':
            template_str = babel_("%(field)s: %(new)s")
        elif change_type == 'removed':
            template_str = babel_("%(field)s: %(old)s")
        else:
            template_str = babel_("%(field)s: %(old)s → %(new)s")
        try:
            result = template_str % params
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{result}'")
            return result
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting single-change message: {e}")
            return template_str

    if key == 'activity.form_data_updated.multiple':
        # Simplified approach - just use the dominant change type
        # IMPORTANT: pluralization must be handled via ngettext so languages like Arabic
        # don't end up with "حقلs" (appending English 's').
        try:
            count = int(params.get('count') or 0)
        except Exception as e:
            current_app.logger.debug("count parse failed: %s", e)
            count = 0
        params['count'] = count
        # Template name used in the summary text
        template_name = params.get('template', '')

        if change_type == 'added':
            template_str = babel_ngettext(
                "Added %(count)d field in %(template)s",
                "Added %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )
        elif change_type == 'removed':
            template_str = babel_ngettext(
                "Removed %(count)d field in %(template)s",
                "Removed %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )
        else:
            template_str = babel_ngettext(
                "Updated %(count)d field in %(template)s",
                "Updated %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )

        try:
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{template_str}'")
            return template_str
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting multi-change message: {e}")
            return template_str

    messages = {
        'activity.assignment_created': babel_("Assignment created: %(template)s"),
        'activity.assignment_submitted': babel_("Assignment submitted: %(template)s"),
        'activity.assignment_approved': babel_("Assignment approved: %(template)s"),
        'activity.assignment_reopened': babel_("Assignment reopened: %(template)s"),
        'activity.document_uploaded': babel_("Document uploaded: %(document)s"),
        'activity.self_report_created': babel_("Self-report created: %(template)s"),
        'activity.audit_user_activity': babel_("User %(action)s"),
        'activity.audit_admin_action': babel_("Admin %(action)s %(target)s"),
        'activity.legacy_removed': babel_("Activity")
    }

    if key in messages:
        try:
            result = messages[key] % params
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{result}'")
            return result
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting message: {e}")
            return messages[key]

    current_app.logger.debug(f"DEBUG render_activity_summary: No message found for key '{key}', returning empty string")
    return ""



# Language switching route
@bp.route('/language/<language>')
def set_language(language):
    """Set the language for the current session"""
    from app.utils.redirect_utils import is_safe_redirect_url
    supported = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES)
    if language in (supported or []):
        session['language'] = language
    # SECURITY: Validate referrer to prevent open redirect attacks
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        return redirect(referrer)
    return redirect(url_for('main.dashboard'))

# Translation reload route (for development)
@bp.route('/reload-translations')
def reload_translations():
    """Manually reload translations (development only)"""
    from app.utils.redirect_utils import is_safe_redirect_url
    if current_app.config.get('DEBUG', False):
        from flask_babel import refresh
        try:
            refresh()
            flash(_("Translations reloaded successfully!"), "success")
        except Exception as e:
            flash(_("An error occurred. Please try again."), "danger")
    else:
        flash(_("Translation reloading is only available in development mode."), "warning")
    # SECURITY: Validate referrer to prevent open redirect attacks
    referrer = request.referrer
    if referrer and is_safe_redirect_url(referrer):
        return redirect(referrer)
    return redirect(url_for('main.dashboard'))


@bp.route("/chat", methods=["GET"], defaults={"conversation_id": None})
@bp.route("/chat/<uuid:conversation_id>", methods=["GET"])
@login_required
def chat_immersive(conversation_id=None):
    """Full-page immersive chat view (ChatGPT-style). Requires chatbot enabled.
    URL /chat for new chat, /chat/<uuid> to open a specific conversation."""
    if not current_app.config.get("CHATBOT_ENABLED", True):
        flash(_("Chat is not available."), "warning")
        return redirect(url_for("main.dashboard"))
    if not getattr(current_user, "chatbot_enabled", True):
        flash(_("Chat is disabled for your account."), "warning")
        return redirect(url_for("main.dashboard"))
    if not user_has_ai_beta_access(current_user):
        flash(_("AI is currently in beta and available only to selected users."), "warning")
        return redirect(url_for("main.dashboard"))
    try:
        from app.utils.app_settings import get_chatbot_org_only, is_organization_email
        if get_chatbot_org_only() and not is_organization_email(getattr(current_user, "email", "")):
            flash(_("Chat is only available to organization users."), "warning")
            return redirect(url_for("main.dashboard"))
    except Exception:
        pass
    websocket_enabled = bool(current_app.config.get("WEBSOCKET_ENABLED", True))
    try:
        from app.utils.app_settings import get_chatbot_name
        chatbot_name = get_chatbot_name(default="")
    except Exception as e:
        current_app.logger.debug("get_chatbot_name failed: %s", e)
        chatbot_name = ""
    return render_template(
        "core/chat_immersive.html",
        title=(chatbot_name if chatbot_name else _("AI Assistant")),
        initial_conversation_id=str(conversation_id) if conversation_id else None,
        websocket_enabled=websocket_enabled,
    )


@bp.route("/", methods=["GET", "POST"])
@login_required
def dashboard():
    """
    Main dashboard page for logged-in users.
    Displays a welcome message, allows entity selection (countries, branches, departments, etc.),
    and lists assigned forms for the selected entity with their completion rates, including data
    from public forms, combined in the assignments section.
    Also allows users to self-assign templates marked for self-reporting.
    """
    # Get user entities (all entity types user has access to)
    user_entities = []
    user_countries = []

    # RBAC-only: entities are derived from explicit entity permissions, with a fallback
    # for users that have none configured yet (e.g. system managers).
    entity_permissions = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
    if entity_permissions:
        for perm in entity_permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                user_entities.append({
                    'entity_type': perm.entity_type,
                    'entity_id': perm.entity_id,
                    'entity': entity
                })
    else:
        all_entities = EntityService.get_entities_for_user(current_user)
        for entity in all_entities:
            entity_type = None
            if isinstance(entity, Country):
                entity_type = EntityType.country.value
            else:
                for et, model_class in EntityService.ENTITY_MODEL_MAP.items():
                    if isinstance(entity, model_class):
                        entity_type = et
                        break
            if entity_type:
                entity_id = getattr(entity, 'id', None)
                if entity_id:
                    user_entities.append({
                        'entity_type': entity_type,
                        'entity_id': entity_id,
                        'entity': entity
                    })

    enabled_entity_groups = get_enabled_entity_groups()
    allowed_entity_types = get_allowed_entity_type_codes(enabled_entity_groups)
    if allowed_entity_types:
        user_entities = [
            entity for entity in user_entities
            if entity['entity_type'] in allowed_entity_types
        ]
    else:
        user_entities = []

    user_countries = [
        e['entity'] for e in user_entities
        if e['entity_type'] == EntityType.country.value and isinstance(e['entity'], Country)
    ]
    countries_group_enabled = 'countries' in enabled_entity_groups

    selected_entity = None
    selected_entity_type = None
    selected_entity_id = None
    selected_country = None  # For backward compatibility
    # assigned_forms will now be a list of AssignmentEntityStatus objects
    assigned_forms_statuses = []
    # NEW: List to hold assignment statuses with calculated completion rates
    assigned_forms_with_completion = []
    # NEW: List to hold public form assignments with completion rates (now using AssignedForm)
    public_assignments_with_completion = []
    # NEW: List of templates available for self-reporting
    self_report_templates = []

    # NEW: Combined list for display
    all_forms_for_display = []
    # NEW: Separate lists for current and past assignments
    current_assignments = []
    past_assignments = []

    # NEW: Dictionary to hold public submissions grouped by assigned_form_id
    public_submissions_by_assignment = {}

    # NEW: Instantiate DeleteForm for CSRF protection on delete actions
    delete_form = DeleteForm()
    # NEW: Instantiate ReopenAssignmentForm for CSRF protection on reopen action
    reopen_form = ReopenAssignmentForm()
    # NEW: Instantiate ApproveAssignmentForm for CSRF protection on approve action
    approve_form = ApproveAssignmentForm()
    # NEW: Instantiate RequestCountryAccessForm for country access requests
    request_access_form = RequestCountryAccessForm(user_id=current_user.id)
    can_request_multiple_countries = is_organization_email(getattr(current_user, "email", ""))

    show_country_select = False
    show_entity_select = False
    current_date = utcnow().date()
    # NEW: Initialize focal points lists
    ns_focal_points = []
    org_focal_points = []

    current_app.logger.debug(f"User {current_user.email} accessed dashboard.")
    current_app.logger.debug(f"User has {len(user_entities)} entities assigned")
    current_app.logger.debug(f"Initial session[{SELECTED_ENTITY_TYPE_SESSION_KEY}]: {session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)}")
    current_app.logger.debug(f"Initial session[{SELECTED_ENTITY_ID_SESSION_KEY}]: {session.get(SELECTED_ENTITY_ID_SESSION_KEY)}")

    # Load access requests so users with existing access can still track pending ones
    pending_access_requests = []
    all_access_requests = []
    non_org_has_counting_request = False
    try:
        all_access_requests = (
            CountryAccessRequest.query.filter_by(user_id=current_user.id)
            .options(joinedload(CountryAccessRequest.country))
            .order_by(CountryAccessRequest.created_at.desc())
            .all()
        )

        # Check if approved requests still have access (may have been revoked by admin)
        for req in all_access_requests:
            if not req.country and req.country_id:
                req.country = Country.query.get(req.country_id)

            # For approved requests, check if user still has access
            if req.status == CountryAccessRequestStatus.APPROVED and req.country_id:
                # Check if user still has entity permission for this country
                has_access = current_user.has_entity_access(EntityType.country.value, req.country_id)
                # Add a computed attribute to indicate if access was revoked
                req._access_revoked = not has_access
            else:
                req._access_revoked = False

        pending_access_requests = [
            req for req in all_access_requests if req.status == CountryAccessRequestStatus.PENDING
        ]
        # For non-org users: only PENDING or APPROVED (with access still active) count toward the one-request limit; rejected/revoked do not
        non_org_has_counting_request = False
        if not can_request_multiple_countries:
            for req in all_access_requests:
                if req.status == CountryAccessRequestStatus.PENDING:
                    non_org_has_counting_request = True
                    break
                if req.status == CountryAccessRequestStatus.APPROVED and not getattr(req, '_access_revoked', True):
                    non_org_has_counting_request = True
                    break
    except Exception as access_error:
        current_app.logger.error(f"Failed to load country access requests for {current_user.email}: {access_error}", exc_info=True)
        all_access_requests = []
        pending_access_requests = []
        non_org_has_counting_request = False

    if not user_entities:
        if len(pending_access_requests) == 0:
            flash(_("Your user account is not associated with any enabled entities. Please contact an administrator."), "warning")
        current_app.logger.warning(f"User {current_user.email} has no enabled entities assigned.")
        # selected_country remains None, which will hide entity-specific sections
    else:
        # User has one or more countries
        if countries_group_enabled and len(user_countries) > 1:
            # Show country selection dropdown if user has multiple countries
            show_country_select = True
            current_app.logger.debug(f"User {current_user.email} has multiple countries, showing country select.")

        # Show entity selection dropdown if user has multiple entities (any type)
        if len(user_entities) > 1:
            show_entity_select = True

        if request.method == "POST":
            # Check if the POST is for country selection
            if countries_group_enabled and 'country_select' in request.form:
                selected_country_id_str = request.form.get('country_select')
                current_app.logger.debug(f"Dashboard POST request: Country Selection. Selected country ID string from form: {selected_country_id_str}")
                if selected_country_id_str:
                    try:
                        selected_country_id = int(selected_country_id_str)
                        temp_selected_country = Country.query.get(selected_country_id)
                        # Validate that the selected country is one of the user's assigned countries
                        if temp_selected_country and temp_selected_country in user_countries:
                            session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_country_id
                            selected_country = temp_selected_country
                            current_app.logger.debug(f"User {current_user.email} selected valid country {selected_country.name} (ID: {selected_country.id}) via POST. Session updated.")
                        else:
                            # Invalid country selected, clear session and flash message
                            session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                            selected_country = None # Will be set to a default below
                            flash(_("Invalid country selection or country not assigned to you."), "warning")
                            current_app.logger.warning(f"User {current_user.email} submitted invalid country ID {selected_country_id_str} via POST.")
                    except ValueError:
                        # Invalid ID format, clear session and flash message
                        session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                        selected_country = None # Will be set to a default below
                        flash(_("Invalid country ID format."), "warning")
                        current_app.logger.error(f"User {current_user.email} submitted non-integer country ID '{selected_country_id_str}' via POST.")
                else:
                     # No country selected in the form, clear session (will default below)
                     session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                     selected_country = None # Will be set to a default below
                     current_app.logger.warning(f"User {current_user.email} submitted POST without a country selection.")

            # NEW: Handle POST for entity selection (multi-entity support)
            elif 'entity_select' in request.form:
                entity_select_value = request.form.get('entity_select', '')
                current_app.logger.debug(f"Dashboard POST request: Entity Selection. Raw value: '{entity_select_value}'")
                if entity_select_value and ':' in entity_select_value:
                    try:
                        selected_type, selected_id_str = entity_select_value.split(':', 1)
                        selected_id = int(selected_id_str)

                        # Validate that the selected entity is one of the user's accessible entities
                        user_entity_pairs = {(e['entity_type'], e['entity_id']) for e in user_entities}
                        if (selected_type, selected_id) in user_entity_pairs or current_user.has_entity_access(selected_type, selected_id):
                            session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_type
                            session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_id

                            # Set legacy country session for compatibility
                            with suppress(Exception):
                                related_country = EntityService.get_country_for_entity(selected_type, selected_id)
                                if related_country:
                                    session[SELECTED_COUNTRY_ID_SESSION_KEY] = related_country.id

                            current_app.logger.debug(f"User {current_user.email} selected entity {selected_type}:{selected_id} via POST. Session updated.")
                        else:
                            session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                            session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                            flash(_("Invalid entity selection or entity not assigned to you."), "warning")
                            current_app.logger.warning(f"User {current_user.email} submitted invalid entity selection '{entity_select_value}'.")
                    except ValueError:
                        flash(_("Invalid entity ID format."), "warning")
                        current_app.logger.error(f"User {current_user.email} submitted non-integer entity ID in '{entity_select_value}'.")
                else:
                    flash(_("Invalid entity selection."), "warning")
                    current_app.logger.warning(f"User {current_user.email} submitted POST with missing or malformed entity_select value.")

            # NEW: Handle POST for self-reporting template selection
            elif countries_group_enabled and 'self_report_template_id' in request.form and SELECTED_COUNTRY_ID_SESSION_KEY in session:
                 selected_template_id_str = request.form.get('self_report_template_id')
                 selected_country_id_from_session = session[SELECTED_COUNTRY_ID_SESSION_KEY]
                 selected_country = Country.query.get(selected_country_id_from_session)

                 current_app.logger.debug(f"Dashboard POST request: Self-Report. Template ID string: {selected_template_id_str}, Selected Country ID from session: {selected_country_id_from_session}")


                 if selected_template_id_str and selected_country:
                     try:
                         selected_template_id = int(selected_template_id_str)
                         # Check if template is enabled for self-report via published version
                         template_to_assign = FormTemplate.query.join(
                             FormTemplateVersion,
                             and_(
                                 FormTemplate.id == FormTemplateVersion.template_id,
                                 FormTemplateVersion.status == 'published'
                             )
                         ).filter(
                             FormTemplate.id == selected_template_id,
                             FormTemplateVersion.add_to_self_report == True
                         ).first()

                         if template_to_assign and selected_country in user_countries:
                             # Check if an assignment for this template and country already exists for the self-report period
                             # REMOVED: This check is removed to allow multiple self-reported assignments of the same template
                             # existing_acs = AssignmentEntityStatus.query.filter(
                             #     AssignmentEntityStatus.entity_id == selected_country.id,
                             #     AssignmentEntityStatus.entity_type == 'country',
                             #     AssignmentEntityStatus.assigned_form.has(
                             #         and_(
                             #             AssignedForm.template_id == template_to_assign.id,
                             #             AssignedForm.period_name == SELF_REPORT_PERIOD_NAME
                             #         )
                             #     )
                             # ).first()

                             # if existing_acs:
                             #     flash(f"Template '{template_to_assign.name}' is already assigned to {selected_country.name} for self-reporting.", "warning")
                             #     current_app.logger.info(f"Duplicate self-report assignment attempt for template {template_to_assign.id} and country {selected_country.id}.")
                             # else:
                                 # Find or create the AssignedForm for this template and the self-report period
                                 # We will create a new AssignedForm record each time for self-reported templates
                                 # to allow multiple instances, rather than reusing a single AssignedForm.
                                 # This simplifies tracking individual self-reported submissions.
                                 assigned_form = AssignedForm(
                                     template_id=template_to_assign.id,
                                     period_name=SELF_REPORT_PERIOD_NAME,
                                     assigned_at=utcnow() # Use current time for uniqueness
                                 )
                                 db.session.add(assigned_form)
                                 db.session.flush() # Flush to get the assigned_form.id
                                 current_app.logger.debug(f"Created new AssignedForm ID {assigned_form.id} for self-report period for template {template_to_assign.id}.")

                                 # Create the new AssignmentEntityStatus entry
                                 new_acs = AssignmentEntityStatus(
                                     assigned_form_id=assigned_form.id,
                                     entity_type='country',
                                     entity_id=selected_country.id,
                                     status='Pending', # Default status
                                     due_date=None # No default due date for self-reported forms
                                 )
                                 db.session.add(new_acs)

                                 # Country assignment is handled by the AssignmentEntityStatus creation above
                                 # No need for separate countries.append() since new_acs already links the country
                                 current_app.logger.debug(f"Country {selected_country.id} linked to AssignedForm {assigned_form.id} via AssignmentEntityStatus {new_acs.id}.")


                                 try:
                                     db.session.flush()

                                     # Send notification about self-report creation
                                     try:
                                         from app.utils.notifications import notify_self_report_created
                                         notify_self_report_created(new_acs)
                                     except Exception as e:
                                         current_app.logger.error(f"Error sending self-report created notification: {e}", exc_info=True)
                                         # Don't fail the self-report creation if notification fails

                                     flash(_("Template '%(template)s' has been added to your assignments for %(country)s.", template=template_to_assign.name, country=selected_country.name), "success")
                                     current_app.logger.debug(f"Successfully created self-report AssignmentEntityStatus ID {new_acs.id}.")
                                 except Exception as e:
                                     request_transaction_rollback()
                                     flash(_("An error occurred. Please try again."), "danger")
                                     current_app.logger.error(f"Error during DB commit for self-report assignment: {e}", exc_info=True)

                         else:
                              flash(_("Invalid template selection or country not assigned to you."), "warning")
                              current_app.logger.warning(f"User {current_user.email} submitted invalid self-report template ID {selected_template_id_str} or country {selected_country_id_from_session} is not assigned.")

                     except ValueError:
                          flash(_("Invalid template ID format."), "warning")
                          current_app.logger.error(f"User {current_user.email} submitted non-integer self-report template ID '{selected_template_id_str}'.")
                 else:
                      flash(_("Please select a template to self-report."), "warning")
                      current_app.logger.warning(f"User {current_user.email} submitted self-report POST without template selection or selected country is missing.")

            # After handling either country selection or self-report, redirect to GET to show updated state
            return redirect(url_for("main.dashboard"))


                                 # If it's a GET request or POST handling didn't redirect, determine the selected entity
        # Check for entity selection in session (new multi-entity system)
        if SELECTED_ENTITY_TYPE_SESSION_KEY in session and SELECTED_ENTITY_ID_SESSION_KEY in session:
            retrieved_entity_type = session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)
            retrieved_entity_id = session.get(SELECTED_ENTITY_ID_SESSION_KEY)
            current_app.logger.debug(f"Found entity {retrieved_entity_type}:{retrieved_entity_id} in session.")
            temp_entity = EntityService.get_entity(retrieved_entity_type, retrieved_entity_id)
            # Validate that the entity in session is still accessible to the user
            if temp_entity and retrieved_entity_type in allowed_entity_types:
                if current_user.has_entity_access(retrieved_entity_type, retrieved_entity_id):
                    selected_entity_type = retrieved_entity_type
                    selected_entity_id = retrieved_entity_id
                    selected_entity = temp_entity
                    # Set selected_country for backward compatibility if it's a country
                    if retrieved_entity_type == EntityType.country.value:
                        selected_country = temp_entity
                        session[SELECTED_COUNTRY_ID_SESSION_KEY] = retrieved_entity_id  # Backward compatibility
                    current_app.logger.debug(f"Using entity {retrieved_entity_type}:{retrieved_entity_id} from session.")
                else:
                    # Entity in session is not valid for the user, clear session
                    session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                    session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                    current_app.logger.warning(f"Entity {retrieved_entity_type}:{retrieved_entity_id} from session is no longer valid for user {current_user.email}. Clearing session.")
            else:
                session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
                current_app.logger.warning(f"Entity {retrieved_entity_type}:{retrieved_entity_id} from session is not enabled or no longer available for user {current_user.email}. Clearing session.")

        # Legacy: Check for country selection in session (backward compatibility)
        elif countries_group_enabled and SELECTED_COUNTRY_ID_SESSION_KEY in session:
            retrieved_country_id = session[SELECTED_COUNTRY_ID_SESSION_KEY]
            current_app.logger.debug(f"Found country ID {retrieved_country_id} in session (legacy).")
            temp_selected_country = Country.query.get(retrieved_country_id)
            # Validate that the country in session is still assigned to the user
            if temp_selected_country:
                user_country_ids = [c.id for c in user_countries] if user_countries else []
                if temp_selected_country.id in user_country_ids or current_user.has_entity_access(EntityType.country.value, temp_selected_country.id):
                    selected_country = temp_selected_country
                    selected_entity_type = EntityType.country.value
                    selected_entity_id = temp_selected_country.id
                    selected_entity = temp_selected_country
                    session[SELECTED_ENTITY_TYPE_SESSION_KEY] = EntityType.country.value
                    session[SELECTED_ENTITY_ID_SESSION_KEY] = temp_selected_country.id
                    current_app.logger.debug(f"Using country {selected_country.name} (ID: {selected_country.id}) from session.")
                else:
                    session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)
                    current_app.logger.warning(f"Country ID {retrieved_country_id} from session is no longer valid for user {current_user.email}. Clearing session.")

        # If selected_entity is still None, default to first entity (alphabetically sorted)
        if selected_entity is None and user_entities:
            # Sort entities alphabetically by display name before selecting the first one
            def get_sort_key(e):
                display_name = EntityService.get_entity_name(
                    e['entity_type'],
                    e['entity_id'],
                    include_hierarchy=True
                )
                return (display_name or '').lower()

            sorted_entities = sorted(user_entities, key=get_sort_key)
            # Default to the first entity in the alphabetically sorted list
            first_entity = sorted_entities[0]
            selected_entity_type = first_entity['entity_type']
            selected_entity_id = first_entity['entity_id']
            selected_entity = first_entity['entity']
            if selected_entity_type == EntityType.country.value:
                selected_country = selected_entity
                session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_country.id  # Backward compatibility
            session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_entity_type
            session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_entity_id
            current_app.logger.debug(f"No valid entity in session for user {current_user.email}. Defaulting to first alphabetical entity {selected_entity_type}:{selected_entity_id}. Session updated.")

        # Fetch data for the selected entity if available
        if selected_entity and selected_entity_type and selected_entity_id:
            # Get country for the entity (needed for activities and some other features)
            entity_country = EntityService.get_country_for_entity(selected_entity_type, selected_entity_id)
            if entity_country:
                selected_country = entity_country  # Ensure selected_country is set for compatibility

            entity_display_name = EntityService.get_entity_name(selected_entity_type, selected_entity_id, include_hierarchy=True)
            current_app.logger.debug(f"Fetching assigned forms statuses for selected entity {entity_display_name} ({selected_entity_type}:{selected_entity_id}).")

            # Query AssignmentEntityStatus for the selected entity (supports all entity types)
            AF = aliased(AssignedForm)
            # Include active assignments and closed ones (closed sets is_active=False but we still show them under Past Assignments)
            assigned_forms_statuses = (
                AssignmentEntityStatus.query
                .join(AF, AF.id == AssignmentEntityStatus.assigned_form_id)
                .options(
                    db.joinedload(AssignmentEntityStatus.assigned_form).joinedload(AssignedForm.template)
                )
                .filter(
                    AssignmentEntityStatus.entity_type == selected_entity_type,
                    AssignmentEntityStatus.entity_id == selected_entity_id,
                    or_(AF.is_active == True, AF.is_closed == True)
                )
                .order_by(
                    AssignmentEntityStatus.due_date.asc().nulls_last(),
                    AF.assigned_at.desc()
                )
                .all()
            )

            current_app.logger.debug(f"Found {len(assigned_forms_statuses)} assigned form statuses for {entity_display_name}.")

            # Pre-compute per-template item counts to avoid repeated queries inside the loop
            template_ids = {
                aes.assigned_form.template.id
                for aes in assigned_forms_statuses
                if aes.assigned_form and aes.assigned_form.template
            }

            countable_item_counts_by_template = {}
            document_counts_by_template = {}

            if template_ids:
                # Single pass aggregation for countable items (all non-document fields)
                counts_rows = (
                    db.session.query(
                        FormSection.template_id,
                        func.sum(case((FormItem.item_type != 'document_field', 1), else_=0)).label('countable_count')
                    )
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(FormSection.template_id.in_(template_ids))
                    .group_by(FormSection.template_id)
                    .all()
                )
                for tpl_id, cnt in counts_rows:
                    countable_item_counts_by_template[tpl_id] = int(cnt or 0)

                # Document fields (all): count every document field regardless of required flag
                document_counts_by_template = dict(
                    db.session.query(FormSection.template_id, func.count())
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(
                        FormSection.template_id.in_(template_ids),
                        FormItem.item_type == 'document_field'
                    )
                    .group_by(FormSection.template_id)
                    .all()
                )

                required_doc_counts_by_template = dict(
                    db.session.query(FormSection.template_id, func.count())
                    .join(FormItem, FormItem.section_id == FormSection.id)
                    .filter(
                        FormSection.template_id.in_(template_ids),
                        and_(FormItem.item_type == 'document_field', FormItem.is_required == True)
                    )
                    .group_by(FormSection.template_id)
                    .all()
                )

            # Batch compute the last modified user per assignment (by latest EntityActivityLog for this entity/country)
            last_modified_user_by_assignment = {}
            contributors_by_assignment = {}
            if assigned_forms_statuses:
                aes_ids = [aes.id for aes in assigned_forms_statuses]
                # Precompute counts of filled data entries per assignment.
                # Non-matrix items: count if value is set, disagg_data is set, or marked not-applicable.
                # Matrix items are handled separately below so that the entire matrix table
                # counts as ONE filled item when ANY cell contains data.
                filled_non_matrix_counts = dict(
                    db.session.query(FormData.assignment_entity_status_id, func.count(FormData.id))
                    .join(FormItem, FormData.form_item_id == FormItem.id)
                    .filter(
                        FormData.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type != 'matrix',
                        or_(
                            FormData.value.isnot(None),
                            FormData.disagg_data.isnot(None),
                            FormData.not_applicable == True
                        )
                    )
                    .group_by(FormData.assignment_entity_status_id)
                    .all()
                )

                # Matrix items: each matrix table counts as 1 filled item if ANY cell has
                # meaningful data (ignoring internal metadata keys).
                matrix_entries = (
                    db.session.query(
                        FormData.assignment_entity_status_id,
                        FormData.disagg_data,
                        FormData.not_applicable,
                    )
                    .join(FormItem, FormData.form_item_id == FormItem.id)
                    .filter(
                        FormData.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type == 'matrix',
                        or_(
                            FormData.disagg_data.isnot(None),
                            FormData.not_applicable == True,
                        )
                    )
                    .all()
                )
                matrix_filled_counts = {}
                for aes_id, disagg, na in matrix_entries:
                    is_filled = False
                    if na:
                        is_filled = True
                    elif disagg and isinstance(disagg, dict):
                        # A matrix is "filled" when at least one non-metadata cell has a value
                        is_filled = any(
                            v is not None and str(v).strip() != ''
                            for k, v in disagg.items()
                            if not k.startswith('_')
                        )
                    if is_filled:
                        matrix_filled_counts[aes_id] = matrix_filled_counts.get(aes_id, 0) + 1

                # Merge non-matrix and matrix filled counts
                filled_data_counts = dict(filled_non_matrix_counts)
                for aes_id, cnt in matrix_filled_counts.items():
                    filled_data_counts[aes_id] = filled_data_counts.get(aes_id, 0) + cnt

                # Precompute counts of documents submitted per assignment (all document fields)
                filled_document_counts = dict(
                    db.session.query(SubmittedDocument.assignment_entity_status_id, func.count(SubmittedDocument.id))
                    .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)
                    .filter(
                        SubmittedDocument.assignment_entity_status_id.in_(aes_ids),
                        FormItem.item_type == 'document_field'
                    )
                    .group_by(SubmittedDocument.assignment_entity_status_id)
                    .all()
                )
                # Only compute last modified users when a country context exists
                if selected_country is not None:
                    subq = (
                        db.session.query(
                            EntityActivityLog.assignment_id.label('aid'),
                            func.max(EntityActivityLog.timestamp).label('max_ts')
                        )
                        .filter(
                            EntityActivityLog.entity_type == 'country',
                            EntityActivityLog.entity_id == selected_country.id,
                            EntityActivityLog.assignment_id.in_(aes_ids)
                        )
                        .group_by(EntityActivityLog.assignment_id)
                    ).subquery()

                    aid_uid_rows = (
                        db.session.query(subq.c.aid, EntityActivityLog.user_id)
                        .join(
                            EntityActivityLog,
                            and_(
                                EntityActivityLog.assignment_id == subq.c.aid,
                                EntityActivityLog.timestamp == subq.c.max_ts
                            )
                        )
                        .all()
                    )

                    user_ids = {uid for _, uid in aid_uid_rows if uid is not None}
                    user_map = {}
                    if user_ids:
                        user_map = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}
                    last_modified_user_by_assignment = {aid: user_map.get(uid) for aid, uid in aid_uid_rows}

                    # Batch compute contributors per assignment (distinct users, ordered by latest activity)
                    contributors_by_assignment = {}
                    contrib_rows = (
                        db.session.query(
                            EntityActivityLog.assignment_id.label('aid'),
                            EntityActivityLog.user_id.label('uid'),
                            func.max(EntityActivityLog.timestamp).label('last_ts'),
                        )
                        .filter(
                            EntityActivityLog.entity_type == 'country',
                            EntityActivityLog.entity_id == selected_country.id,
                            EntityActivityLog.assignment_id.in_(aes_ids),
                            EntityActivityLog.user_id.isnot(None),
                        )
                        .group_by(EntityActivityLog.assignment_id, EntityActivityLog.user_id)
                        .all()
                    )

                    contrib_user_ids = {uid for _, uid, _ in contrib_rows if uid is not None}
                    contrib_user_map = {}
                    if contrib_user_ids:
                        contrib_user_map = {
                            u.id: u for u in User.query.filter(User.id.in_(contrib_user_ids)).all()
                        }

                    # Build {assignment_id: [User, ...]} sorted by last activity desc
                    tmp = {}
                    for aid, uid, last_ts in contrib_rows:
                        user = contrib_user_map.get(uid)
                        if not user:
                            continue
                        tmp.setdefault(aid, []).append((last_ts, user))

                    for aid, items in tmp.items():
                        items.sort(key=lambda x: x[0] or datetime.min, reverse=True)
                        contributors_by_assignment[aid] = [u for _, u in items]
                else:
                    last_modified_user_by_assignment = {}
                    contributors_by_assignment = {}

            # Calculate completion rate for each AssignmentEntityStatus and prepare for combined list
            for aes in assigned_forms_statuses:
                template = aes.assigned_form.template

                # Calculate total items in the template (All non-document fields + All Document Fields)
                # Using unified FormItem approach, excluding Blank/Note fields
                template_id = template.id if template else None
                total_countable_items = countable_item_counts_by_template.get(template_id, 0) if template_id else 0
                total_document_fields = document_counts_by_template.get(template_id, 0) if template_id else 0

                total_possible_items = (
                    total_countable_items + total_document_fields
                )

                # Calculate filled items for this specific assignment country status
                # Count data entries that have actual values OR are marked as not applicable
                # Use proper JSON handling for PostgreSQL - just check if value exists
                filled_data_entries_count = filled_data_counts.get(aes.id, 0)
                filled_documents_count = filled_document_counts.get(aes.id, 0)

                filled_items = filled_data_entries_count + filled_documents_count

                if total_possible_items > 0:
                    completion_rate = (filled_items / total_possible_items) * 100
                else:
                    completion_rate = 0.0 # Handle templates with no items

                # NEW: Get the last modified user from CountryActivityLog
                last_modified_user = last_modified_user_by_assignment.get(aes.id)
                contributors = contributors_by_assignment.get(aes.id, []) if contributors_by_assignment else []
                if (not contributors) and last_modified_user:
                    contributors = [last_modified_user]

                # Add to combined list
                all_forms_for_display.append({
                    'type': 'assigned',
                    'name': f"{aes.assigned_form.period_name} - {template.name if template else 'Template Missing'}",
                    'status': aes.status,
                    'status_timestamp': aes.status_timestamp,
                    'date_info': aes.due_date,
                    'completion_rate': completion_rate,
                    'completion_filled_items': filled_items,
                    'completion_total_items': total_possible_items,
                    'item_object': aes,
                    'is_public': False,
                    'last_modified_user': last_modified_user,
                    'contributors': contributors,
                    'submitted_by_user': aes.submitted_by_user,
                    'approved_by_user': aes.approved_by_user,
                    'submitted_at': aes.submitted_at,
                })


            # NEW: Fetch PublicSubmission records for the selected country
            if selected_country is not None:
                current_app.logger.debug(f"Fetching public submissions for selected country {selected_country.name} (ID: {selected_country.id}).")

                public_submissions = PublicSubmission.query.filter_by(country_id=selected_country.id)\
                    .options(
                        db.joinedload(PublicSubmission.assigned_form).joinedload(AssignedForm.template) # Eager load assignment and template
                    )\
                    .order_by(PublicSubmission.submitted_at.desc()).all() # Order by submitted date

                current_app.logger.debug(f"Found {len(public_submissions)} public submissions for {selected_country.name}.")

                # Group public submissions by assigned_form_id
                for submission in public_submissions:
                     if submission.assigned_form_id not in public_submissions_by_assignment:
                         public_submissions_by_assignment[submission.assigned_form_id] = []
                     public_submissions_by_assignment[submission.assigned_form_id].append(submission)

            # NEW: Add public submission information to existing assignments
            for item in all_forms_for_display:
                if item['type'] == 'assigned':
                    aes = item['item_object']
                    assigned_form_id = aes.assigned_form_id

                    # Check if this assignment has public submissions
                    if assigned_form_id in public_submissions_by_assignment:
                        submissions_list = public_submissions_by_assignment[assigned_form_id]
                        item['public_submissions'] = submissions_list
                        item['public_submission_count'] = len(submissions_list)
                        item['latest_public_submission'] = submissions_list[0]  # Most recent submission
                        # Remove from the dict so it won't be processed as standalone
                        del public_submissions_by_assignment[assigned_form_id]

            # NEW: Process remaining public submissions (standalone - no corresponding assignment)
            for pa_id, submissions_list in public_submissions_by_assignment.items():
                 # Get the parent assigned form (assuming all submissions in the list have the same parent)
                 assigned_form = submissions_list[0].assigned_form

                 if assigned_form and assigned_form.template:
                     template = assigned_form.template

                     # Calculate total items in the template (Indicators + Questions + Matrices + Required Document Fields)
                     # Using unified FormItem approach, excluding Blank/Note fields
                     section_ids = [s.id for s in template.sections]
                     total_template_indicators = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'indicator'
                     ).count()
                     total_template_questions = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'question',
                         # Exclude Blank/Note fields - they don't count toward completion
                         and_(
                             or_(FormItem.question_type.is_(None), FormItem.question_type != QuestionType.blank),
                             or_(FormItem.type.is_(None), FormItem.type != 'blank')
                         )
                     ).count()
                     total_template_matrices = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'matrix'
                     ).count()
                     total_required_document_fields = FormItem.query.filter(
                         FormItem.section_id.in_(section_ids),
                         FormItem.item_type == 'document_field',
                         FormItem.is_required == True
                     ).count()

                     total_possible_items = total_template_indicators + total_template_questions + total_template_matrices + total_required_document_fields

                     # Calculate completion based on the most recent submission in this group
                     latest_submission = submissions_list[0]  # List is ordered by submission date desc

                     # Count filled data entries for this specific submission.
                     # Matrix items are checked separately: each matrix counts as 1 filled
                     # item if ANY cell in its disagg_data has a value.
                     aes = AssignmentEntityStatus.query.filter_by(
                         assigned_form_id=assigned_form.id,
                         entity_type='country',
                         entity_id=latest_submission.country_id
                     ).first()
                     if aes:
                         # Non-matrix items
                         filled_non_matrix = db.session.query(FormData)\
                             .join(FormItem, FormData.form_item_id == FormItem.id)\
                             .filter(
                                 FormData.assignment_entity_status_id == aes.id,
                                 FormItem.item_type != 'matrix',
                                 or_(
                                     FormData.value.isnot(None),
                                     FormData.disagg_data.isnot(None),
                                     FormData.not_applicable == True
                                 )
                             ).count()

                         # Matrix items — count each as filled if any cell has data
                         matrix_rows = db.session.query(FormData.disagg_data, FormData.not_applicable)\
                             .join(FormItem, FormData.form_item_id == FormItem.id)\
                             .filter(
                                 FormData.assignment_entity_status_id == aes.id,
                                 FormItem.item_type == 'matrix',
                                 or_(
                                     FormData.disagg_data.isnot(None),
                                     FormData.not_applicable == True,
                                 )
                             ).all()
                         filled_matrices = 0
                         for disagg, na in matrix_rows:
                             if na:
                                 filled_matrices += 1
                             elif disagg and isinstance(disagg, dict):
                                 if any(
                                     v is not None and str(v).strip() != ''
                                     for k, v in disagg.items()
                                     if not k.startswith('_')
                                 ):
                                     filled_matrices += 1

                         filled_data_entries_count = filled_non_matrix + filled_matrices
                     else:
                         filled_data_entries_count = 0

                     # Count filled required documents for this specific submission
                     # Using unified FormItem approach
                     if aes:
                         filled_required_documents_count = db.session.query(SubmittedDocument)\
                             .join(FormItem, SubmittedDocument.form_item_id == FormItem.id)\
                             .filter(
                                 SubmittedDocument.assignment_entity_status_id == aes.id,
                                 and_(
                                     FormItem.item_type == 'document_field',
                                     FormItem.is_required == True
                                 )
                             ).count()
                     else:
                         filled_required_documents_count = 0

                     filled_items = filled_data_entries_count + filled_required_documents_count

                     if total_possible_items > 0:
                         completion_rate = (filled_items / total_possible_items) * 100
                     else:
                         completion_rate = 0.0

                     # Add to combined list as standalone public submission
                     all_forms_for_display.append({
                         'type': 'public',
                         'name': template.name,
                         'period': assigned_form.period_name,  # Include period name for public forms if available
                         'date_info': latest_submission.submitted_at,  # Use latest submission date for sorting/display
                         'completion_rate': completion_rate,
                        'completion_filled_items': filled_items,
                        'completion_total_items': total_possible_items,
                         'item_object': assigned_form,  # Keep the assigned form object
                         'is_public': True,
                         'view_data_link': url_for('assignment_management.view_public_submissions', assignment_id=assigned_form.id),  # Link to the list of submissions
                         'submission_count': len(submissions_list)  # Add the count of submissions
                     })
                 else:
                     current_app.logger.warning(f"Public Submission group found with no associated AssignedForm ID {pa_id} or template missing.")


            # Sort the combined list - sort by date_info, with None dates last
            all_forms_for_display.sort(key=lambda x: x['date_info'] if x['date_info'] is not None else datetime.max, reverse=False)

            # NEW: Separate assignments into current and past based on status and timestamp
            # Rules:
            # - Requires Revision -> Past
            # - Approved older than 1 month -> Past
            # - Pending or In Progress older than 1 year -> Past
            from datetime import timedelta, timezone
            one_month_ago = utcnow() - timedelta(days=30)
            one_year_ago = utcnow() - timedelta(days=365)

            for item in all_forms_for_display:
                if item['type'] == 'assigned':
                    # Closed assignments always go to past (with Reopen for admins)
                    try:
                        aes = item['item_object']
                        af = aes.assigned_form if aes else None
                        if af and af.is_effectively_closed:
                            past_assignments.append(item)
                            continue
                    except (AttributeError, TypeError):
                        pass
                    # For assigned forms, check if they should be in past submissions
                    if item['status'] == 'Requires Revision':
                        past_assignments.append(item)
                    elif item['status'] in ('Approved', 'Pending', 'In Progress'):
                        # Ensure status_timestamp is timezone-aware for comparison
                        status_ts = item.get('status_timestamp')
                        if status_ts is None:
                            # Fallback: treat assignment time as status timestamp
                            try:
                                status_ts = item['item_object'].assigned_form.assigned_at
                            except Exception as e:
                                current_app.logger.debug("status_ts lookup failed: %s", e)
                                status_ts = None
                        if status_ts and status_ts.tzinfo is None:
                            # If naive, assume it's UTC and make it aware
                            status_ts = status_ts.replace(tzinfo=timezone.utc)
                        if item['status'] == 'Approved':
                            if status_ts and status_ts < one_month_ago:
                                past_assignments.append(item)
                            else:
                                current_assignments.append(item)
                        else:  # Pending or In Progress: move to past if older than 1 year
                            if status_ts and status_ts < one_year_ago:
                                past_assignments.append(item)
                            else:
                                current_assignments.append(item)
                    else:
                        current_assignments.append(item)
                else:
                    # Public submissions always go to current for now
                    current_assignments.append(item)


            # NEW: Fetch and categorize focal points for the selected context (only if country is known)
            # PERFORMANCE: Use explicit join instead of .any() to avoid subquery per user
            if selected_country is not None:
                # UserEntityPermission is already imported at the top of the file
                all_focal_points_for_country = (
                    User.query
                    .join(UserEntityPermission, User.id == UserEntityPermission.user_id)
                    .join(RbacUserRole, User.id == RbacUserRole.user_id)
                    .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                    .filter(
                        RbacRole.code == "assignment_editor_submitter",
                        UserEntityPermission.entity_type == 'country',
                        UserEntityPermission.entity_id == selected_country.id
                    )
                    .distinct()
                    .order_by(User.name)
                    .all()
                )

                from app.utils.organization_helpers import is_org_email
                admin_role_user_ids = set(
                    uid for (uid,) in db.session.query(RbacUserRole.user_id)
                    .join(RbacRole, RbacUserRole.role_id == RbacRole.id)
                    .filter(RbacRole.code.in_(["system_manager", "admin_core"]))
                    .all()
                )
                ns_focal_points = [fp for fp in all_focal_points_for_country if not is_org_email(fp.email)]
                org_focal_points = [
                    fp for fp in all_focal_points_for_country
                    if is_org_email(fp.email) and fp.id not in admin_role_user_ids
                ]
                current_app.logger.debug(f"Found {len(ns_focal_points)} NS focal points and {len(org_focal_points)} organization focal points for {selected_country.name}.")
            else:
                ns_focal_points = []
                org_focal_points = []

            # NEW: Fetch templates available for self-reporting for the selected country
            # REMOVED: The filter to exclude already assigned templates is removed
            # Filter by published version's add_to_self_report property
            self_report_templates = FormTemplate.query.join(
                FormTemplateVersion,
                and_(
                    FormTemplate.id == FormTemplateVersion.template_id,
                    FormTemplateVersion.status == 'published'
                )
            ).filter(
                FormTemplateVersion.add_to_self_report == True
                # FormTemplate.id.notin_(assigned_template_ids) # REMOVED FILTER
            ).all()
            # Sort by name (from published version) in Python since it's a property
            self_report_templates.sort(key=lambda t: t.name if t.name else "")

            # Log using entity display name to support non-country entities
            current_app.logger.debug(
                f"Found {len(self_report_templates)} templates available for self-reporting (including already assigned ones) for {entity_display_name}."
            )


        else:
             current_app.logger.debug("No country selected or available for fetching assigned forms statuses.")

    # NEW: Fetch recent activities for the user and selected country
    recent_activities = []

    if selected_country:
        # Get recent activities for this country (last month, initial load of 10)
        recent_activities = get_country_recent_activities(
            country_id=selected_country.id,
            days=30,
            limit=10
        )

        current_app.logger.debug(f"Found {len(recent_activities)} recent activities for {selected_country.name}")

        # Post-process recent activities so matrix-style field changes only include changed cells
        # Also add period information to activities for filtering
        try:
            for activity in recent_activities:
                params = getattr(activity, 'summary_params', None)
                if not isinstance(params, dict):
                    params = {}
                    activity.summary_params = params

                # Add period information if assignment_id is available
                assignment_id = getattr(activity, 'assignment_id', None)
                if assignment_id and 'period' not in params:
                    try:
                        aes = AssignmentEntityStatus.query.get(assignment_id)
                        if aes and aes.assigned_form:
                            period_name = aes.assigned_form.period_name
                            params['period'] = period_name
                            # Update template-period combination for filtering
                            template_name = params.get('template', '')
                            if template_name:
                                params['template_period'] = f"{template_name} - {period_name}"
                    except Exception as e:
                        current_app.logger.debug(f"Could not get period for activity {assignment_id}: {e}")

                key = getattr(activity, 'summary_key', None)

                # Single field change
                if key == 'activity.form_data_updated.single':
                    old_val = params.get('old')
                    new_val = params.get('new')
                    trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                    # Only override when we detect a real matrix-style diff
                    if trimmed_old is not None and trimmed_new is not None:
                        params['old'] = trimmed_old
                        params['new'] = trimmed_new

                # Multiple field changes – each change entry may be matrix-style
                elif key == 'activity.form_data_updated.multiple' and isinstance(params.get('changes'), list):
                    for change in params['changes']:
                        if not isinstance(change, dict):
                            continue
                        old_val = change.get('old')
                        new_val = change.get('new')
                        trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                        if trimmed_old is not None and trimmed_new is not None:
                            change['old'] = trimmed_old
                            change['new'] = trimmed_new
        except Exception as e:
            # Never break the dashboard if activity post-processing fails
            current_app.logger.error(
                f"Error post-processing recent activities for matrix diffs: {e}",
                exc_info=True
            )

    # Always render the dashboard; the template handles None values where applicable
    return render_template("core/dashboard.html",
                       user=current_user,
                       user_countries=user_countries,
                       user_entities=user_entities,  # Pass user entities to template
                       selected_country=selected_country,
                       selected_entity=selected_entity,  # Pass selected entity to template
                       selected_entity_type=selected_entity_type,  # Pass entity type to template
                       selected_entity_id=selected_entity_id,  # Pass entity ID to template
                       # Pass the combined list
                       all_forms_for_display=all_forms_for_display,
                       # NEW: Pass the separate lists
                       current_assignments=current_assignments,
                       past_assignments=past_assignments,
                       show_country_select=show_country_select,
                       show_entity_select=show_entity_select,  # Pass entity select flag
                       title=_("Dashboard"),
                       current_date=current_date,
                       # NEW: Pass categorized focal points to the template
                       ns_focal_points=ns_focal_points,
                       org_focal_points=org_focal_points,
                       # NEW: Pass self-report templates to the template
                       self_report_templates=self_report_templates,
                       # NEW: Pass the delete form for CSRF protection
                       delete_form=delete_form,
                       # NEW: Pass the reopen form for CSRF protection
                       reopen_form=reopen_form,
                       # NEW: Pass recent activities data
                       recent_activities=recent_activities,
                       # NEW: Pass the approve form for CSRF protection
                       approve_form=approve_form,
                       # NEW: Pass the request access form for country access requests
                       request_access_form=request_access_form,
                       # NEW: Pass pending access requests to template
                       pending_access_requests=pending_access_requests,
                       # NEW: Pass all access requests to template
                       all_access_requests=all_access_requests,
                       can_request_multiple_countries=can_request_multiple_countries,
                       non_org_has_counting_request=non_org_has_counting_request,
                       enabled_entity_types=enabled_entity_groups,
                       # NEW: Pass the helper function for localized country names
                       get_localized_country_name=get_localized_country_name,
                       # NEW: Pass the helper function for localized National Society names (now also available as template global)
                       get_localized_national_society_name=_get_localized_national_society_name)


@bp.route("/load_more_activities", methods=["POST"])
@login_required
def load_more_activities():
    """Load more recent activities with pagination."""
    from app.utils.notifications import get_country_recent_activities

    try:
        offset = _parse_int(request.form.get('offset', 0), 'offset', minimum=0)
        limit = _parse_int(request.form.get('limit', 10), 'limit', minimum=1)
        country_id = _parse_int(request.form.get('country_id'), 'country_id', minimum=1)

        # Verify user has access to this country
        user_countries = get_user_countries()  # Uses current_user internally
        country_ids = [c['id'] for c in user_countries]  # Returns list of dicts, not objects

        from app.services.authorization_service import AuthorizationService
        if not AuthorizationService.has_country_access(current_user, country_id):
            return json_forbidden('Access denied')

        # Get more activities - when loading more, go beyond the 1 month limit
        # Use a large days value (1 year) to allow loading older activities
        # Fetch enough to check if there are more beyond this batch
        fetch_limit = offset + limit + 1
        all_activities = get_country_recent_activities(
            country_id=country_id,
            days=365,  # Allow loading activities up to 1 year old
            limit=fetch_limit
        )

        # Get the next batch
        more_activities = all_activities[offset:offset + limit] if offset < len(all_activities) else []
        # Check if there are more activities available
        has_more = len(all_activities) >= fetch_limit

        # Post-process activities (same as dashboard)
        for activity in more_activities:
            params = getattr(activity, 'summary_params', None)
            if not isinstance(params, dict):
                params = {}
                activity.summary_params = params

            # Add period information if assignment_id is available
            assignment_id = getattr(activity, 'assignment_id', None)
            if assignment_id and 'period' not in params:
                try:
                    aes = AssignmentEntityStatus.query.get(assignment_id)
                    if aes and aes.assigned_form:
                        period_name = aes.assigned_form.period_name
                        params['period'] = period_name
                        template_name = params.get('template', '')
                        if template_name:
                            params['template_period'] = f"{template_name} - {period_name}"
                except Exception as e:
                    current_app.logger.debug(f"Could not get period for activity {assignment_id}: {e}")

            # Trim matrix-style diffs so we only render changed cells
            try:
                key = getattr(activity, 'summary_key', None)

                if key == 'activity.form_data_updated.single':
                    old_val = params.get('old')
                    new_val = params.get('new')
                    trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                    if trimmed_old is not None and trimmed_new is not None:
                        params['old'] = trimmed_old
                        params['new'] = trimmed_new

                elif key == 'activity.form_data_updated.multiple' and isinstance(params.get('changes'), list):
                    for change in params['changes']:
                        if not isinstance(change, dict):
                            continue
                        old_val = change.get('old')
                        new_val = change.get('new')
                        trimmed_old, trimmed_new = _extract_changed_matrix_values(old_val, new_val)
                        if trimmed_old is not None and trimmed_new is not None:
                            change['old'] = trimmed_old
                            change['new'] = trimmed_new
            except Exception as e:
                current_app.logger.debug(f"Matrix diff trimming failed for load_more activities: {e}")

        # Render activities to HTML using template partial
        # Note: profile_icon is a Jinja2 macro imported in the template, not needed here
        activity_html = render_template('core/activity_items_partial.html',
                                       recent_activities=more_activities,
                                       get_localized_template_name=get_localized_template_name,
                                       localized_field_name=localized_field_name,
                                       format_activity_value=format_activity_value,
                                       render_activity_summary=render_activity_summary,
                                       render_matrix_change=render_matrix_change,
                                       _=_,
                                       url_for=url_for)

        return json_ok(html=activity_html, has_more=has_more, count=len(more_activities))
    except ValueError as err:
        current_app.logger.warning(f"Invalid pagination parameters: {err}")
        return json_bad_request('Invalid request parameters.')
    except Exception as e:
        current_app.logger.error(f"Error loading more activities: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/mark_notifications_read", methods=["POST"])
@login_required
def mark_notifications_read():
    """Mark selected notifications as read via AJAX."""
    from app.services.notification_service import NotificationService
    from app.utils.api_responses import json_bad_request, json_server_error, json_ok

    try:
        notification_ids = get_json_safe().get('notification_ids', [])
        if not notification_ids:
            return json_bad_request('No notifications specified')

        # Convert to list of ints if needed
        if isinstance(notification_ids, str):
            notification_ids = [int(id.strip()) for id in notification_ids.split(',') if id.strip().isdigit()]

        # Mark notifications as read (service handles ownership validation)
        success = NotificationService.mark_as_read(notification_ids, current_user.id)

        if success:
            return json_ok()
        else:
            return json_server_error('Failed to update notifications')

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/users/profile-summary", methods=["GET"])
@login_required
def api_users_profile_summary():
    """Return lightweight user profile summaries for hover tooltips (dashboard/non-admin pages)."""
    try:
        user_ids_raw = request.args.getlist('user_ids')
        if not user_ids_raw:
            user_ids_csv = (request.args.get('user_ids') or '').strip()
            if user_ids_csv:
                user_ids_raw = [part.strip() for part in user_ids_csv.split(',') if part.strip()]

        emails_raw = request.args.getlist('emails')
        if not emails_raw:
            emails_csv = (request.args.get('emails') or '').strip()
            if emails_csv:
                emails_raw = [part.strip() for part in emails_csv.split(',') if part.strip()]

        user_ids = []
        for value in user_ids_raw:
            with suppress(Exception):
                user_ids.append(int(value))

        emails = [str(email).strip().lower() for email in (emails_raw or []) if str(email).strip()]

        if not user_ids and not emails:
            return json_ok(status='success', profiles=[])

        query = User.query
        filters = []
        if user_ids:
            filters.append(User.id.in_(list(set(user_ids))))
        if emails:
            filters.append(func.lower(User.email).in_(list(set(emails))))
        if filters:
            query = query.filter(or_(*filters))

        users = query.all()
        if not users:
            return json_ok(status='success', profiles=[])

        # Non-admin users can only fetch profile summaries for users sharing at least one entity scope,
        # plus themselves. Admin/system-manager users are unrestricted.
        from app.services.authorization_service import AuthorizationService
        is_privileged = bool(
            AuthorizationService.is_system_manager(current_user) or
            AuthorizationService.has_rbac_permission(current_user, "admin.users.view")
        )

        if not is_privileged:
            visible_user_ids = {int(current_user.id)}
            requester_scopes = {
                (str(p.entity_type), int(p.entity_id))
                for p in UserEntityPermission.query.filter_by(user_id=current_user.id).all()
                if getattr(p, "entity_type", None) and getattr(p, "entity_id", None) is not None
            }
            if requester_scopes:
                all_candidate_perms = UserEntityPermission.query.filter(
                    UserEntityPermission.user_id.in_([u.id for u in users])
                ).all()
                for perm in all_candidate_perms:
                    scope_key = (str(perm.entity_type), int(perm.entity_id))
                    if scope_key in requester_scopes:
                        visible_user_ids.add(int(perm.user_id))
            users = [u for u in users if int(u.id) in visible_user_ids]
            if not users:
                return json_ok(status='success', profiles=[])

        found_user_ids = [u.id for u in users]

        # Fetch last presence (most recent session activity) per user
        last_presence_by_user_id = {}
        with suppress(Exception):
            last_presence_rows = (
                db.session.query(
                    UserSessionLog.user_id,
                    func.max(UserSessionLog.last_activity).label('last_presence')
                )
                .filter(UserSessionLog.user_id.in_(found_user_ids))
                .group_by(UserSessionLog.user_id)
                .all()
            )
            for row in last_presence_rows:
                last_presence_by_user_id[row.user_id] = row.last_presence

        roles_by_user_id = {}
        with suppress(Exception):
            user_roles = RbacUserRole.query.filter(RbacUserRole.user_id.in_(found_user_ids)).all()
            role_ids = list({ur.role_id for ur in user_roles})
            roles = RbacRole.query.filter(RbacRole.id.in_(role_ids)).all() if role_ids else []
            roles_by_id = {r.id: r for r in roles}
            for ur in user_roles:
                role = roles_by_id.get(ur.role_id)
                if not role:
                    continue
                role_code = (role.code or '').strip()
                role_label = (role.name or '').strip()
                roles_by_user_id.setdefault(ur.user_id, []).append(role_code or role_label)

        all_permissions = UserEntityPermission.query.filter(
            UserEntityPermission.user_id.in_(found_user_ids)
        ).all()

        country_count_by_user_id = {}
        entity_counts_by_user_id = {}
        for perm in all_permissions:
            uid = int(perm.user_id)
            etype = str(perm.entity_type or '')
            if etype == 'country':
                country_count_by_user_id[uid] = country_count_by_user_id.get(uid, 0) + 1
            elif etype:
                bucket = entity_counts_by_user_id.setdefault(uid, {})
                bucket[etype] = int(bucket.get(etype, 0)) + 1

        profiles = []
        for user in users:
            profile_color = user.profile_color
            if not profile_color:
                with suppress(Exception):
                    profile_color = user.generate_profile_color()

            entity_counts = entity_counts_by_user_id.get(user.id, {})
            entity_summary_parts = []
            for key, value in sorted(entity_counts.items()):
                if int(value) > 0:
                    entity_summary_parts.append(f"{key.replace('_', ' ')}: {value}")

            last_presence_dt = last_presence_by_user_id.get(user.id)
            last_presence_iso = last_presence_dt.isoformat() + 'Z' if last_presence_dt else None

            profiles.append({
                'id': user.id,
                'name': user.name or '',
                'email': user.email or '',
                'title': user.title or '',
                'profile_color': profile_color or '#3B82F6',
                'active': bool(user.active),
                'last_presence': last_presence_iso,
                'rbac_roles': roles_by_user_id.get(user.id, []),
                'countries_count': int(country_count_by_user_id.get(user.id, 0)),
                'entity_counts': entity_counts,
                'entity_summary': ', '.join(entity_summary_parts),
            })

        return json_ok(status='success', profiles=profiles)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    """Get notifications for the current user via API"""
    from app.services.notification_service import NotificationService

    try:
        # Get notifications
        notifications_data, total_count = NotificationService.get_user_notifications(
            user_id=current_user.id,
            unread_only=False,
            notification_type=None,
            date_from=None,
            date_to=None,
            include_archived=False,
            archived_only=False,
            limit=20,
            offset=0
        )

        unread_count = NotificationService.get_unread_count(current_user.id)

        return json_ok(
            success=True,
            notifications=notifications_data,
            unread_count=unread_count,
            total_count=total_count
        )

    except Exception as e:
        current_app.logger.error(f"Error getting notifications: {e}")
        from app.utils.api_responses import json_server_error
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/notifications/count", methods=["GET"])
@login_required
def api_get_notifications_count():
    """Get unread notifications count for the current user"""
    from app.services.notification_service import NotificationService

    try:
        unread_count = NotificationService.get_unread_count(current_user.id)

        return json_ok(success=True, unread_count=unread_count)

    except Exception as e:
        current_app.logger.error(f"Error getting notifications count: {e}")
        from app.utils.api_responses import json_server_error
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/api/notifications/websocket-status", methods=["GET"])
def api_websocket_status_public():
    """
    Public endpoint to check if WebSocket is enabled on the server.
    No authentication required - useful for quick verification after deployment.

    Returns basic WebSocket status without sensitive diagnostics.
    """
    import os

    websocket_enabled = bool(current_app.config.get('WEBSOCKET_ENABLED', True))

    # Check if flask-sock is available
    try:
        import flask_sock  # type: ignore
        flask_sock_available = True
    except Exception as e:
        current_app.logger.debug("flask_sock import failed: %s", e)
        flask_sock_available = False

    return json_ok(
        success=True,
        enabled=websocket_enabled,
        websocket_enabled=websocket_enabled,
        websocket_endpoint='/api/notifications/ws',
        flask_sock_available=flask_sock_available,
        message='WebSocket status check - use /notifications/api/stream/status for full diagnostics (login required)'
    )


@bp.route("/select_country/<int:country_id>", methods=["POST"])
@login_required
def select_country(country_id):
    current_app.logger.warning("select_country route was called, but dashboard route handles POST. This route might be redundant.")
    return redirect(url_for("main.dashboard"))

# NEW: Route to handle reopening an assignment
@bp.route("/reopen_assignment/<int:aes_id>", methods=["POST"])
@login_required
def reopen_assignment(aes_id):
    """
    Reopens an assignment by changing its status to 'In Progress'.
    Uses AuthorizationService for granular RBAC checks.
    """
    from app.services.authorization_service import AuthorizationService

    assignment_entity_status = AssignmentEntityStatus.query.get_or_404(aes_id)

    # Check RBAC permission
    if not AuthorizationService.can_reopen_assignment(assignment_entity_status, current_user):
        flash("You do not have permission to reopen this assignment.", "danger")
        current_app.logger.warning(f"User {current_user.email} attempted to reopen assignment {aes_id} without sufficient permission.")
        return redirect(url_for("main.dashboard"))

    # Validate CSRF token
    form = ReopenAssignmentForm()
    if not form.validate_on_submit():
        flash("Invalid request. Please try again.", "danger")
        current_app.logger.warning(f"CSRF validation failed for reopen assignment {aes_id} for user {current_user.email}.")
        return redirect(url_for("main.dashboard"))

    if assignment_entity_status:
        try:
            assignment_entity_status.status = 'In Progress'
            assignment_entity_status.status_timestamp = utcnow()  # Set timestamp when status changes
            db.session.flush()

            # Send notification to focal points about reopening
            try:
                from app.utils.notifications import notify_assignment_reopened
                created = notify_assignment_reopened(assignment_entity_status)
            except Exception as e:
                current_app.logger.error(f"Error sending assignment reopened notification: {e}", exc_info=True)
                # Don't fail the reopen if notification fails

            flash(f"Assignment '{assignment_entity_status.assigned_form.template.name if assignment_entity_status.assigned_form.template else 'Template Missing'}' for {assignment_entity_status.country.name if assignment_entity_status.country else 'N/A'} has been reopened.", "success")
        except Exception as e:
            request_transaction_rollback()
            flash("Error reopening assignment.", "danger")
            current_app.logger.error(f"Error during DB commit for reopening assignment {aes_id}: {e}", exc_info=True)
    else:
        flash("Assignment not found.", "danger")
        current_app.logger.warning(f"Admin {current_user.email} attempted to reopen non-existent assignment {aes_id}.")

    # Redirect back to the dashboard, preserving the selected country if possible
    selected_country_id = session.get(SELECTED_COUNTRY_ID_SESSION_KEY)
    if selected_country_id:
         return redirect(url_for("main.dashboard", country_id=selected_country_id))
    else:
         return redirect(url_for("main.dashboard"))

# NEW: Route to handle approving an assignment
@bp.route("/approve_assignment/<int:aes_id>", methods=["POST"])
@login_required
def approve_assignment(aes_id):
    """
    Approves an assignment by changing its status to 'Approved'.
    Uses AuthorizationService for granular RBAC checks.
    """
    from app.services.authorization_service import AuthorizationService

    assignment_entity_status = AssignmentEntityStatus.query.get_or_404(aes_id)

    # Check RBAC permission
    if not AuthorizationService.can_approve_assignment(assignment_entity_status, current_user):
        flash("You do not have permission to approve this assignment.", "danger")
        current_app.logger.warning(f"User {current_user.email} attempted to approve assignment {aes_id} without sufficient permission.")
        return redirect(url_for("main.dashboard"))

    # Validate CSRF token
    form = ApproveAssignmentForm()
    if not form.validate_on_submit():
        flash("Invalid request. Please try again.", "danger")
        current_app.logger.warning(f"CSRF validation failed for approve assignment {aes_id} for user {current_user.email}.")
        return redirect(url_for("main.dashboard"))

    if assignment_entity_status:
        try:
            assignment_entity_status.status = 'Approved'
            assignment_entity_status.status_timestamp = utcnow()  # Set timestamp when status changes
            assignment_entity_status.approved_by_user_id = current_user.id
            db.session.flush()

            # Send notification to focal points about approval
            try:
                from app.utils.notifications import notify_assignment_approved
                notify_assignment_approved(assignment_entity_status)
            except Exception as e:
                current_app.logger.error(f"Error sending assignment approved notification: {e}", exc_info=True)
                # Don't fail the approval if notification fails

            flash(f"Assignment '{assignment_entity_status.assigned_form.template.name if assignment_entity_status.assigned_form.template else 'Template Missing'}' for {assignment_entity_status.country.name if assignment_entity_status.country else 'N/A'} has been approved.", "success")
            current_app.logger.info(f"AssignmentEntityStatus ID {aes_id} status changed to 'Approved' by admin {current_user.email}.")
        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error during DB commit for approving assignment {aes_id}: {e}", exc_info=True)
    else:
        flash("Assignment not found.", "danger")
        current_app.logger.warning(f"Admin {current_user.email} attempted to approve non-existent assignment {aes_id}.")

    # Redirect back to the dashboard, preserving the selected country if possible
    selected_country_id = session.get(SELECTED_COUNTRY_ID_SESSION_KEY)
    if selected_country_id:
         return redirect(url_for("main.dashboard", country_id=selected_country_id))
    else:
         return redirect(url_for("main.dashboard"))

@bp.route("/request_country_access", methods=["POST"])
@login_required
def request_country_access():
    """Handle country access request submission from dashboard. Supports multiple countries."""
    form = RequestCountryAccessForm()
    can_request_multiple_countries = is_organization_email(getattr(current_user, "email", ""))
    return_to = request.form.get('return_to', '').strip()
    redirect_endpoint = 'auth.account_settings' if return_to == 'account_settings' else 'main.dashboard'

    if form.validate_on_submit():
        try:
            requested_country_ids = form.requested_country_id.data
            if requested_country_ids and len(requested_country_ids) > 0:
                # Ensure we have a list
                if not isinstance(requested_country_ids, list):
                    requested_country_ids = [requested_country_ids]

                if not can_request_multiple_countries and len(requested_country_ids) > 1:
                    flash(
                        _(
                            'Only users with an organization email can request access to multiple countries at once. Please select a single country.'
                        ),
                        'warning'
                    )
                    return redirect(url_for(redirect_endpoint))

                # Non-org users can only ever have one "counting" request: PENDING or APPROVED with access still active (rejected/revoked don't count)
                if not can_request_multiple_countries:
                    existing_requests = CountryAccessRequest.query.filter(
                        CountryAccessRequest.user_id == current_user.id
                    ).filter(
                        (CountryAccessRequest.status == CountryAccessRequestStatus.PENDING) |
                        (CountryAccessRequest.status == CountryAccessRequestStatus.APPROVED)
                    ).all()
                    has_counting_request = False
                    for req in existing_requests:
                        if req.status == CountryAccessRequestStatus.PENDING:
                            has_counting_request = True
                            break
                        if req.status == CountryAccessRequestStatus.APPROVED and req.country_id:
                            if current_user.has_entity_access(EntityType.country.value, req.country_id):
                                has_counting_request = True
                                break
                    if has_counting_request:
                        flash(
                            _('You can only request access to one country in total. You have already submitted a request.'),
                            'warning'
                        )
                        return redirect(url_for(redirect_endpoint))

                created_requests = []
                skipped_already_pending = []
                skipped_already_has_access = []
                skipped_invalid = []

                # Get all admins and system managers (excluding the requester) for notifications
                from app.utils.notifications import create_notification
                from app.models.enums import NotificationType
                admin_role_ids = (
                    db.session.query(RbacRole.id)
                    .filter(
                        or_(
                            RbacRole.code == "system_manager",
                            RbacRole.code == "admin_core",
                            RbacRole.code.like("admin\\_%", escape="\\"),
                        )
                    )
                    .subquery()
                )
                admin_users = (
                    User.query.join(RbacUserRole, User.id == RbacUserRole.user_id)
                    .filter(RbacUserRole.role_id.in_(admin_role_ids), User.id != current_user.id)
                    .distinct()
                    .all()
                )
                admin_user_ids = [admin.id for admin in admin_users] if admin_users else []
                user_name = current_user.name or current_user.email

                # Process each country
                for country_id in requested_country_ids:
                    try:
                        country_id_int = int(country_id)

                        # Check if user already has a pending request for this country
                        existing_request = CountryAccessRequest.query.filter_by(
                            user_id=current_user.id,
                            country_id=country_id_int,
                            status=CountryAccessRequestStatus.PENDING
                        ).first()

                        if existing_request:
                            country = Country.query.get(country_id_int)
                            country_name = country.name if country else f'Country ID {country_id_int}'
                            skipped_already_pending.append(country_name)
                            continue

                        # Check if user already has access to this country
                        country = Country.query.get(country_id_int)
                        if not country:
                            skipped_invalid.append(f'ID {country_id_int}')
                            continue

                        user_permissions = UserEntityPermission.query.filter_by(
                            user_id=current_user.id,
                            entity_type='country',
                            entity_id=country.id
                        ).first()

                        if user_permissions:
                            skipped_already_has_access.append(country.name)
                            continue

                        # Check auto-approve setting
                        from app.utils.app_settings import get_auto_approve_access_requests
                        auto_approve = get_auto_approve_access_requests()

                        access_request = CountryAccessRequest(
                            user_id=current_user.id,
                            country_id=country_id_int,
                            request_message=form.request_message.data or None,
                            status=CountryAccessRequestStatus.PENDING
                        )
                        db.session.add(access_request)
                        db.session.flush()

                        if auto_approve:
                            current_user.add_entity_permission(entity_type='country', entity_id=country.id)
                            access_request.status = CountryAccessRequestStatus.APPROVED
                            access_request.processed_at = db.func.now()
                            access_request.admin_notes = 'Auto-approved'
                            db.session.flush()
                            try:
                                from app.utils.notifications import notify_user_added_to_country
                                notify_user_added_to_country(current_user.id, country.id)
                            except Exception as e:
                                current_app.logger.debug("notify_user_added_to_country failed: %s", e)

                        created_requests.append(access_request)

                        # Notify admins and system managers about the access request
                        if admin_user_ids and not auto_approve:
                            try:
                                country_name = country.name if country else 'Unknown Country'

                                # Create notification for each admin using translation keys
                                notifications = create_notification(
                                    user_ids=admin_user_ids,
                                    notification_type=NotificationType.access_request_received,
                                    title_key='notification.access_request_received.title',
                                    title_params=None,
                                    message_key='notification.access_request_received.message',
                                    message_params={
                                        'user_name': user_name,
                                        'country_name': country_name
                                    },
                                    entity_type='country',
                                    entity_id=country_id_int,
                                    related_object_type='country_access_request',
                                    related_object_id=access_request.id,
                                    related_url=url_for('user_management.access_requests'),
                                    priority='normal',
                                    icon='fas fa-user-plus'
                                )

                                if notifications:
                                    current_app.logger.info(
                                        f"Created {len(notifications)} notifications for admins about access request "
                                        f"from {current_user.email} for country {country_name}"
                                    )
                            except Exception as e:
                                # Log error but don't fail the request
                                current_app.logger.error(
                                    f"Error creating notifications for access request: {e}",
                                    exc_info=True
                                )
                    except (ValueError, TypeError) as e:
                        current_app.logger.warning(f"Invalid country ID in request: {country_id}, error: {e}")
                        skipped_invalid.append(str(country_id))
                        continue

                db.session.flush()

                # Provide user feedback
                if created_requests:
                    all_auto = all(r.status == CountryAccessRequestStatus.APPROVED for r in created_requests)
                    if all_auto:
                        if len(created_requests) == 1:
                            flash(_('Your country access request has been approved. You now have access.'), 'success')
                        else:
                            flash(_('Your access requests for %(count)d countries have been approved.', count=len(created_requests)), 'success')
                    elif len(created_requests) == 1:
                        flash(_('Your country access request has been submitted. An admin will review it shortly.'), 'success')
                    else:
                        flash(_('Your access requests for %(count)d countries have been submitted. An admin will review them shortly.', count=len(created_requests)), 'success')

                    current_app.logger.info(
                        f"User {current_user.email} requested access to {len(created_requests)} countries: "
                        f"{[r.country_id for r in created_requests]}"
                    )

                # Inform about skipped countries
                if skipped_already_pending:
                    if len(skipped_already_pending) == 1:
                        flash(_('You already have a pending request for: %(country)s', country=skipped_already_pending[0]), 'info')
                    else:
                        flash(_('You already have pending requests for: %(countries)s', countries=', '.join(skipped_already_pending)), 'info')

                if skipped_already_has_access:
                    if len(skipped_already_has_access) == 1:
                        flash(_('You already have access to: %(country)s', country=skipped_already_has_access[0]), 'info')
                    else:
                        flash(_('You already have access to: %(countries)s', countries=', '.join(skipped_already_has_access)), 'info')

                if skipped_invalid:
                    flash(_('Some countries could not be processed. Please try again.'), 'warning')

                # If no requests were created and nothing was skipped, show error
                if not created_requests and not skipped_already_pending and not skipped_already_has_access:
                    flash(_('No valid countries were selected. Please try again.'), 'warning')
            else:
                flash(_('Please select at least one country.'), 'danger')
        except Exception as e:
            request_transaction_rollback()
            flash(_('Could not submit request. Please try again.'), 'danger')
            current_app.logger.error(f"Error creating country access request: {e}", exc_info=True)
    else:
        # Form validation errors
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"{getattr(form, field).label.text}: {error}", 'danger')

    return redirect(url_for(redirect_endpoint))

@bp.route("/download_submission_pdf/<int:submission_id>")
def download_submission_pdf(submission_id):
    """Generate and serve a PDF of the public submission using the exact HTML template."""
    # Get the submission
    submission = PublicSubmission.query.get_or_404(submission_id)

    # Create a dummy field class for form rendering
    class DummyField:
        def __init__(self, data, label=""):
            self.data = data
            self.label = label

    class DummyForm:
        def __init__(self, submission):
            self.name = DummyField(submission.submitter_name, "Name")
            self.email = DummyField(submission.submitter_email, "Email")
            self.csrf_token = DummyField("")

    class DummyCountryForm:
        def __init__(self, country):
            self.country_id = DummyField(country, "Country")

    # Create dummy forms to match template structure
    form = DummyForm(submission)
    country_form = DummyCountryForm(submission.country)

    # Organize data entries by section (unified FormItem model)
    organized_data = {}
    for entry in submission.data_entries:
        form_item = getattr(entry, 'form_item', None)
        if not form_item:
            continue
        section = FormSection.query.get(form_item.section_id)
        if not section:
            continue
        if section.id not in organized_data:
            organized_data[section.id] = {
                'section': section,
                'entries': []
            }
        entry_type = 'indicator' if form_item.item_type == 'indicator' else ('question' if form_item.item_type == 'question' else form_item.item_type)
        organized_data[section.id]['entries'].append({
            'type': entry_type,
            'item': form_item,
            'value': entry.value
        })

    # Sort sections by their order
    organized_sections = sorted(
        organized_data.values(),
        key=lambda x: x['section'].order if x['section'].order is not None else float('inf')
    )

    # Organize documents by section (use SubmittedDocument.form_item)
    organized_documents = {}
    for doc in submission.submitted_documents:
        form_item = getattr(doc, 'form_item', None)
        if not form_item or not form_item.form_section:
            continue
        section = form_item.form_section
        if section.id not in organized_documents:
            organized_documents[section.id] = {
                'section': section,
                'documents': []
            }
        organized_documents[section.id]['documents'].append(doc)

    # Sort document sections by their order
    organized_doc_sections = sorted(
        organized_documents.values(),
        key=lambda x: x['section'].order if x['section'].order is not None else float('inf')
    )

    # Generate HTML using the exact template
    html_content = render_template(
        'public_form.html',
        title=f"Submission Details - {submission.country.name}",
        form=form,
        country_form=country_form,
        sections=organized_sections,
        document_sections=organized_doc_sections,
        submission=submission,
        is_pdf=True  # Flag to modify template behavior for PDF
    )

    # Create PDF from HTML
    pdf_buffer = BytesIO()

    # Lazy import heavy PDF libraries to avoid container runtime deps unless needed
    try:
        from weasyprint import HTML, CSS  # type: ignore
    except Exception as e:
        current_app.logger.error(f"WeasyPrint not available: {e}")
        return current_app.response_class(
            response="PDF generation is not available on this deployment.",
            status=503,
            mimetype='text/plain'
        )

    # Get the path to the static directory for loading assets
    static_dir = os.path.join(current_app.root_path, 'static')

    # Create custom CSS for PDF
    pdf_css = CSS(string='''
        @page {
            margin: 2.5cm 2cm;
            size: letter;
            @bottom-right {
                content: "Page " counter(page);
                font-size: 9pt;
                color: #6b7280;
                padding: 1cm 0;
            }
            @top-center {
                content: string(title);
                font-size: 9pt;
                color: #6b7280;
                padding: 1cm 0;
            }
        }

        /* Set string value for running header */
        h1 { string-set: title content(); }

        /* Base styles */
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: white !important;
            color: #111827;
            line-height: 1.5;
        }

        /* Container */
        .container {
            width: 100% !important;
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        /* Form sections */
        .form-section {
            background-color: white;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 2rem;
            margin-bottom: 2rem;
            page-break-inside: avoid;
        }

        /* Section titles */
        .form-section-title {
            font-size: 1.5rem;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 1.5rem;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 0.5rem;
        }

        /* Labels */
        .form-item-label {
            font-weight: 600;
            color: #34495e;
            margin-bottom: 0.5rem;
            display: block;
        }

        /* Input fields */
        .form-item-input {
            border: 1px solid #dcdcdc;
            border-radius: 4px;
            padding: 0.75rem 1rem;
            font-size: 1rem;
            color: #333;
            width: 100%;
            background-color: #f9fafb;
        }

        /* Help text */
        .form-item-help {
            font-size: 0.875rem;
            color: #7f8c8d;
            margin-top: 0.5rem;
        }

        /* Form groups */
        .form-group {
            margin-bottom: 1rem;
        }

        /* Hide elements not needed in PDF */
        .no-print, button, .section-nav, input[type="submit"] {
            display: none !important;
        }

        /* Force background colors and borders to show in PDF */
        * {
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
        }

        /* Add page breaks before major sections */
        .form-section {
            page-break-before: auto;
            page-break-after: auto;
        }

        /* Ensure proper spacing */
        .space-y-4 > * + * {
            margin-top: 1rem;
        }
        .space-y-6 > * + * {
            margin-top: 1.5rem;
        }

        /* Section description */
        .section-description {
            color: #555;
            margin-bottom: 1rem;
            line-height: 1.5;
        }
    ''')

    # Generate PDF with base URL set to the static directory for loading assets
    HTML(string=html_content, base_url=static_dir).write_pdf(
        pdf_buffer,
        stylesheets=[pdf_css],
        optimize_size=('fonts', 'images')
    )

    # Prepare the response
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        download_name=f'submission_{submission_id}_{submission.submitted_at.strftime("%Y%m%d")}.pdf',
        as_attachment=True,
        mimetype='application/pdf'
    )


@bp.route('/sw.js')
@limiter.exempt
def service_worker():
    """Serve the service worker from the app root for proper scope.

    Injects ASSET_VERSION into the service worker file to keep cache versioning in sync.
    """
    try:
        # IMPORTANT: create_app() disables Flask's automatic static route by setting static_folder=None.
        # So current_app.static_folder is None here. Use the real static directory on disk instead.
        static_dir = os.path.join(current_app.root_path, 'static')
        sw_path = os.path.join(static_dir, 'js', 'sw.js')
        if not os.path.exists(sw_path):
            current_app.logger.error(f"Service worker file not found: {sw_path}")
            return "", 404

        # Read the service worker file
        with open(sw_path, 'r', encoding='utf-8') as f:
            sw_content = f.read()

        # Get per-boot asset version from config (set in create_app)
        cache_version = str(current_app.config.get('ASSET_VERSION') or 'v1')

        # Replace the placeholder with the actual version
        sw_content = sw_content.replace("'ASSET_VERSION_PLACEHOLDER'", f"'{cache_version}'")

        # Create response with injected version
        response = current_app.response_class(
            sw_content,
            mimetype='application/javascript'
        )
        # Allow browser revalidation without forcing full refetch on every request.
        # Service workers are still update-checked frequently by browsers.
        response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
        return response
    except Exception as e:
        current_app.logger.error(f"Error serving service worker: {e}")
        return "", 404


# === National Society Structure Management Routes ===
@bp.route("/ns_structure", methods=["GET"])
@login_required
def manage_ns_hierarchy():
    """Manage National Society hierarchy (branches, sub-branches, local units)"""
    from app.models import NSBranch, NSSubBranch, NSLocalUnit
    from flask import abort
    from app.services.authorization_service import AuthorizationService

    is_sys_mgr = AuthorizationService.is_system_manager(current_user)
    is_org_admin = AuthorizationService.has_rbac_permission(current_user, 'admin.organization.manage') or AuthorizationService.has_rbac_permission(current_user, 'admin.countries.view')
    is_focal_point = AuthorizationService.has_role(current_user, 'assignment_editor_submitter')

    # Allow org admins/system managers, and focal points scoped to their countries
    if not (is_sys_mgr or is_org_admin or is_focal_point):
        abort(403)

    # Filter data based on user scope
    if is_focal_point and not (is_sys_mgr or is_org_admin):
        # Get focal point's countries
        user_countries = list(current_user.countries.all()) if hasattr(current_user, 'countries') else []
        if not user_countries:
            # If focal point has no countries assigned, show empty page
            branches = []
            subbranches = []
            local_units = []
            countries = []
        else:
            # Filter entities by focal point's countries
            country_ids = [country.id for country in user_countries]
            branches = NSBranch.query.filter(NSBranch.country_id.in_(country_ids)).order_by(NSBranch.display_order, NSBranch.name).all()
            subbranches = NSSubBranch.query.join(NSBranch).filter(NSBranch.country_id.in_(country_ids)).order_by(NSSubBranch.display_order, NSSubBranch.name).all()
            local_units = NSLocalUnit.query.join(NSBranch).filter(NSBranch.country_id.in_(country_ids)).order_by(NSLocalUnit.display_order, NSLocalUnit.name).all()

            # Only show country selector if focal point has more than one country
            if len(user_countries) > 1:
                countries = user_countries
            else:
                countries = []
    else:
        # Admin and System Manager see all entities
        branches = NSBranch.query.order_by(NSBranch.display_order, NSBranch.name).all()
        subbranches = NSSubBranch.query.order_by(NSSubBranch.display_order, NSSubBranch.name).all()
        local_units = NSLocalUnit.query.order_by(NSLocalUnit.display_order, NSLocalUnit.name).all()

        # Get countries that have NS hierarchy data (branches, sub-branches, or local units)
        countries = db.session.query(Country).join(NSBranch).distinct().order_by(Country.name).all()

    return render_template("core/ns_structure.html",
                         branches=branches,
                         subbranches=subbranches,
                         local_units=local_units,
                         countries=countries,
                         title="NS Structure")

@bp.route('/manifest.webmanifest')
def manifest():
    """Serve dynamic web app manifest with organization branding"""
    from app.utils.app_settings import (
        get_organization_name,
        get_organization_short_name,
        get_organization_logo_path,
        get_organization_favicon_path,
    )
    from flask import jsonify

    org_name = get_organization_name()
    org_short_name = get_organization_short_name() or org_name[:15]  # Fallback to first 15 chars

    # Use logo from Settings > Branding > Visual Assets (fallback: favicon, then IFRC_logo_square.svg)
    icon_path = (
        get_organization_logo_path(default="").strip()
        or get_organization_favicon_path(default="").strip()
        or "IFRC_logo_square.svg"
    )
    # Ensure path is safe and served from /static/
    if icon_path.startswith("/"):
        icon_src = icon_path if icon_path.startswith("/static/") else "/static" + icon_path
    else:
        icon_src = "/static/" + icon_path.lstrip("/")

    # Set type and sizes based on file extension
    icon_path_lower = icon_path.lower()
    if icon_path_lower.endswith(".svg"):
        icon_type = "image/svg+xml"
        icon_sizes = "any"
    elif icon_path_lower.endswith(".png"):
        icon_type = "image/png"
        icon_sizes = "192x192"
    elif icon_path_lower.endswith((".jpg", ".jpeg")):
        icon_type = "image/jpeg"
        icon_sizes = "192x192"
    else:
        icon_type = "image/svg+xml"
        icon_sizes = "any"

    manifest_data = {
        "name": org_name,
        "short_name": org_short_name,
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ba0c2f",
        "icons": [
            {
                "src": icon_src,
                "sizes": icon_sizes,
                "type": icon_type,
            }
        ],
    }

    return jsonify(manifest_data), 200, {"Content-Type": "application/manifest+json"}
