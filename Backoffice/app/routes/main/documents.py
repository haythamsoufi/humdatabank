from flask import render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user
from app.models.enums import EntityType
from app.services.organization.entity_service import EntityService
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY
from flask_babel import _
from config import Config
from app.utils.entity_groups import get_enabled_entity_groups
from app.utils.request_utils import is_top_level_navigation
from contextlib import suppress

from app.routes.main import bp
from app.routes.main.helpers import (
    SELECTED_ENTITY_TYPE_SESSION_KEY,
    SELECTED_ENTITY_ID_SESSION_KEY,
    _build_user_nav_entities,
    _document_modal_entity_choice_rows,
    _resolve_selected_entity_for_focal_nav,
)


@bp.route("/documents", methods=["GET", "POST"])
@login_required
def documents_submit():
    """
    Non-admin document library for focal users: documents for the **selected entity**
    (same session keys as the dashboard), including uploads by any user on that entity's
    assignments and standalone library rows linked to that entity.
    """
    from app.services.organization.authorization_service import AuthorizationService
    from app.services.platform.app_settings_service import get_document_types
    from app.routes.admin.content_management import _row_with_focal_entity_access

    if AuthorizationService.is_system_manager(current_user) or AuthorizationService.has_rbac_permission(
        current_user, "admin.documents.manage"
    ):
        return redirect(url_for("content_management.manage_documents"))

    if not AuthorizationService.has_role(current_user, "assignment_documents_uploader"):
        flash(_("Access denied."), "warning")
        return redirect(url_for("main.dashboard"))

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

    # GET is accepted so the switch carries no CSRF token that can go stale on
    # mobile; see the matching block in the dashboard route. GET has no CSRF
    # check, so require a real navigation rather than a cross-site subresource.
    if "entity_select" in request.values and (request.method == "POST" or is_top_level_navigation()):
        entity_select_value = request.values.get("entity_select", "")
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

    from app.services.documents.entity_repository_service import list_entity_repository_rows

    merged = list_entity_repository_rows(current_user, sel_type, sel_id)
    documents = [_row_with_focal_entity_access(r) for r in merged]

    show_entity_select = len(user_entities) > 1
    selected_entity_display_name = next(
        (e.get("display_name") for e in user_entities if e.get("entity_type") == sel_type and e.get("entity_id") == sel_id),
        None,
    )
    documents_page_subtitle = None
    if not show_entity_select:
        try:
            documents_page_subtitle = selected_entity_display_name or EntityService.get_localized_entity_name(
                sel_type, sel_id, include_hierarchy=True,
            )
        except Exception:
            documents_page_subtitle = None
    log_pfx = "[documents_submit]"
    current_app.logger.info(
        "%s user_id=%s entity=%s:%s merged=%s final_rows=%s show_entity_select=%s",
        log_pfx,
        getattr(current_user, "id", None),
        sel_type,
        sel_id,
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
        show_country_column=False,
        title=_("Document repository"),
        page_title=_("Document repository"),
        next_url=next_url,
        upload_action_url=url_for("content_management.upload_document", next=next_url),
        user_entities=user_entities,
        show_entity_select=show_entity_select,
        documents_page_subtitle=documents_page_subtitle,
        selected_entity=selected_entity,
        selected_entity_type=selected_entity_type,
        selected_entity_id=selected_entity_id,
        selected_entity_display_name=selected_entity_display_name,
        document_entity_types=document_entity_types,
        standalone_entity_options_url=url_for("content_management.standalone_document_entity_options"),
        documents_repo_team_pending_edit=True,
        documents_modal_lock_entity_to_nav=True,
        documents_modal_entity_choices=documents_modal_entity_choices,
    )
