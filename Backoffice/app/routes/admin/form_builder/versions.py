"""Template versioning action routes."""

from flask import request, flash, redirect, url_for, current_app
from flask_login import current_user
from sqlalchemy import func, select

from . import bp
from app import db
from app.models import FormTemplate, FormSection, FormItem, FormPage, FormTemplateVersion
from app.routes.admin.shared import permission_required, check_template_access
from app.services.user_analytics_service import log_admin_action
from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from .helpers import _clone_template_structure


@bp.route("/templates/<int:template_id>/deploy", methods=["POST"])
@permission_required('admin.templates.publish')
def deploy_template_version(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        target_version_id = request.form.get('version_id')
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - target_version_id from form: {target_version_id}")
        version = None
        if target_version_id:
            try:
                version = FormTemplateVersion.query.filter_by(id=int(target_version_id), template_id=template.id).first()
                current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - found version by explicit ID: {version.id if version else None}")
            except Exception as e:
                current_app.logger.debug("deploy version_id parse failed: %s", e)
                version = None
        if not version:
            version = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
            current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - found draft version: {version.id if version else None}")
        if not version:
            current_app.logger.warning(f"VERSIONING_DEBUG: deploy_template_version - no target version found for template_id={template_id}")
            flash('No target version specified and no draft version found to deploy.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        invalid_indicator_items = (
            FormItem.query
            .filter_by(template_id=template.id, version_id=version.id, item_type='indicator')
            .filter(FormItem.indicator_bank_id.is_(None))
            .count()
        )
        if invalid_indicator_items and invalid_indicator_items > 0:
            flash(
                f"Cannot deploy this version: {invalid_indicator_items} indicator item(s) have missing/invalid indicator references. "
                f"Open the form builder, fix the items marked with an issue, then try deploying again.",
                "danger",
            )
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version.id))

        if template.published_version_id and template.published_version_id != version.id:
            prev = FormTemplateVersion.query.get(template.published_version_id)
            if prev and prev.status == 'published':
                current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - archiving previous published version {prev.id}")
                prev.status = 'archived'
                prev.updated_at = utcnow()

        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - publishing version {version.id}, previous published_version_id={template.published_version_id}")
        version.status = 'published'
        version.updated_at = utcnow()
        template.published_version_id = version.id

        db.session.flush()

        try:
            log_admin_action(
                action_type='template_version_deploy',
                description=f"Deployed version {version.version_number if hasattr(version, 'version_number') else version.id} for template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version.id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version deployment: {log_error}")

        try:
            from app.services.notification.core import notify_template_updated
            notify_template_updated(template)
        except Exception as e:
            current_app.logger.error(f"Error sending template updated notification: {e}", exc_info=True)

        current_app.logger.info(f"VERSIONING_DEBUG: deploy_template_version - successfully deployed version {version.id} for template {template_id}")
        flash('Version deployed successfully.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deploying version for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/discard_draft", methods=["POST"])
@permission_required('admin.templates.edit')
def discard_template_draft(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if not draft:
            current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - no draft version found for template_id={template_id}")
            flash('No draft version to discard.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleting draft version {draft.id} and associated rows")

        items_deleted = FormItem.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleted {items_deleted} items, {sections_deleted} sections, {pages_deleted} pages")

        db.session.delete(draft)
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: discard_template_draft - successfully discarded draft version {draft.id} for template {template_id}")

        try:
            log_admin_action(
                action_type='template_version_discard',
                description=f"Discarded draft version {draft.version_number if hasattr(draft, 'version_number') else draft.id} for template '{template.name}' (items={items_deleted}, sections={sections_deleted}, pages={pages_deleted})",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {draft.id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version discard: {log_error}")

        flash('Draft discarded.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error discarding draft for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/versions/<int:version_id>/delete", methods=["POST"])
@permission_required('admin.templates.delete')
def delete_template_version(template_id, version_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version called for template_id={template_id}, version_id={version_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first_or_404()
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - found version {version_id} with status={version.status}")

        if template.published_version_id == version.id:
            current_app.logger.warning(f"VERSIONING_DEBUG: delete_template_version - attempt to delete published version {version_id}")
            flash('Cannot delete the published version. Deploy another version first.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - deleting version {version_id} and associated rows")

        from app.models import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData
        item_ids_subq = select(FormItem.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()
        section_ids_subq = select(FormSection.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()

        data_counts = 0
        try:
            data_counts += db.session.query(func.count(FormData.id)).filter(FormData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupData.id)).filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupInstance.id)).filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(DynamicIndicatorData.id)).filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).scalar() or 0
        except Exception as _e:
            current_app.logger.error(f"VERSIONING_DEBUG: delete_template_version - error counting dependent data: {_e}")
            data_counts = None

        if data_counts and data_counts > 0:
            current_app.logger.warning(
                f"VERSIONING_DEBUG: delete_template_version - aborting delete; dependent data rows found: {data_counts}"
            )
            flash('Cannot delete this version because data exists for its items/sections. Remove data or archive the version.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        items_deleted = FormItem.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id, version_id=version.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - deleted {items_deleted} items, {sections_deleted} sections, {pages_deleted} pages")

        dependent_versions = FormTemplateVersion.query.filter_by(template_id=template.id, based_on_version_id=version.id).all()
        if dependent_versions:
            current_app.logger.debug(
                f"VERSIONING_DEBUG: delete_template_version - clearing based_on_version_id for {len(dependent_versions)} dependent versions: "
                f"{[v.id for v in dependent_versions]}"
            )
            for dep in dependent_versions:
                dep.based_on_version_id = None

        db.session.delete(version)
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: delete_template_version - successfully deleted version {version_id} for template {template_id}")

        try:
            log_admin_action(
                action_type='template_version_delete',
                description=f"Deleted version {version.version_number if hasattr(version, 'version_number') else version_id} for template '{template.name}' (items={items_deleted}, sections={sections_deleted})",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version_id}",
                risk_level='medium'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version deletion: {log_error}")

        flash('Version deleted.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting version {version_id} for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))

@bp.route("/templates/<int:template_id>/draft_comment", methods=["POST"])
@permission_required('admin.templates.edit')
def update_draft_comment(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if not draft:
            current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - no draft version found for template_id={template_id}")
            flash('No draft version to update.', 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        new_comment = request.form.get('comment') or None
        current_app.logger.debug(f"VERSIONING_DEBUG: update_draft_comment - updating draft {draft.id} comment from '{draft.comment}' to '{new_comment}'")
        draft.comment = new_comment
        draft.updated_at = utcnow()
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: update_draft_comment - successfully updated comment for draft {draft.id}")

        try:
            log_admin_action(
                action_type='template_version_comment',
                description=f"Updated comment for draft version {draft.version_number if hasattr(draft, 'version_number') else draft.id} of template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {draft.id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging draft comment update: {log_error}")

        flash('Draft note saved.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error saving draft note for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/versions/new", methods=["POST"])
@permission_required('admin.templates.edit')
def create_draft_version(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version called for template_id={template_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    try:
        source_version_id = request.form.get('source_version_id', type=int)
        source_version = None

        if source_version_id:
            source_version = FormTemplateVersion.query.filter_by(id=source_version_id, template_id=template.id).first()
            if not source_version:
                current_app.logger.warning(f"VERSIONING_DEBUG: create_draft_version - specified source_version_id {source_version_id} not found")
                flash('Source version not found.', 'warning')
                return redirect(url_for("form_builder.edit_template", template_id=template.id))

        if not source_version:
            if template.published_version_id:
                source_version = FormTemplateVersion.query.filter_by(id=template.published_version_id).first()
            else:
                source_version = FormTemplateVersion.query.filter_by(template_id=template.id).order_by(FormTemplateVersion.created_at.desc()).first()

            if not source_version:
                current_app.logger.warning(f"VERSIONING_DEBUG: create_draft_version - no version found to clone from for template_id={template_id}")
                flash('No version found to clone from.', 'warning')
                return redirect(url_for("form_builder.edit_template", template_id=template.id))

        max_version = db.session.query(func.max(FormTemplateVersion.version_number)).filter_by(template_id=template.id).scalar()
        next_version_number = (max_version + 1) if max_version else 1

        current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version - creating new draft from version {source_version.id}, version_number={next_version_number}")
        now = utcnow()
        draft = FormTemplateVersion(
            template_id=template.id,
            version_number=next_version_number,
            status='draft',
            based_on_version_id=source_version.id,
            created_by=current_user.id,
            updated_by=current_user.id,
            comment=None,
            created_at=now,
            updated_at=now,
            name=source_version.name,
            name_translations=source_version.name_translations.copy() if source_version.name_translations else None,
            description_translations=source_version.description_translations.copy() if source_version.description_translations else None
        )
        db.session.add(draft)
        db.session.flush()

        _clone_template_structure(template.id, source_version.id, draft.id)
        db.session.flush()

        current_app.logger.info(f"VERSIONING_DEBUG: create_draft_version - successfully created draft version {draft.id} for template {template_id} based on version {source_version.id}")

        try:
            log_admin_action(
                action_type='template_version_create',
                description=f"Created new draft version {draft.version_number} for template '{template.name}' based on version {source_version.version_number if hasattr(source_version, 'version_number') else source_version.id}",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, New Version ID: {draft.id}, Source Version ID: {source_version.id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version creation: {log_error}")

        flash('New version created.', 'success')
        return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=draft.id))
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error creating draft for template {template_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
        return redirect(url_for("form_builder.edit_template", template_id=template.id))

@bp.route("/templates/<int:template_id>/versions/<int:version_id>/comment", methods=["POST"])
@permission_required('admin.templates.edit')
def update_version_comment(template_id, version_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment called for template_id={template_id}, version_id={version_id}, user_id={current_user.id}")
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    try:
        version = FormTemplateVersion.query.filter_by(id=version_id, template_id=template.id).first_or_404()
        new_comment = request.form.get('comment') or None
        current_app.logger.debug(f"VERSIONING_DEBUG: update_version_comment - updating version {version_id} comment from '{version.comment}' to '{new_comment}'")
        version.comment = new_comment
        version.updated_at = utcnow()
        version.updated_by = current_user.id
        db.session.flush()
        current_app.logger.info(f"VERSIONING_DEBUG: update_version_comment - successfully updated comment for version {version_id}")

        try:
            log_admin_action(
                action_type='template_version_comment',
                description=f"Updated comment for version {version.version_number if hasattr(version, 'version_number') else version_id} of template '{template.name}'",
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version_id}",
                risk_level='low'
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version comment update: {log_error}")

        flash('Version note saved.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error saving version note for template {template_id}, version {version_id}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "danger")
    return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version_id))
