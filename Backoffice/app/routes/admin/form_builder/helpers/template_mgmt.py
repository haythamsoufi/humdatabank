"""Template management helpers (draft versioning, pages, sharing, access)."""

from flask import flash, current_app, redirect, url_for
from flask_login import current_user
from app import db
from app.models import (
    FormTemplate, FormPage, FormSection, FormItem, FormTemplateVersion, TemplateShare, User
)
from app.routes.admin.shared import check_template_access
from app.utils.user_analytics import log_admin_action
from app.utils.datetime_helpers import utcnow
from sqlalchemy import func
from config.config import Config
from .cloning import _clone_template_structure
import json


def _get_or_create_draft_version(template: FormTemplate, user_id: int) -> FormTemplateVersion:
    """Return existing draft version for template or create one.

    Behavior:
    - Brand-new templates (no versions and no rows): create a single draft (v1) and return it.
    - Legacy templates (rows exist with NULL version_id): create a published baseline, stamp rows,
      then create a draft cloned from published and return it.
    - Otherwise: if a draft exists, return it; if not, create a draft from the published version.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version called for template_id={template.id}, user_id={user_id}")
    draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
    if draft:
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - existing draft version {draft.id} found, returning it")
        return draft

    # Detect brand-new template state: no versions and no structural rows
    total_versions_for_template = FormTemplateVersion.query.filter_by(template_id=template.id).count()
    if total_versions_for_template == 0:
        pages_without_version = FormPage.query.filter_by(template_id=template.id, version_id=None).count()
        sections_without_version = FormSection.query.filter_by(template_id=template.id, version_id=None).count()
        items_without_version = FormItem.query.filter_by(template_id=template.id, version_id=None).count()

        if pages_without_version == 0 and sections_without_version == 0 and items_without_version == 0:
            # Brand-new template: create only a draft version (v1)
            now = utcnow()
            draft = FormTemplateVersion(
                template_id=template.id,
                version_number=1,
                status='draft',
                based_on_version_id=None,
                created_by=user_id,
                updated_by=user_id,
                comment=None,
                created_at=now,
                updated_at=now,
                name="Unnamed Template",  # Default name for new template
                name_translations=None,
                description=None,  # Default for new template
                add_to_self_report=False,  # Default for new template
                display_order_visible=False,  # Default for new template
                is_paginated=False,  # Default for new template
                enable_export_pdf=False,  # Default for new template
                enable_export_excel=False,  # Default for new template
                enable_import_excel=False,  # Default for new template
                enable_ai_validation=False  # Default for new template
            )
            db.session.add(draft)
            db.session.flush()
            current_app.logger.info(f"VERSIONING_DEBUG: _get_or_create_draft_version - created initial draft version {draft.id} for new template {template.id}")
            return draft

    # Ensure there is a published version (backfill migration should have created it)
    published = None
    if template.published_version_id:
        published = FormTemplateVersion.query.get(template.published_version_id)
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - found published version {published.id if published else None}")
    if not published:
        # As a safety net, create a published version and stamp current rows
        current_app.logger.warning(f"VERSIONING_DEBUG: _get_or_create_draft_version - no published version found, auto-creating one for template_id={template.id}")
        # Get the next version number for this template
        max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
        next_version_number = (max_version + 1) if max_version else 1

        now = utcnow()
        # Get name from first version if exists, otherwise use default
        first_version = template.versions.order_by('created_at').first()
        version_name = first_version.name if first_version and first_version.name else "Unnamed Template"
        version_translations = first_version.name_translations.copy() if first_version and first_version.name_translations else None
        version_desc_translations = first_version.description_translations.copy() if first_version and first_version.description_translations else None

        published = FormTemplateVersion(
            template_id=template.id,
            version_number=next_version_number,
            status='published',
            comment='Auto-created published baseline',
            created_by=user_id,
            updated_by=user_id,
            created_at=now,
            updated_at=now,
            name=version_name,
            name_translations=version_translations,
            description_translations=version_desc_translations
        )
        db.session.add(published)
        db.session.flush()
        # Stamp any rows missing version_id
        pages_updated = FormPage.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        sections_updated = FormSection.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        items_updated = FormItem.query.filter_by(template_id=template.id, version_id=None).update({'version_id': published.id})
        current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - auto-created published version {published.id}, stamped {pages_updated} pages, {sections_updated} sections, {items_updated} items")
        template.published_version_id = published.id
        db.session.flush()

    # Get the next version number for this template
    max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
    next_version_number = (max_version + 1) if max_version else 1

    # Create a new draft based on published and clone structure
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - creating new draft version based on published version {published.id}, version_number={next_version_number}")
    now = utcnow()
    draft = FormTemplateVersion(
        template_id=template.id,
        version_number=next_version_number,
        status='draft',
        based_on_version_id=published.id,
        created_by=user_id,
        updated_by=user_id,
        comment=None,
        created_at=now,
        updated_at=now,
        name=published.name,
        name_translations=published.name_translations.copy() if published.name_translations else None,
        description=published.description,
        description_translations=published.description_translations.copy() if published.description_translations else None,
        add_to_self_report=published.add_to_self_report,
        display_order_visible=published.display_order_visible,
        is_paginated=published.is_paginated,
        enable_export_pdf=published.enable_export_pdf,
        enable_export_excel=published.enable_export_excel,
        enable_import_excel=published.enable_import_excel,
        enable_ai_validation=published.enable_ai_validation
    )
    db.session.add(draft)
    db.session.flush()
    current_app.logger.debug(f"VERSIONING_DEBUG: _get_or_create_draft_version - cloning structure from version {published.id} to draft {draft.id}")
    _clone_template_structure(template.id, published.id, draft.id)
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: _get_or_create_draft_version - successfully created draft version {draft.id} for template {template.id}")
    return draft


def _handle_template_pages(template, form_data, version_id: int):
    """Handle template pages data processing"""
    page_ids = form_data.getlist('page_ids')
    page_names = form_data.getlist('page_names')
    page_orders = form_data.getlist('page_orders')
    page_name_translations = form_data.getlist('page_name_translations')

    # Create a set of existing page IDs for tracking deletions
    existing_pages = FormPage.query.filter_by(template_id=template.id, version_id=version_id).all()
    existing_page_ids = {str(page.id) for page in existing_pages}
    processed_page_ids = set()

    current_app.logger.debug(
        f"VERSIONING_DEBUG: _handle_template_pages - start template_id={template.id}, version_id={version_id}, "
        f"existing_pages={len(existing_pages)}, incoming_names={len(page_names)}"
    )

    # Process each page from the form
    for i in range(len(page_names)):
        page_id = page_ids[i] if i < len(page_ids) and page_ids[i] else None
        name = page_names[i]
        try:
            order = int(page_orders[i])
        except (ValueError, TypeError):
            order = i + 1

        # Handle page translations (ISO codes only)
        name_translations = None
        if i < len(page_name_translations) and page_name_translations[i]:
            try:
                parsed_translations = json.loads(page_name_translations[i])
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(parsed_translations, dict):
                    for k, v in parsed_translations.items():
                        if not (isinstance(k, str) and isinstance(v, str) and v.strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = v.strip()
                name_translations = filtered_translations if filtered_translations else None
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Error parsing page name translations: {e}")
                name_translations = None

        if page_id and page_id in existing_page_ids:
            # Update existing page
            try:
                page_pk = int(page_id)
            except Exception as e:
                current_app.logger.debug("page_id int parse failed: %s", e)
                page_pk = page_id
            page = FormPage.query.get(page_pk)
            if page:
                page.name = name
                page.order = order
                page.name_translations = name_translations
                processed_page_ids.add(page_id)
                current_app.logger.debug(
                    f"VERSIONING_DEBUG: _handle_template_pages - updated page id={page_id} name='{name}' order={order}"
                )
        else:
            # Create new page
            new_page = FormPage(
                template_id=template.id,
                version_id=version_id,
                name=name,
                order=order,
                name_translations=name_translations
            )
            db.session.add(new_page)
            current_app.logger.debug(
                f"VERSIONING_DEBUG: _handle_template_pages - creating new page name='{name}' order={order}"
            )

    # Delete pages that were removed from the form
    pages_to_delete = existing_page_ids - processed_page_ids
    if pages_to_delete:
        current_app.logger.debug(
            f"VERSIONING_DEBUG: _handle_template_pages - pages_to_delete={sorted(list(pages_to_delete))}"
        )
    for page_id in pages_to_delete:
        try:
            page_pk = int(page_id)
        except Exception as e:
            current_app.logger.debug("page_id int parse failed for %r: %s", page_id, e)
            page_pk = page_id
        page = FormPage.query.get(page_pk)
        if page:
            db.session.delete(page)
            current_app.logger.debug(
                f"VERSIONING_DEBUG: _handle_template_pages - deleted page id={page_id}"
            )


def _handle_template_sharing(template, shared_admin_ids, shared_by_user_id, template_name=None):
    """
    Handle template sharing by creating/updating TemplateShare records.

    Args:
        template: The FormTemplate object
        shared_admin_ids: List of user IDs to share the template with
        shared_by_user_id: ID of the user who is sharing the template
        template_name: Optional template name to avoid accessing template.name property
                       (useful during template creation when versions might not be fully persisted)
    """
    current_app.logger.debug(f"_handle_template_sharing called with template_id={template.id}, shared_admin_ids={shared_admin_ids}, shared_by_user_id={shared_by_user_id}")

    if not shared_admin_ids:
        shared_admin_ids = []

    # Get current sharing records for this template
    current_shares = TemplateShare.query.filter_by(template_id=template.id).all()
    current_shared_user_ids = {share.shared_with_user_id for share in current_shares}

    # Convert to set for easier comparison
    new_shared_user_ids = set(shared_admin_ids)

    # Remove shares that are no longer needed
    shares_to_remove = current_shared_user_ids - new_shared_user_ids
    for user_id in shares_to_remove:
        TemplateShare.query.filter_by(
            template_id=template.id,
            shared_with_user_id=user_id
        ).delete()

    # Add new shares
    shares_to_add = new_shared_user_ids - current_shared_user_ids
    for user_id in shares_to_add:
        # Don't share with the owner
        if user_id != template.owned_by:
            share = TemplateShare(
                template_id=template.id,
                shared_with_user_id=user_id,
                shared_by_user_id=shared_by_user_id
            )
            db.session.add(share)

    current_app.logger.info(f"Updated template sharing for template {template.id}: "
                          f"removed {len(shares_to_remove)}, added {len(shares_to_add)}")

    # Log admin action for audit trail if there were changes
    if shares_to_add or shares_to_remove:
        try:
            # Get user names for better audit trail description
            added_users = []
            removed_users = []
            if shares_to_add:
                added_users = User.query.filter(User.id.in_(shares_to_add)).all()
            if shares_to_remove:
                removed_users = User.query.filter(User.id.in_(shares_to_remove)).all()

            description_parts = []
            if added_users:
                added_names = [u.name or u.email for u in added_users]
                description_parts.append(f"Shared with: {', '.join(added_names)}")
            if removed_users:
                removed_names = [u.name or u.email for u in removed_users]
                description_parts.append(f"Removed access: {', '.join(removed_names)}")

            # Use provided template_name or fall back to template.name property
            # During template creation, template_name should be provided to avoid
            # accessing template.name which queries versions relationship
            name_to_use = template_name if template_name is not None else template.name

            log_admin_action(
                action_type='template_sharing_update',
                description=f"Updated sharing for template '{name_to_use}'. " + "; ".join(description_parts),
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Added: {len(shares_to_add)}, Removed: {len(shares_to_remove)}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging template sharing update: {log_error}")


def _populate_template_sharing(form, template):
    """
    Populate the owned_by and shared_with_admins fields with current sharing data.

    Args:
        form: The FormTemplateForm instance
        template: The FormTemplate object
    """
    # Populate the owner field
    form.owned_by.data = template.owned_by

    # Populate the shared users
    current_shares = TemplateShare.query.filter_by(template_id=template.id).all()
    shared_user_ids = [share.shared_with_user_id for share in current_shares]
    form.shared_with_admins.data = shared_user_ids


def _ensure_template_access_or_redirect(template_id, version_id=None):
    """Return redirect response if user lacks template access, otherwise None."""
    if check_template_access(template_id, current_user.id):
        return None

    flash("Access denied. You don't have permission to modify this template.", "warning")
    redirect_kwargs = {"template_id": template_id}
    if version_id:
        redirect_kwargs["version_id"] = version_id
    return redirect(url_for("form_builder.edit_template", **redirect_kwargs))
