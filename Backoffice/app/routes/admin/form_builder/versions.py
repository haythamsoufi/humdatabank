"""Template versioning action routes."""

from flask import request, flash, redirect, url_for, current_app, render_template
from flask_babel import _
from flask_login import current_user
from sqlalchemy import func, select

from . import bp
from app import db
from app.models import FormTemplate, FormSection, FormItem, FormPage, FormTemplateVersion
from app.routes.admin.shared import permission_required, check_template_access
from app.services.platform.user_analytics_service import log_admin_action
from app.utils.transactions import request_transaction_rollback
from app.utils.datetime_helpers import utcnow
from app.utils.request_utils import get_request_data, is_json_request
from app.utils.api_responses import json_bad_request, json_server_error, json_ok, json_error
from .helpers import _clone_template_structure
from .helpers.field_mapping import (
    FieldMappingConflictError,
    FieldMappingValidationError,
    link_draft_item,
    link_draft_section,
    published_picker_items,
    published_picker_sections,
    unlink_draft_item,
    unlink_draft_section,
)


@bp.route("/templates/<int:template_id>/deploy", methods=["POST"])
@permission_required('admin.templates.publish')
def deploy_template_version(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version called for template_id={template_id}, user_id={current_user.id}")
    is_ajax = is_json_request()
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    deployed_version_id = None
    migration_summary = None
    prev_version_id = None
    try:
        target_version_id = get_request_data().get('version_id')
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
            msg = 'No target version specified and no draft version found to deploy.'
            if is_ajax:
                return json_bad_request(msg, success=False)
            flash(msg, 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        invalid_indicator_items = (
            FormItem.query
            .filter_by(template_id=template.id, version_id=version.id, item_type='indicator')
            .filter(FormItem.indicator_bank_id.is_(None))
            .count()
        )
        if invalid_indicator_items and invalid_indicator_items > 0:
            msg = (
                f"Cannot deploy this version: {invalid_indicator_items} indicator item(s) have missing/invalid indicator references. "
                f"Open the form builder, fix the items marked with an issue, then try deploying again."
            )
            if is_ajax:
                return json_bad_request(msg, success=False)
            flash(msg, "danger")
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version.id))

        if template.published_version_id and template.published_version_id != version.id:
            prev = FormTemplateVersion.query.get(template.published_version_id)
            if prev and prev.status == 'published':
                current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - archiving previous published version {prev.id}")
                prev.status = 'archived'
                prev.updated_at = utcnow()
                prev_version_id = prev.id

        current_app.logger.debug(f"VERSIONING_DEBUG: deploy_template_version - publishing version {version.id}, previous published_version_id={template.published_version_id}")
        version.status = 'published'
        version.updated_at = utcnow()
        template.published_version_id = version.id

        if prev_version_id:
            from app.services.platform.version_deploy_migration_service import (
                VersionDeployMigrationError,
                VersionDeployMigrationService,
            )
            try:
                migration_summary = VersionDeployMigrationService.migrate_submission_fks(
                    prev_version_id, version.id, template.id
                )
            except VersionDeployMigrationError as mig_err:
                request_transaction_rollback()
                msg = str(mig_err)
                if is_ajax:
                    return json_bad_request(msg, success=False)
                flash(msg, 'danger')
                return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=version.id))

        db.session.flush()

        # Evict cached section/item data for this template so the next form load
        # picks up the freshly published structure instead of stale rows.
        try:
            from app.services.templates.preparation_service import invalidate_sections_cache
            invalidate_sections_cache(template.id)
        except Exception as _ce:
            current_app.logger.debug("Section cache invalidation skipped: %s", _ce)

        try:
            audit_description = (
                f"Deployed version {version.version_number if hasattr(version, 'version_number') else version.id} "
                f"for template '{template.name}'"
            )
            if migration_summary:
                audit_description += (
                    f" (remapped_rows={migration_summary.get('remapped_rows', 0)}, "
                    f"orphaned_items={migration_summary.get('orphaned_items', 0)})"
                )
            log_admin_action(
                action_type='template_version_deploy',
                description=audit_description,
                target_type='form_template',
                target_id=template.id,
                target_description=f"Template ID: {template.id}, Version ID: {version.id}",
                risk_level='medium',
                new_values={
                    'deployed_version_id': version.id,
                    'previous_version_id': prev_version_id,
                    'stable_key_migration_summary': migration_summary,
                } if migration_summary else {
                    'deployed_version_id': version.id,
                    'previous_version_id': prev_version_id,
                },
            )
        except Exception as log_error:
            current_app.logger.error(f"Error logging version deployment: {log_error}")

        current_app.logger.info(f"VERSIONING_DEBUG: deploy_template_version - successfully deployed version {version.id} for template {template_id}")
        deployed_version_id = version.id
        if migration_summary and migration_summary.get('remapped_rows', 0) > 0:
            flash(
                f"Version deployed. {migration_summary['remapped_rows']} field value(s) carried forward; "
                f"{migration_summary.get('orphaned_items', 0)} removed field(s) retained on archived version.",
                'success',
            )
        else:
            flash('Version deployed successfully.', 'success')
    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deploying version for template {template_id}: {e}", exc_info=True)
        if is_ajax:
            return json_server_error("An error occurred. Please try again.", success=False)
        flash("An error occurred. Please try again.", "danger")

    if deployed_version_id:
        return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=deployed_version_id))
    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/deploy/preflight", methods=["GET"])
@permission_required('admin.templates.publish')
def deploy_template_preflight(template_id):
    """Return estimated submission FK remapping counts before deploy (read-only)."""
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        return json_bad_request('Access denied.', success=False)

    target_version_id = request.args.get('version_id', type=int)
    version = None
    if target_version_id:
        version = FormTemplateVersion.query.filter_by(
            id=target_version_id, template_id=template.id
        ).first()
    if not version:
        version = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
    if not version:
        return json_bad_request('No target version found.', success=False)

    prev_version_id = None
    if template.published_version_id and template.published_version_id != version.id:
        prev = FormTemplateVersion.query.get(template.published_version_id)
        if prev and prev.status == 'published':
            prev_version_id = prev.id

    from app.services.platform.version_deploy_migration_service import VersionDeployMigrationService
    from flask import current_app as app_ctx

    if not prev_version_id:
        estimate = VersionDeployMigrationService._empty_summary()
        estimate['remappable_rows'] = 0
    else:
        estimate = VersionDeployMigrationService.estimate_migration_counts(
            prev_version_id, version.id, template.id
        )

    threshold = app_ctx.config.get('DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD', 500000)
    remappable = estimate.get('remappable_rows', 0)
    mapping_summary = {}
    if prev_version_id:
        mapping_summary = VersionDeployMigrationService.count_field_mapping_summary(
            prev_version_id, version.id, template.id
        )
    return json_ok(
        success=True,
        estimate=estimate,
        show_latency_warning=remappable > threshold,
        threshold=threshold,
        mapping_summary=mapping_summary,
        field_mapping_url=url_for(
            'form_builder.field_mapping_review',
            template_id=template.id,
            version_id=version.id,
        ),
    )


def _resolve_draft_version_for_mapping(template, version_id: int):
    version = FormTemplateVersion.query.filter_by(
        id=version_id, template_id=template.id
    ).first_or_404()
    if version.status == 'published':
        return None, 'Field mapping is only available for draft versions.'
    return version, None


def _resolve_prev_published_version_id(template, draft_version_id: int):
    if not template.published_version_id or template.published_version_id == draft_version_id:
        return None
    prev = FormTemplateVersion.query.get(template.published_version_id)
    if prev and prev.status == 'published':
        return prev.id
    return None


@bp.route("/templates/<int:template_id>/versions/<int:version_id>/field-mapping", methods=["GET"])
@permission_required('admin.templates.publish')
def field_mapping_review(template_id, version_id):
    """Review draft vs published field identity before deploy."""
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        flash('Access denied.', 'warning')
        return redirect(url_for('form_builder.manage_templates'))

    draft_version, err = _resolve_draft_version_for_mapping(template, version_id)
    if err:
        flash(err, 'warning')
        return redirect(url_for('form_builder.edit_template', template_id=template.id))

    prev_version_id = _resolve_prev_published_version_id(template, draft_version.id)
    from app.services.platform.version_deploy_migration_service import VersionDeployMigrationService

    comparison_rows = []
    mapping_summary = {}
    if prev_version_id:
        comparison_rows = VersionDeployMigrationService.build_field_comparison(
            prev_version_id, draft_version.id, template.id
        )
        mapping_summary = VersionDeployMigrationService.count_field_mapping_summary(
            prev_version_id, draft_version.id, template.id
        )

    item_comparison_rows = [row for row in comparison_rows if row.get('entity_type') == 'item']
    section_comparison_rows = [row for row in comparison_rows if row.get('entity_type') == 'section']
    published_version = (
        FormTemplateVersion.query.get(prev_version_id) if prev_version_id else None
    )

    stat_counts = {
        'linked': sum(
            1 for row in item_comparison_rows
            if row.get('confidence') == 'exact' and row.get('draft_item')
        ),
        'suggested': mapping_summary.get('suggested_items', 0),
        'new': mapping_summary.get('unlinked_items', 0),
        'orphaned': sum(
            1 for row in item_comparison_rows if row.get('confidence') == 'orphaned'
        ),
        'needs_review': mapping_summary.get('suggested_items', 0),
    }

    return render_template(
        'forms/form_builder/field_mapping.html',
        title=_('Field mapping review'),
        template_obj=template,
        draft_version=draft_version,
        published_version=published_version,
        comparison_rows=comparison_rows,
        item_comparison_rows=item_comparison_rows,
        section_comparison_rows=section_comparison_rows,
        mapping_summary=mapping_summary,
        stat_counts=stat_counts,
        published_items=published_picker_items(template),
        published_sections=published_picker_sections(template),
        deploy_form_action=url_for('form_builder.deploy_template_version', template_id=template.id),
        builder_url=url_for(
            'form_builder.edit_template',
            template_id=template.id,
            version_id=draft_version.id,
        ),
    )


@bp.route(
    "/templates/<int:template_id>/versions/<int:version_id>/items/<int:item_id>/link",
    methods=["POST"],
)
@permission_required('admin.templates.publish')
def link_draft_item_route(template_id, version_id, item_id):
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        return json_bad_request('Access denied.', success=False)

    draft_version, err = _resolve_draft_version_for_mapping(template, version_id)
    if err:
        return json_bad_request(err, success=False)

    draft_item = FormItem.query.filter_by(
        id=item_id, template_id=template.id, version_id=draft_version.id
    ).first_or_404()

    data = get_request_data()
    published_stable_key = (data.get('published_stable_key') or '').strip()
    confirm_reassign = str(data.get('confirm_reassign', '')).lower() in ('1', 'true', 'yes')

    try:
        stable_key, warnings, displaced = link_draft_item(
            template=template,
            draft_version=draft_version,
            draft_item=draft_item,
            published_stable_key=published_stable_key,
            confirm_reassign=confirm_reassign,
        )
        db.session.commit()
        return json_ok(
            stable_key=stable_key,
            warnings=warnings,
            displaced_draft_item=displaced,
        )
    except FieldMappingConflictError as conflict:
        request_transaction_rollback()
        return json_error(
            str(conflict),
            status=409,
            success=False,
            conflict=True,
            existing_draft_item=conflict.existing_draft_item,
            published_item=conflict.published_item,
        )
    except FieldMappingValidationError as validation_err:
        request_transaction_rollback()
        return json_bad_request(str(validation_err), success=False)
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error('link_draft_item failed: %s', exc, exc_info=True)
        return json_server_error('An error occurred. Please try again.', success=False)


@bp.route(
    "/templates/<int:template_id>/versions/<int:version_id>/items/<int:item_id>/unlink",
    methods=["POST"],
)
@permission_required('admin.templates.publish')
def unlink_draft_item_route(template_id, version_id, item_id):
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        return json_bad_request('Access denied.', success=False)

    draft_version, err = _resolve_draft_version_for_mapping(template, version_id)
    if err:
        return json_bad_request(err, success=False)

    draft_item = FormItem.query.filter_by(
        id=item_id, template_id=template.id, version_id=draft_version.id
    ).first_or_404()

    try:
        stable_key = unlink_draft_item(
            template=template,
            draft_version=draft_version,
            draft_item=draft_item,
        )
        db.session.commit()
        return json_ok(stable_key=stable_key)
    except FieldMappingValidationError as validation_err:
        request_transaction_rollback()
        return json_bad_request(str(validation_err), success=False)
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error('unlink_draft_item failed: %s', exc, exc_info=True)
        return json_server_error('An error occurred. Please try again.', success=False)


@bp.route(
    "/templates/<int:template_id>/versions/<int:version_id>/sections/<int:section_id>/link",
    methods=["POST"],
)
@permission_required('admin.templates.publish')
def link_draft_section_route(template_id, version_id, section_id):
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        return json_bad_request('Access denied.', success=False)

    draft_version, err = _resolve_draft_version_for_mapping(template, version_id)
    if err:
        return json_bad_request(err, success=False)

    draft_section = FormSection.query.filter_by(
        id=section_id, template_id=template.id, version_id=draft_version.id
    ).first_or_404()

    data = get_request_data()
    published_stable_key = (data.get('published_stable_key') or '').strip()
    confirm_reassign = str(data.get('confirm_reassign', '')).lower() in ('1', 'true', 'yes')

    try:
        stable_key, warnings, displaced = link_draft_section(
            template=template,
            draft_version=draft_version,
            draft_section=draft_section,
            published_stable_key=published_stable_key,
            confirm_reassign=confirm_reassign,
        )
        db.session.commit()
        return json_ok(
            stable_key=stable_key,
            warnings=warnings,
            displaced_draft_section=displaced,
        )
    except FieldMappingConflictError as conflict:
        request_transaction_rollback()
        return json_error(
            str(conflict),
            status=409,
            success=False,
            conflict=True,
            existing_draft_section=conflict.existing_draft_section,
            published_section=conflict.published_section,
        )
    except FieldMappingValidationError as validation_err:
        request_transaction_rollback()
        return json_bad_request(str(validation_err), success=False)
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error('link_draft_section failed: %s', exc, exc_info=True)
        return json_server_error('An error occurred. Please try again.', success=False)


@bp.route(
    "/templates/<int:template_id>/versions/<int:version_id>/sections/<int:section_id>/unlink",
    methods=["POST"],
)
@permission_required('admin.templates.publish')
def unlink_draft_section_route(template_id, version_id, section_id):
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        return json_bad_request('Access denied.', success=False)

    draft_version, err = _resolve_draft_version_for_mapping(template, version_id)
    if err:
        return json_bad_request(err, success=False)

    draft_section = FormSection.query.filter_by(
        id=section_id, template_id=template.id, version_id=draft_version.id
    ).first_or_404()

    try:
        stable_key = unlink_draft_section(
            template=template,
            draft_version=draft_version,
            draft_section=draft_section,
        )
        db.session.commit()
        return json_ok(stable_key=stable_key)
    except FieldMappingValidationError as validation_err:
        request_transaction_rollback()
        return json_bad_request(str(validation_err), success=False)
    except Exception as exc:
        request_transaction_rollback()
        current_app.logger.error('unlink_draft_section failed: %s', exc, exc_info=True)
        return json_server_error('An error occurred. Please try again.', success=False)


@bp.route("/templates/<int:template_id>/discard_draft", methods=["POST"])
@permission_required('admin.templates.edit')
def discard_template_draft(template_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft called for template_id={template_id}, user_id={current_user.id}")
    is_ajax = is_json_request()
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))

    try:
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if not draft:
            current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - no draft version found for template_id={template_id}")
            msg = 'No draft version to discard.'
            if is_ajax:
                return json_bad_request(msg, success=False)
            flash(msg, 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleting draft version {draft.id} and associated rows")

        items_deleted = FormItem.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        sections_deleted = FormSection.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        pages_deleted = FormPage.query.filter_by(template_id=template.id, version_id=draft.id).delete(synchronize_session=False)
        current_app.logger.debug(f"VERSIONING_DEBUG: discard_template_draft - deleted {items_deleted} items, {sections_deleted} sections, {pages_deleted} pages")

        dependent_versions = FormTemplateVersion.query.filter_by(template_id=template.id, based_on_version_id=draft.id).all()
        if dependent_versions:
            current_app.logger.debug(
                f"VERSIONING_DEBUG: discard_template_draft - clearing based_on_version_id for {len(dependent_versions)} dependent versions: "
                f"{[v.id for v in dependent_versions]}"
            )
            for dep in dependent_versions:
                dep.based_on_version_id = None

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
        if is_ajax:
            return json_server_error("An error occurred. Please try again.", success=False)
        flash("An error occurred. Please try again.", "danger")

    return redirect(url_for("form_builder.edit_template", template_id=template.id))


@bp.route("/templates/<int:template_id>/versions/<int:version_id>/delete", methods=["POST"])
@permission_required('admin.templates.delete')
def delete_template_version(template_id, version_id):
    current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version called for template_id={template_id}, version_id={version_id}, user_id={current_user.id}")
    is_ajax = is_json_request()
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
            msg = 'Cannot delete the published version. Deploy another version first.'
            if is_ajax:
                return json_bad_request(msg, success=False)
            flash(msg, 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id))

        current_app.logger.debug(f"VERSIONING_DEBUG: delete_template_version - deleting version {version_id} and associated rows")

        from app.models import FormData, RepeatGroupData, RepeatGroupInstance, DynamicIndicatorData, DynamicSectionContext
        from app.models.documents import SubmittedDocument
        item_ids_subq = select(FormItem.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()
        section_ids_subq = select(FormSection.id).filter_by(template_id=template.id, version_id=version.id).scalar_subquery()

        data_counts = 0
        try:
            data_counts += db.session.query(func.count(FormData.id)).filter(FormData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupData.id)).filter(RepeatGroupData.form_item_id.in_(item_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(RepeatGroupInstance.id)).filter(RepeatGroupInstance.section_id.in_(section_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(DynamicIndicatorData.id)).filter(DynamicIndicatorData.section_id.in_(section_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(DynamicSectionContext.id)).filter(DynamicSectionContext.section_id.in_(section_ids_subq)).scalar() or 0
            data_counts += db.session.query(func.count(SubmittedDocument.id)).filter(SubmittedDocument.form_item_id.in_(item_ids_subq)).scalar() or 0
        except Exception as _e:
            current_app.logger.error(f"VERSIONING_DEBUG: delete_template_version - error counting dependent data: {_e}")
            data_counts = None

        if data_counts and data_counts > 0:
            current_app.logger.warning(
                f"VERSIONING_DEBUG: delete_template_version - aborting delete; dependent data rows found: {data_counts}"
            )
            msg = (
                f'Cannot delete this version: {data_counts} data record(s) are linked to its items or sections. '
                'Archive the version instead, or contact an administrator to remove the data first.'
            )
            if is_ajax:
                return json_bad_request(msg, success=False)
            flash(msg, 'warning')
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
        if is_ajax:
            return json_server_error("An error occurred. Please try again.", success=False)
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

        new_comment = get_request_data().get('comment') or None
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
    is_ajax = is_json_request()
    template = FormTemplate.query.get_or_404(template_id)
    if not check_template_access(template_id, current_user.id):
        current_app.logger.debug(f"VERSIONING_DEBUG: create_draft_version - access denied for template_id={template_id}, user_id={current_user.id}")
        flash("Access denied.", "warning")
        return redirect(url_for("form_builder.manage_templates"))
    try:
        existing_draft = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()
        if existing_draft:
            current_app.logger.warning(
                f"VERSIONING_DEBUG: create_draft_version - draft version {existing_draft.id} already exists for template_id={template_id}"
            )
            msg = (
                f'A draft version (V{existing_draft.version_number}) already exists. '
                'Open or discard it before creating a new version.'
            )
            if is_ajax:
                return json_bad_request(
                    msg,
                    success=False,
                    redirect_url=url_for(
                        "form_builder.edit_template",
                        template_id=template.id,
                        version_id=existing_draft.id,
                    ),
                )
            flash(msg, 'warning')
            return redirect(url_for("form_builder.edit_template", template_id=template.id, version_id=existing_draft.id))

        source_version_id = get_request_data().get('source_version_id', type=int)
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
            description_translations=source_version.description_translations.copy() if source_version.description_translations else None,
            description=source_version.description,
            add_to_self_report=source_version.add_to_self_report,
            display_order_visible=source_version.display_order_visible,
            is_paginated=source_version.is_paginated,
            enable_export_pdf=source_version.enable_export_pdf,
            enable_export_excel=source_version.enable_export_excel,
            enable_import_excel=source_version.enable_import_excel,
            enable_ai_validation=source_version.enable_ai_validation,
            enable_data_quality=source_version.enable_data_quality,
            data_quality_methodology=source_version.data_quality_methodology,
            validation_rule_pack=source_version.validation_rule_pack,
            variables=source_version.variables.copy() if source_version.variables else None,
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
        new_comment = get_request_data().get('comment') or None
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
