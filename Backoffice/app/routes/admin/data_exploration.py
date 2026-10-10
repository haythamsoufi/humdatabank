# File: Backoffice/app/routes/admin/data_exploration.py
"""
Data Exploration Module - Explore form data with filters
"""

from functools import wraps
from flask import Blueprint, render_template, request, current_app, abort, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import distinct, func, and_, or_, tuple_
from sqlalchemy.orm import joinedload
from typing import Any, Dict, List
from app import db
from app.models import (
    FormTemplate, AssignedForm, Country, FormItem, FormData, AIFormDataValidation,
    AssignmentEntityStatus, FormSection, FormPage, PublicSubmission
)
from app.utils.api_responses import json_auth_required, json_bad_request, json_error, json_forbidden, json_not_found, json_ok, json_server_error
from app.utils.redirect_utils import get_current_relative_url
from app.utils.request_utils import is_json_request
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.routes.admin.shared import admin_required, permission_required, permission_required_any
from app.services.security.api_authentication import get_user_allowed_template_ids, _get_user_allowed_country_ids
from app.utils.datetime_helpers import utcnow
from app.services.organization.authorization_service import AuthorizationService
from app.plugins.data_explorer import (
    CORE_DATA_EXPLORER_PERMISSIONS,
    explore_tab_access_flags,
    manage_flag_key,
    resolve_explore_tab,
    tab_flag_key,
    user_can_read_disaggregation_template,
)
from app.plugins.manager import PluginManager
from app.services.data_quality.helpers import list_exploration_period_names
from app.utils.country_utils import exclude_sandbox_countries
from flask_babel import gettext as _
from markupsafe import Markup
import json
import logging

logger = logging.getLogger(__name__)
bp = Blueprint("data_exploration", __name__, url_prefix="/admin")

# FDRS template ID — default for Disaggregation Analysis
FDRS_TEMPLATE_ID = 21

# Data Explorer core permission codes (extension tabs add their own at runtime).
DATA_EXPLORER_PERMISSIONS = list(CORE_DATA_EXPLORER_PERMISSIONS)


def _plugin_manager() -> PluginManager:
    return current_app.plugin_manager


def _data_explorer_permissions() -> list[str]:
    try:
        return _plugin_manager().get_data_explorer_permission_codes()
    except Exception:
        return list(DATA_EXPLORER_PERMISSIONS)


def _ai_beta_denied_response():
    """Return a JSON error response when AI beta access is restricted for this user."""
    try:
        from app.services.platform.app_settings_service import is_ai_beta_restricted, user_has_ai_beta_access

        if not is_ai_beta_restricted():
            return None
        if not getattr(current_user, "is_authenticated", False):
            return json_forbidden("AI beta access is limited to selected users.")
        if not user_has_ai_beta_access(current_user):
            return json_forbidden("AI beta access is limited to selected users.")
    except Exception as e:
        logger.debug("data_exploration AI beta gate check failed: %s", e, exc_info=True)
    return None


def has_any_data_explorer_permission(user) -> bool:
    """Check if user has any Data Explorer permission."""
    if AuthorizationService.is_system_manager(user):
        return True
    for perm in _data_explorer_permissions():
        if AuthorizationService.has_rbac_permission(user, perm):
            return True
    return False


def _explore_tab_access_flags(user) -> dict[str, bool]:
    try:
        return explore_tab_access_flags(user, _plugin_manager())
    except Exception as exc:
        logger.debug("Extension tab flags fallback: %s", exc)
        is_sm = AuthorizationService.is_system_manager(user)
        return {
            'can_access_data_table': is_sm or AuthorizationService.has_rbac_permission(user, 'admin.data_explore.data_table'),
        }


def _explore_active_tab(flags: dict[str, bool], requested_tab: str | None = None) -> str:
    try:
        return resolve_explore_tab(flags, _plugin_manager(), requested_tab)
    except Exception as exc:
        logger.debug("Extension first-tab fallback: %s", exc)
        accessible = []
        if flags.get('can_access_data_table'):
            accessible.append('data-table')
        if requested_tab and requested_tab in accessible:
            return requested_tab
        if accessible:
            return accessible[0]
        return 'data-table'


def _explorer_extension_tabs_render(
    flags: dict[str, bool],
    first_tab: str,
    panels: dict[str, Markup],
) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    try:
        plugin_manager = _plugin_manager()
    except Exception:
        return rendered
    for tab in plugin_manager.get_data_explorer_tabs():
        if not flags.get(tab_flag_key(tab.tab_id)):
            continue
        rendered.append(
            {
                "tab_id": tab.tab_id,
                "label": tab.label,
                "icon": tab.icon,
                "can_manage": flags.get(manage_flag_key(tab.tab_id), False),
                "panel_html": panels.get(tab.tab_id, ""),
                "is_first": tab.tab_id == first_tab,
            }
        )
    return rendered


_PANEL_TEMPLATE_SUFFIXES = (".html", ".htm")


def _render_panel_template(panel_template: str, context: dict[str, Any]) -> Markup:
    """Render a plugin panel template and mark the result as trusted markup.

    This is the single trust boundary for plugin-contributed panels: the output is
    ``Markup`` only because it came from a Jinja template rendered with autoescaping
    (enforced here via the file suffix), so every ``{{ value }}`` inside the panel was
    already escaped. Panel templates must therefore never use ``|safe`` / ``Markup`` on
    request- or user-controlled data (see docs/DEVELOPER-HANDBOOK.md, plugin panels).
    """
    name = str(panel_template or "")
    if (
        not name.lower().endswith(_PANEL_TEMPLATE_SUFFIXES)
        or ".." in name.replace("\\", "/").split("/")
        or name.startswith(("/", "\\"))
    ):
        raise ValueError("Plugin panel_template must be a relative .html template path")
    return Markup(render_template(name, **context))


def _render_extension_panels(
    flags: dict[str, bool],
    first_tab: str,
    extra_context: dict[str, Any] | None = None,
) -> dict[str, Markup]:
    panels: dict[str, Markup] = {}
    try:
        plugin_manager = _plugin_manager()
    except Exception as exc:
        logger.debug("Extension panel render skipped: %s", exc)
        return panels

    for tab in plugin_manager.get_data_explorer_tabs():
        access_key = tab_flag_key(tab.tab_id)
        if not flags.get(access_key):
            continue
        context: dict[str, Any] = {
            'explore_first_tab': first_tab,
        }
        if extra_context:
            context.update(extra_context)
        context.update(plugin_manager.get_panel_render_context(tab.plugin_id, flags, first_tab))
        if tab.manage_requires_system_manager:
            context[manage_flag_key(tab.tab_id)] = flags.get(manage_flag_key(tab.tab_id), False)
        try:
            panels[tab.tab_id] = _render_panel_template(tab.panel_template, context)
        except Exception as exc:
            logger.error("Failed to render extension panel %s: %s", tab.tab_id, exc, exc_info=True)
            panels[tab.tab_id] = Markup("")
    return panels


def data_explorer_required(f):
    """
    Decorator that requires at least one Data Explorer permission.
    Used for the main explore_data page.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if is_json_request():
                return json_auth_required()
            flash("Access denied. Please log in.", "warning")
            return redirect(url_for("auth.login", next=get_current_relative_url()))
        if not has_any_data_explorer_permission(current_user):
            abort(403)
        return f(*args, **kwargs)
    # Metadata for startup-time guard auditing
    try:
        decorated_function._rbac_permissions_any_required = _data_explorer_permissions()  # type: ignore[attr-defined]
        decorated_function._rbac_permissions_required = list(getattr(f, "_rbac_permissions_required", []) or [])  # type: ignore[attr-defined]
        decorated_function._rbac_admin_required = bool(getattr(f, "_rbac_admin_required", False))  # type: ignore[attr-defined]
        decorated_function._rbac_system_manager_required = bool(getattr(f, "_rbac_system_manager_required", False))  # type: ignore[attr-defined]
    except Exception as e:
        logger.debug("data_explorer_required: metadata assignment failed: %s", e)
    return decorated_function

def _templates_for_disaggregation(templates, tab_flags):
    """Include FDRS in the analysis template list even when the user has no share."""
    if not tab_flags.get("can_access_disaggregation"):
        return templates
    if any(getattr(template, "id", None) == FDRS_TEMPLATE_ID for template in templates):
        return templates
    fdrs_template = (
        FormTemplate.query
        .options(joinedload(FormTemplate.published_version))
        .get(FDRS_TEMPLATE_ID)
    )
    if fdrs_template is None:
        return templates
    panel_templates = list(templates)
    panel_templates.append(fdrs_template)
    panel_templates.sort(key=lambda template: template.name if template.name else "")
    return panel_templates


# === Data Exploration Routes ===
@bp.route("/data-exploration", methods=["GET"])
@data_explorer_required
def explore_data():
    """Display data exploration page with filters for template and assignment."""
    try:
        tab_flags = _explore_tab_access_flags(current_user)
        requested_tab = request.args.get('tab')
        explore_first_tab = _explore_active_tab(tab_flags, requested_tab)
        # System managers can see all templates regardless of ownership and sharing
        # Use joinedload for published_version to avoid N+1 queries when accessing template.name
        if AuthorizationService.is_system_manager(current_user):
            templates = (
                FormTemplate.query
                .options(joinedload(FormTemplate.published_version))
                .all()
            )
        else:
            # Get templates that the user has access to (owned or shared)
            allowed_template_ids = get_user_allowed_template_ids(current_user.id)
            if allowed_template_ids:
                templates = (
                    FormTemplate.query
                    .filter(FormTemplate.id.in_(allowed_template_ids))
                    .options(joinedload(FormTemplate.published_version))
                    .all()
                )
            else:
                templates = []
        # Sort by name (from published version) in Python since it's a property
        # Note: published_version is already eager-loaded, avoiding N+1 queries
        templates.sort(key=lambda t: t.name if t.name else "")

        panel_context = {
            "templates": _templates_for_disaggregation(templates, tab_flags),
            "fdrs_template_id": FDRS_TEMPLATE_ID,
        }
        extension_panels = _render_extension_panels(
            tab_flags, explore_first_tab, panel_context
        )
        explorer_extension_tabs_render = _explorer_extension_tabs_render(
            tab_flags, explore_first_tab, extension_panels
        )

        # All periods with assignments or saved data (closed/deactivated included).
        period_names = list_exploration_period_names()

        # Get all countries for filter dropdown
        countries = Country.query.order_by(Country.name).all()

        return render_template("admin/data_exploration/explore_data.html",
                             templates=templates,
                             period_names=period_names,
                             countries=countries,
                             explore_first_tab=explore_first_tab,
                             extension_panels=extension_panels,
                             explorer_extension_tabs_render=explorer_extension_tabs_render,
                             fdrs_template_id=FDRS_TEMPLATE_ID,
                             title=_("Explore Data"),
                             **tab_flags)
    except Exception as e:
        logger.error(f"Error loading data exploration page: {str(e)}", exc_info=True)
        db.session.rollback()
        tab_flags = _explore_tab_access_flags(current_user)
        requested_tab = request.args.get('tab')
        explore_first_tab = _explore_active_tab(tab_flags, requested_tab)
        extension_panels = _render_extension_panels(
            tab_flags,
            explore_first_tab,
            {"templates": [], "fdrs_template_id": FDRS_TEMPLATE_ID},
        )
        explorer_extension_tabs_render = _explorer_extension_tabs_render(
            tab_flags, explore_first_tab, extension_panels
        )
        return render_template("admin/data_exploration/explore_data.html",
                             templates=[],
                             period_names=[],
                             countries=[],
                             explore_first_tab=explore_first_tab,
                             extension_panels=extension_panels,
                             explorer_extension_tabs_render=explorer_extension_tabs_render,
                             fdrs_template_id=FDRS_TEMPLATE_ID,
                             title=_("Explore Data"),
                             error="Failed to load filter options. Please refresh the page.",
                             **tab_flags)

@bp.route("/data-exploration/form-items", methods=["GET"])
@permission_required('admin.data_explore.data_table')
def get_form_items_for_template():
    """Get form items for a specific template."""
    try:
        template_id = request.args.get('template_id', type=int)

        if not template_id:
            return json_error('template_id is required', 400)

        logger.info(
            "Data Explorer: form-items request template_id=%s user_id=%s",
            template_id,
            getattr(current_user, "id", None),
        )

        # System managers have access to all templates
        if not AuthorizationService.is_system_manager(current_user):
            # Validate template exists and user has access
            allowed_template_ids = get_user_allowed_template_ids(current_user.id)
            if template_id not in allowed_template_ids:
                return json_forbidden('Forbidden: no access to requested template')

        template = FormTemplate.query.get(template_id)
        if not template:
            return json_not_found('Template not found')

        # IMPORTANT: Only return items for the published version (or earliest version fallback).
        # Templates can have multiple versions, and FormItem.template_id is denormalized across versions.
        # Without scoping by version_id, the dropdown can show "duplicates" (same label, different ids)
        # coming from different versions.
        version_id = None
        try:
            if getattr(template, "published_version_id", None):
                version_id = int(template.published_version_id)
            else:
                first_version = template.versions.order_by('created_at').first()
                if first_version and getattr(first_version, "id", None):
                    version_id = int(first_version.id)
        except Exception as e:
            logger.debug("version_id extraction failed: %s", e)
            version_id = None

        logger.info(
            "Data Explorer: form-items template_id=%s resolved_version_id=%s",
            template_id,
            version_id,
        )

        # Get form items for the template (load section, parent section, and page for full display order)
        q = (
            FormItem.query
            .options(
                joinedload(FormItem.form_section).options(
                    joinedload(FormSection.parent_section),
                    joinedload(FormSection.page),
                )
            )
            .filter_by(template_id=template_id, archived=False)
        )
        if version_id:
            q = q.filter(FormItem.version_id == int(version_id))
        form_items = q.order_by(FormItem.order).all()
        # Sort by template display order: page -> section hierarchy (parent then section) -> item order
        def _template_order_key(item):
            sec = item.form_section
            if not sec:
                return (0, 0, 0, float(item.order or 0))
            page = getattr(sec, 'page', None)
            page_order = int(page.order or 0) if page else 0
            parent = sec.parent_section
            parent_order = float((parent.order if parent else 0) or 0)
            sec_order = float(sec.order or 0)
            item_order = float(item.order or 0)
            return (page_order, parent_order, sec_order, item_order)
        form_items = sorted(form_items, key=_template_order_key)

        # Debug duplication signals (same ID should never repeat; labels may repeat depending on data)
        try:
            ids = [int(i.id) for i in form_items if getattr(i, "id", None) is not None]
            dup_ids = {v for v in ids if ids.count(v) > 1}
            if dup_ids:
                logger.warning(
                    "Data Explorer: duplicate FormItem IDs in query result template_id=%s dup_ids=%s",
                    template_id,
                    sorted(list(dup_ids))[:50],
                )

            labels = [str(i.label or "").strip() for i in form_items]
            dup_labels = sorted({v for v in labels if v and labels.count(v) > 1})[:25]
            if dup_labels:
                logger.info(
                    "Data Explorer: duplicate FormItem labels template_id=%s examples=%s",
                    template_id,
                    dup_labels,
                )
            logger.info(
                "Data Explorer: form-items response template_id=%s count=%s",
                template_id,
                len(form_items),
            )
        except Exception as e:
            logger.warning("Data Explorer: form-items debug logging failed: %s", e, exc_info=True)

        # Serialize form items with section/subsection, page, and order for dropdown (preserve template order)
        items_data = []
        for item in form_items:
            sec = item.form_section
            section_name = (sec.name if sec else None)
            parent_sec = (sec.parent_section if sec else None)
            parent_section_name = (parent_sec.name if parent_sec else None)
            parent_section_order = float(parent_sec.order or 0) if parent_sec else 0
            section_order = float(sec.order or 0) if sec else 0
            page = getattr(sec, 'page', None) if sec else None
            page_order = int(page.order or 0) if page else 0
            items_data.append({
                'item_id': item.id,
                'label': item.label,
                'item_type': item.item_type,
                'order': item.order,
                'section_id': item.section_id,
                'section_name': section_name,
                'parent_section_name': parent_section_name,
                'parent_section_order': parent_section_order,
                'section_order': section_order,
                'page_order': page_order,
            })

        return json_ok(form_items=items_data)
    except Exception as e:
        logger.error(f"Error loading form items for template {template_id}: {str(e)}", exc_info=True)
        return json_server_error('Failed to load form items')


@bp.route("/data-exploration/assignment-filters", methods=["GET"])
@permission_required_any(
    'admin.data_explore.data_table',
    'admin.data_explore.disaggregation',
    'admin.data_explore.analysis',
)
def get_assignment_filters_for_template():
    """Get assignment periods and countries for a specific template (for filter dropdowns)."""
    try:
        template_id = request.args.get('template_id', type=int)

        if not template_id:
            return json_error('template_id is required', 400)

        if not AuthorizationService.is_system_manager(current_user):
            if not user_can_read_disaggregation_template(current_user, template_id):
                allowed_template_ids = get_user_allowed_template_ids(current_user.id)
                if template_id not in allowed_template_ids:
                    return json_forbidden('Forbidden: no access to requested template')

        template = FormTemplate.query.get(template_id)
        if not template:
            return json_not_found('Template not found')

        # All periods for this template (closed/deactivated assignments and saved data included).
        period_names = list_exploration_period_names(template_id)

        # Distinct countries for this template (via AssignmentEntityStatus where entity_type='country')
        countries_query = (
            db.session.query(Country)
            .join(AssignmentEntityStatus, and_(
                AssignmentEntityStatus.entity_id == Country.id,
                AssignmentEntityStatus.entity_type == 'country'
            ))
            .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
            .filter(AssignedForm.template_id == template_id)
            .distinct()
            .order_by(Country.name)
        )
        countries_query = exclude_sandbox_countries(countries_query)
        countries = countries_query.all()
        countries_data = [{'id': c.id, 'name': c.name} for c in countries]

        return json_ok(period_names=period_names, countries=countries_data)
    except Exception as e:
        logger.error(f"Error loading assignment filters for template {template_id}: {str(e)}", exc_info=True)
        return json_server_error('Failed to load assignment filters')


def _parse_ai_opinion_ids(raw_ids: str | List[str]) -> tuple[List[int], List[tuple[int, int]], List[str]]:
    """
    Parse a comma-separated string or list of row ids into form_data_ids, missing_pairs, missing_keys.
    Ids can be numeric (FormData id) or virtual (m:<aes_id>:<form_item_id>).
    Returns (form_data_ids, missing_pairs, missing_keys) with deduplication applied.
    """
    if not raw_ids:
        return [], [], []
    if isinstance(raw_ids, list):
        parts = [str(p).strip() for p in raw_ids if p is not None and str(p).strip()]
    else:
        parts = [p.strip() for p in str(raw_ids).split(",") if (p or "").strip()]

    form_data_ids: List[int] = []
    missing_pairs: List[tuple[int, int]] = []
    missing_keys: List[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("m:"):
            try:
                _p = part.split(":")
                if len(_p) == 3:
                    aes_id = int(_p[1])
                    fi_id = int(_p[2])
                    if aes_id > 0 and fi_id > 0:
                        missing_pairs.append((aes_id, fi_id))
                        missing_keys.append(part)
                        continue
            except Exception as e:
                logger.debug("_parse_ai_opinion_ids: part parse failed for %r: %s", part, e)
        try:
            v = int(part)
            if v > 0:
                form_data_ids.append(v)
        except Exception as e:
            logger.debug("form_data_id int parse failed: %s", e)
            continue

    form_data_ids = list(dict.fromkeys(form_data_ids))
    seen_pairs = set()
    dedup_pairs: List[tuple[int, int]] = []
    dedup_keys: List[str] = []
    for k, pair in zip(missing_keys, missing_pairs):
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        dedup_pairs.append(pair)
        dedup_keys.append(k)
    return form_data_ids, dedup_pairs, dedup_keys


def _explorer_scope():
    """(unrestricted, allowed_template_ids, allowed_country_ids) for the current user.

    ``allowed_country_ids`` is None when country access is unrestricted; mirrors
    ``apply_user_template_scoping`` so row-level actions match what the Data Table can list.
    """
    if AuthorizationService.is_system_manager(current_user):
        return True, set(), None
    return (
        False,
        set(get_user_allowed_template_ids(current_user.id)),
        _get_user_allowed_country_ids(current_user),
    )


def _accessible_aes_ids(aes_ids) -> set:
    """Subset of assignment-entity-status ids the current user may explore/modify."""
    ids = {int(a) for a in (aes_ids or []) if a is not None}
    if not ids:
        return set()
    unrestricted, allowed_templates, allowed_countries = _explorer_scope()
    rows = (
        db.session.query(
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.entity_type,
            AssignmentEntityStatus.entity_id,
            AssignedForm.template_id,
        )
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(AssignmentEntityStatus.id.in_(ids))
        .all()
    )
    if unrestricted:
        return {int(r[0]) for r in rows}
    ok = set()
    for aes_id, entity_type, entity_id, template_id in rows:
        if template_id not in allowed_templates:
            continue
        if allowed_countries is not None and not (entity_type == "country" and entity_id in allowed_countries):
            continue
        ok.add(int(aes_id))
    return ok


def _accessible_form_data_ids(form_data_ids) -> set:
    """Subset of FormData ids (assigned or public) the current user may explore/modify."""
    ids = {int(f) for f in (form_data_ids or []) if f is not None}
    if not ids:
        return set()
    rows = (
        db.session.query(FormData.id, FormData.assignment_entity_status_id, FormData.public_submission_id)
        .filter(FormData.id.in_(ids))
        .all()
    )
    assigned_ok = _accessible_aes_ids([r[1] for r in rows if r[1] is not None])

    public_ids = {int(r[2]) for r in rows if r[2] is not None}
    public_ok = set()
    if public_ids:
        unrestricted, allowed_templates, allowed_countries = _explorer_scope()
        pub_rows = (
            db.session.query(PublicSubmission.id, PublicSubmission.country_id, AssignedForm.template_id)
            .join(AssignedForm, AssignedForm.id == PublicSubmission.assigned_form_id)
            .filter(PublicSubmission.id.in_(public_ids))
            .all()
        )
        for pub_id, country_id, template_id in pub_rows:
            if unrestricted or (
                template_id in allowed_templates
                and (allowed_countries is None or country_id in allowed_countries)
            ):
                public_ok.add(int(pub_id))

    return {
        int(fd_id)
        for fd_id, aes_id, pub_id in rows
        if (aes_id is not None and int(aes_id) in assigned_ok) or (pub_id is not None and int(pub_id) in public_ok)
    }


@bp.route("/data-exploration/ai-opinions", methods=["GET", "POST"])
@permission_required('admin.data_explore.data_table')
def get_ai_opinions_for_rows():
    """
    Fetch AI validation opinions for a set of row ids (single bulk query, no N+1).
    GET: query param ids=1,2,3,m:398:915
    POST: body { "ids": ["1", "2", "m:398:915"] } — use for large sets to avoid URL length limits.
    """
    try:
        denied = _ai_beta_denied_response()
        if denied is not None:
            return denied

        if request.method == "POST":
            payload = get_json_safe()
            raw_ids = payload.get("ids")
            if isinstance(raw_ids, list):
                form_data_ids, missing_pairs, missing_keys = _parse_ai_opinion_ids(raw_ids)
            else:
                form_data_ids, missing_pairs, missing_keys = _parse_ai_opinion_ids(
                    str(raw_ids) if raw_ids is not None else ""
                )
        else:
            raw_ids = (request.args.get("ids") or "").strip()
            form_data_ids, missing_pairs, missing_keys = _parse_ai_opinion_ids(raw_ids)

        if not form_data_ids and not missing_pairs:
            return json_ok(opinionsByFormDataId={})

        accessible_fd = _accessible_form_data_ids(form_data_ids)
        form_data_ids = [fid for fid in form_data_ids if fid in accessible_fd]
        accessible_aes = _accessible_aes_ids([pair[0] for pair in missing_pairs])
        kept = [(k, pair) for k, pair in zip(missing_keys, missing_pairs) if pair[0] in accessible_aes]
        missing_keys = [k for k, _pair in kept]
        missing_pairs = [pair for _k, pair in kept]

        opinions: List[AIFormDataValidation] = []
        if form_data_ids:
            opinions.extend(AIFormDataValidation.query.filter(AIFormDataValidation.form_data_id.in_(form_data_ids)).all())
        if missing_pairs:
            # latest-only is enforced via unique constraint (aes_id, form_item_id)
            q = (
                AIFormDataValidation.query
                .filter(AIFormDataValidation.form_data_id.is_(None))
                .filter(
                    tuple_(
                        AIFormDataValidation.assignment_entity_status_id,
                        AIFormDataValidation.form_item_id,
                    ).in_(missing_pairs)
                )
            )
            opinions.extend(q.all())

        by_form_data_id = {int(o.form_data_id): o for o in opinions if getattr(o, "form_data_id", None)}
        by_missing_pair = {
            (int(o.assignment_entity_status_id), int(o.form_item_id)): o
            for o in opinions
            if (getattr(o, "form_data_id", None) is None)
            and getattr(o, "assignment_entity_status_id", None) is not None
            and getattr(o, "form_item_id", None) is not None
        }

        def _serialize(o: AIFormDataValidation) -> dict:
            suggestion = None
            opinion_ui = None
            try:
                suggestion = (o.evidence or {}).get("suggestion") if isinstance(o.evidence, dict) else None
            except Exception as e:
                logger.debug("suggestion from evidence failed: %s", e)
                suggestion = None
            try:
                opinion_ui = (o.evidence or {}).get("opinion_ui") if isinstance(o.evidence, dict) else None
            except Exception as e:
                logger.debug("opinion_ui from evidence failed: %s", e)
                opinion_ui = None
            return {
                "id": int(o.id),
                "form_data_id": int(o.form_data_id) if o.form_data_id else None,
                "status": o.status,
                "verdict": o.verdict,
                "confidence": o.confidence,
                "opinion_text": o.opinion_text,
                "opinion_summary": (opinion_ui or {}).get("summary") if isinstance(opinion_ui, dict) else o.opinion_text,
                "opinion_details": (opinion_ui or {}).get("details") if isinstance(opinion_ui, dict) else None,
                "opinion_sources": (opinion_ui or {}).get("sources") if isinstance(opinion_ui, dict) else None,
                "opinion_basis": (opinion_ui or {}).get("basis") if isinstance(opinion_ui, dict) else None,
                "decision": (opinion_ui or {}).get("decision") if isinstance(opinion_ui, dict) else None,
                "provider": o.provider,
                "model": o.model,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
                "evidence": o.evidence,
                "suggestion": suggestion,
            }

        out: Dict[str, Any] = {}
        for fid in form_data_ids:
            o = by_form_data_id.get(int(fid))
            out[str(fid)] = _serialize(o) if o else None
        for key, pair in zip(missing_keys, missing_pairs):
            o = by_missing_pair.get(pair)
            out[str(key)] = _serialize(o) if o else None

        return json_ok(opinionsByFormDataId=out)
    except Exception as e:
        logger.error("Error fetching AI opinions: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/data-exploration/ai-validate", methods=["POST"])
@permission_required('admin.data_explore.data_table')
def run_ai_validation_for_rows():
    """
    Run AI validation for selected FormData rows.
    Body: { form_data_ids: [1,2,3] }
    """
    try:
        denied = _ai_beta_denied_response()
        if denied is not None:
            return denied

        payload = get_json_safe()
        sources = payload.get("sources", None)  # optional: ['historical','system_documents','upr_documents']

        # New shape (preferred): rows=[{row_id, form_data_id? or submission_id+form_item_id?}]
        rows = payload.get("rows")
        if rows is not None:
            if not isinstance(rows, list) or not rows:
                return json_bad_request("rows is required")
        else:
            # Legacy: form_data_ids=[1,2,3]
            ids = payload.get("form_data_ids") or []
            if not isinstance(ids, list) or not ids:
                return json_bad_request("rows (or form_data_ids) is required")
            rows = [{"row_id": v, "form_data_id": v} for v in ids]

        from app.services.ai.validation.formdata_validation import AIFormDataValidationService

        svc = AIFormDataValidationService()
        results: Dict[str, Any] = {}

        requested_fd_ids, requested_aes_ids = set(), set()
        for _row in rows:
            if not isinstance(_row, dict):
                continue
            try:
                if _row.get("form_data_id") is not None:
                    requested_fd_ids.add(int(_row["form_data_id"]))
                elif _row.get("submission_id") is not None:
                    requested_aes_ids.add(int(_row["submission_id"]))
            except (TypeError, ValueError):
                continue
        accessible_fd = _accessible_form_data_ids(requested_fd_ids)
        accessible_aes = _accessible_aes_ids(requested_aes_ids)

        def _serialize_rec(rec: AIFormDataValidation) -> Dict[str, Any]:
            suggestion = None
            opinion_ui = None
            try:
                suggestion = (rec.evidence or {}).get("suggestion") if isinstance(rec.evidence, dict) else None
            except Exception as e:
                logger.debug("suggestion extract failed: %s", e)
                suggestion = None
            try:
                opinion_ui = (rec.evidence or {}).get("opinion_ui") if isinstance(rec.evidence, dict) else None
            except Exception as e:
                logger.debug("opinion_ui extract failed: %s", e)
                opinion_ui = None
            return {
                "id": int(rec.id),
                "form_data_id": int(rec.form_data_id) if rec.form_data_id else None,
                "status": rec.status,
                "verdict": rec.verdict,
                "confidence": rec.confidence,
                "opinion_text": rec.opinion_text,
                "opinion_summary": (opinion_ui or {}).get("summary") if isinstance(opinion_ui, dict) else rec.opinion_text,
                "opinion_details": (opinion_ui or {}).get("details") if isinstance(opinion_ui, dict) else None,
                "opinion_sources": (opinion_ui or {}).get("sources") if isinstance(opinion_ui, dict) else None,
                "opinion_basis": (opinion_ui or {}).get("basis") if isinstance(opinion_ui, dict) else None,
                "decision": (opinion_ui or {}).get("decision") if isinstance(opinion_ui, dict) else None,
                "provider": rec.provider,
                "model": rec.model,
                "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
                "evidence": rec.evidence,
                "suggestion": suggestion,
            }

        for row in rows:
            try:
                row_id = row.get("row_id") if isinstance(row, dict) else None
                form_data_id = row.get("form_data_id") if isinstance(row, dict) else None

                fd_id_int = None
                try:
                    if form_data_id is not None:
                        fd_id_int = int(form_data_id)
                except Exception as e:
                    logger.debug("fd_id_int parse failed: %s", e)
                    fd_id_int = None

                if fd_id_int and fd_id_int not in accessible_fd:
                    raise PermissionError("You do not have access to this submission row.")
                if not fd_id_int and int(row.get("submission_id") or 0) not in accessible_aes:
                    raise PermissionError("You do not have access to this submission row.")

                if not fd_id_int:
                    # Missing/virtual row: do NOT create placeholder FormData rows.
                    # Only validate rows that already have a persisted FormData id.
                    submission_id = row.get("submission_id") if isinstance(row, dict) else None
                    form_item_id = row.get("form_item_id") if isinstance(row, dict) else None
                    if not submission_id or not form_item_id:
                        raise ValueError("Row is missing form_data_id and (submission_id, form_item_id)")
                    aes_id = int(submission_id)
                    fi_id = int(form_item_id)

                    existing_fd = (
                        FormData.query
                        .filter(FormData.assignment_entity_status_id == aes_id, FormData.form_item_id == fi_id)
                        .first()
                    )
                    if existing_fd:
                        fd_id_int = int(existing_fd.id)
                    else:
                        # Non-reported item: run suggestion-only validation WITHOUT creating FormData,
                        # but persist the opinion keyed by (assignment_entity_status_id, form_item_id).
                        row_key = str(row_id if row_id is not None else f"m:{aes_id}:{fi_id}")
                        rec, _vr = svc.upsert_missing_assigned_validation(
                            assignment_entity_status_id=int(aes_id),
                            form_item_id=int(fi_id),
                            run_by_user_id=int(current_user.id),
                            sources=sources,
                        )
                        payload = _serialize_rec(rec)
                        payload["row_id"] = row_key
                        results[row_key] = payload
                        continue

                rec, _ = svc.upsert_validation(
                    form_data_id=int(fd_id_int),
                    run_by_user_id=int(current_user.id),
                    sources=sources,
                )
                results[str(row_id if row_id is not None else fd_id_int)] = _serialize_rec(rec)
            except Exception as e:
                logger.warning("AI validation failed for row %s: %s", row, e, exc_info=True)
                key = None
                try:
                    key = str(row.get("row_id")) if isinstance(row, dict) and row.get("row_id") is not None else None
                except Exception as e:
                    logger.debug("row_id key extract failed: %s", e)
                    key = None
                results[str(key or "unknown")] = {
                    "status": "failed",
                    "verdict": "uncertain",
                    "opinion_text": f"Validation failed: {e}",
                }

        return json_ok(resultsByRowId=results, resultsByFormDataId=results)
    except Exception as e:
        logger.error("Error running AI validation: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@bp.route("/data-exploration/apply-imputed-value", methods=["POST"])
@permission_required('admin.data_explore.data_table')
@permission_required('admin.data_explore.impute')
def apply_imputed_value():
    """
    Apply an accepted AI-suggested value into FormData.imputed_value.
    Body:
      - { form_data_id: 123, imputed_value: <scalar or list for multi-choice> }
      - { form_data_id: 123, imputed_disagg_data: <any JSON-serializable> }
      - { submission_id: 398, form_item_id: 915, imputed_value: ..., ... }  # creates FormData row if missing
      - or both
    """
    try:
        denied = _ai_beta_denied_response()
        if denied is not None:
            return denied

        payload = get_json_safe()
        form_data_id = payload.get("form_data_id")
        submission_id = payload.get("submission_id")  # AES id
        form_item_id = payload.get("form_item_id")

        created = False

        # Resolve/validate target: either an existing FormData id, or an (AES, FormItem) pair.
        fd = None
        if form_data_id is not None and str(form_data_id).strip() != "":
            try:
                form_data_id = int(form_data_id)
            except Exception as e:
                logger.debug("form_data_id int parse failed: %s", e)
                return json_bad_request("form_data_id must be an integer")
            if form_data_id <= 0:
                return json_bad_request("form_data_id must be positive")
            fd = FormData.query.get(int(form_data_id))
            if not fd or int(fd.id) not in _accessible_form_data_ids([fd.id]):
                return json_not_found("FormData not found")
        else:
            try:
                submission_id = int(submission_id) if submission_id is not None else None
                form_item_id = int(form_item_id) if form_item_id is not None else None
            except Exception as e:
                logger.debug("submission_id/form_item_id parse failed: %s", e)
                return json_bad_request("submission_id and form_item_id must be integers")
            if not submission_id or not form_item_id:
                return json_bad_request("form_data_id or (submission_id and form_item_id) is required")

            if int(submission_id) not in _accessible_aes_ids([submission_id]):
                return json_not_found("Submission not found")
            target_template_id = (
                db.session.query(AssignedForm.template_id)
                .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
                .filter(AssignmentEntityStatus.id == int(submission_id))
                .scalar()
            )
            item_row = (
                db.session.query(FormItem.template_id, FormItem.version_id)
                .filter(FormItem.id == int(form_item_id))
                .first()
            )
            if item_row is None or item_row.template_id != target_template_id:
                return json_bad_request("form_item_id does not belong to this submission's template")
            live_version_id = (
                db.session.query(FormTemplate.published_version_id)
                .filter(FormTemplate.id == target_template_id)
                .scalar()
            )
            has_row = (
                db.session.query(FormData.id)
                .filter(
                    FormData.assignment_entity_status_id == int(submission_id),
                    FormData.form_item_id == int(form_item_id),
                )
                .first()
                is not None
            )
            if not has_row and live_version_id is not None and item_row.version_id != live_version_id:
                return json_bad_request(
                    "This field belongs to an older version of the template. Reload the page and try again."
                )

            fd = (
                FormData.query
                .filter(FormData.assignment_entity_status_id == int(submission_id), FormData.form_item_id == int(form_item_id))
                .first()
            )
            if not fd:
                # User-intent action: create a FormData row now (this is NOT a placeholder).
                fd = FormData(
                    assignment_entity_status_id=int(submission_id),
                    form_item_id=int(form_item_id),
                    created_at=utcnow(),
                    created_by_user_id=current_user.id if current_user.is_authenticated else None,
                )
                # Ensure a clean "empty reported value" baseline.
                fd.value = None
                fd.disagg_data = db.null()
                fd.prefilled_value = None
                fd.prefilled_disagg_data = db.null()
                fd.imputed_value = None
                fd.imputed_disagg_data = db.null()
                fd.data_not_available = False
                fd.not_applicable = False
                db.session.add(fd)
                db.session.flush()
                created = True

        imputed_value = payload.get("imputed_value", None)
        imputed_disagg_data = payload.get("imputed_disagg_data", None)

        def _has_payload_value(value):
            if value is None:
                return False
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, (list, dict)):
                return bool(value)
            return True

        # Require at least one of the two payloads
        has_scalar = _has_payload_value(imputed_value)
        has_disagg = _has_payload_value(imputed_disagg_data)
        if not has_scalar and not has_disagg:
            return json_bad_request("imputed_value or imputed_disagg_data is required")

        # Normalize common quoted-string artifacts from the frontend.
        # For single-choice questions, the stored value should be CHF (not "CHF").
        try:
            if isinstance(imputed_value, str):
                s = imputed_value.strip()
                # Treat literal "null" string as empty/missing
                if s.lower() == "null":
                    imputed_value = None

                # If the value itself looks like a JSON-encoded string (e.g. '"CHF"'),
                # decode it so we store CHF without extra quotes.
                if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
                    try:
                        decoded = json.loads(s)
                        if isinstance(decoded, str):
                            imputed_value = decoded
                    except Exception as e:
                        logger.debug("imputed_value decode failed: %s", e)
                        imputed_value = s[1:-1]

                # Also tolerate single-quoted values (rare)
                s2 = str(imputed_value).strip()
                if len(s2) >= 2 and s2[0] == "'" and s2[-1] == "'":
                    imputed_value = s2[1:-1]
        except Exception as e:
            logger.debug("imputed_value parse failed: %s", e)

        if isinstance(imputed_value, str):
            s = imputed_value.strip()
            if s.startswith("{") and s.endswith("}"):
                return json_bad_request("JSON object imputed payloads must be sent as imputed_disagg_data")
        if isinstance(imputed_value, dict):
            return json_bad_request("JSON object imputed payloads must be sent as imputed_disagg_data")
        if isinstance(imputed_value, list) and any(isinstance(item, (dict, list)) for item in imputed_value):
            return json_bad_request("Nested JSON imputed payloads must be sent as imputed_disagg_data")

        # Normalize imputed_disagg_data if sent as a JSON string
        try:
            if isinstance(imputed_disagg_data, str):
                s = imputed_disagg_data.strip()
                if s.lower() == "null" or s == "":
                    imputed_disagg_data = None
                elif (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                    imputed_disagg_data = json.loads(s)
        except Exception as e:
            logger.debug("imputed_disagg_data json parse failed: %s", e)

        # Only set fields that were actually provided (allows scalar-only or disagg-only applies).
        if "imputed_value" in payload:
            try:
                FormData.sync_imputed_numeric_value(fd, imputed_value)
            except ValueError as e:
                return json_bad_request(str(e))
        if "imputed_disagg_data" in payload:
            fd.imputed_disagg_data = imputed_disagg_data

        # If the user is imputing a value for a previously "missing" row (no FormData existed when AI ran),
        # we likely already have an AIFormDataValidation record keyed by (assignment_entity_status_id, form_item_id).
        # Once we create/resolve the persisted FormData row, link that opinion to the new form_data_id so future
        # lookups by FormData id keep showing the same opinion/suggestion.
        try:
            aes_id = None
            fi_id = None
            if getattr(fd, "assignment_entity_status_id", None) and getattr(fd, "form_item_id", None):
                aes_id = int(fd.assignment_entity_status_id)
                fi_id = int(fd.form_item_id)
            if aes_id and fi_id and getattr(fd, "id", None):
                existing_for_fd = AIFormDataValidation.query.filter_by(form_data_id=int(fd.id)).first()
                missing_rec = (
                    AIFormDataValidation.query
                    .filter(AIFormDataValidation.form_data_id.is_(None))
                    .filter(AIFormDataValidation.assignment_entity_status_id == int(aes_id))
                    .filter(AIFormDataValidation.form_item_id == int(fi_id))
                    .first()
                )
                if missing_rec:
                    if existing_for_fd:
                        # If both exist, keep the FormData-linked one and remove the virtual duplicate.
                        db.session.delete(missing_rec)
                    else:
                        # Migrate the virtual opinion to be keyed by persisted FormData id.
                        missing_rec.form_data_id = int(fd.id)
                        missing_rec.assignment_entity_status_id = None
                        missing_rec.form_item_id = None
                        missing_rec.updated_at = utcnow()
        except Exception as e:
            logger.debug("opinion linking failed (non-fatal): %s", e)
        db.session.commit()

        return json_ok(
            success=True,
            form_data_id=int(fd.id),
            created=bool(created),
            imputed_value=fd.imputed_value,
            imputed_disagg_data=getattr(fd, "imputed_disagg_data", None),
        )
    except Exception as e:
        logger.error("Error applying imputed value: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
