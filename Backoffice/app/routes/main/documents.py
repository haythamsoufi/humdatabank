from flask import render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_required, current_user
from app.models import db, User, AssignedForm, Country, SubmittedDocument
from app.models.documents import submitted_document_countries
from app.models.assignments import AssignmentEntityStatus
from app.models.enums import EntityType
from app.services.entity_service import EntityService
from sqlalchemy import and_, or_, literal
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY
from datetime import datetime
from flask_babel import _
from config import Config
from app.utils.entity_groups import get_enabled_entity_groups
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
    from app.services.authorization_service import AuthorizationService
    from app.services.app_settings_service import get_document_types
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
