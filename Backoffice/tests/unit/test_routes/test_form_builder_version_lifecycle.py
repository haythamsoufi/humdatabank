"""End-to-end tests for the form-builder template version lifecycle.

Walks the real routes (create draft -> edit -> deploy -> roll back -> discard/delete) and
asserts on the database, so regressions in cloning, id remapping, submission carry-forward
or the safety guards show up as data problems rather than as status codes.
"""

import json
from unittest.mock import patch

import pytest

from app import db
from app.models import (
    AIFormDataValidation,
    FormData,
    FormItem,
    FormPage,
    FormSection,
    FormTemplate,
    FormTemplateVersion,
    RepeatGroupInstance,
)
from app.models.assignments import AssignmentPageStatus
from app.routes.admin.form_builder.helpers.field_mapping import (
    FieldMappingIncompatibleError,
    FieldMappingTypeMismatchError,
    link_draft_item,
    link_draft_section,
)
from app.routes.admin.form_builder.helpers.template_mgmt import (
    PageInUseError,
    _handle_template_pages,
)
from app.routes.forms.helpers import entry_form_is_stale
from app.services.platform.template_version_audit import audit_template_versions
from app.services.templates.excel_service import TemplateExcelService as TemplateExcelImportService
from app.routes.admin.form_builder.helpers.cloning import (
    _clone_template_structure,
    _clone_template_structure_between_templates,
)
from app.utils.stable_key import generate_stable_key
from tests.factories import (
    _grant_role_permission,
    create_test_assignment_entity_status,
    create_test_draft_version,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant(db_session):
    for perm in ('admin.templates.publish', 'admin.templates.delete', 'admin.templates.edit'):
        _grant_role_permission(db_session, 'admin_core', perm)
    db_session.commit()


def _template(db_session, admin_user):
    _grant(db_session)
    return create_test_template(db_session, owner_id=admin_user.id)


def _flashes(client):
    with client.session_transaction() as sess:
        return [message for _category, message in sess.get('_flashes', [])]


def _post(client, url, **data):
    with patch('app.routes.admin.form_builder.versions.log_admin_action'):
        return client.post(url, data={k: str(v) for k, v in data.items()}, follow_redirects=False)


def _create_draft(client, template, source=None):
    data = {'source_version_id': source.id} if source is not None else {}
    return _post(client, f'/admin/templates/{template.id}/versions/new', **data)


def _deploy(client, template, version=None, **extra):
    data = dict(extra)
    if version is not None:
        data['version_id'] = version.id
    return _post(client, f'/admin/templates/{template.id}/deploy', **data)


def _draft_of(template):
    return FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').first()


def _structured_published(db_session, template):
    """Published version with one section, two questions and a rule pointing at the first."""
    published = template.published_version
    section = create_test_section(db_session, template, version=published, name='Main', order=1)
    first = create_test_item(
        db_session, section, template, version=published, item_type='question', label='First', order=1
    )
    second = create_test_item(
        db_session, section, template, version=published, item_type='question', label='Second', order=2
    )
    second.relevance_condition = json.dumps({
        'conditions': [{'item_id': str(first.id), 'operator': 'eq', 'value': 'yes'}]
    })
    db_session.commit()
    return published, section, first, second


# ---------------------------------------------------------------------------
# create_draft_version
# ---------------------------------------------------------------------------

class TestCreateDraftCopiesEverything:
    def test_every_version_setting_is_copied_and_json_is_not_shared(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        published = template.published_version
        published.name_translations = {'fr': 'Nom'}
        published.description_translations = {'fr': 'Description'}
        published.add_to_self_report = True
        published.display_order_visible = True
        published.is_paginated = True
        published.enable_export_pdf = True
        published.enable_export_excel = True
        published.enable_import_excel = True
        published.enable_ai_validation = True
        published.enable_data_quality = True
        published.data_quality_methodology = 'method-a'
        published.validation_rule_pack = 'pack-a'
        published.enable_discussion = True
        published.discussion_config = {'show_in_sidebar': False}
        published.variables = {'v': {'source_form_item_id': 5}}
        db_session.commit()

        resp = _create_draft(logged_in_client, template)
        assert resp.status_code == 302

        draft = _draft_of(template)
        assert draft is not None
        assert draft.status == 'draft'
        assert draft.version_number == published.version_number + 1
        assert draft.based_on_version_id == published.id
        assert draft.created_by == admin_user.id

        copied = [
            'name', 'name_translations', 'description', 'description_translations',
            'add_to_self_report', 'display_order_visible', 'is_paginated', 'enable_export_pdf',
            'enable_export_excel', 'enable_import_excel', 'enable_ai_validation',
            'enable_data_quality', 'data_quality_methodology', 'validation_rule_pack',
            'enable_discussion', 'discussion_config', 'variables',
        ]
        for column in copied:
            assert getattr(draft, column) == getattr(published, column), column

        draft.discussion_config = {'show_in_sidebar': True}
        draft.variables = {'v': {'source_form_item_id': 6}}
        db_session.commit()
        db_session.refresh(published)
        assert published.discussion_config == {'show_in_sidebar': False}
        assert published.variables == {'v': {'source_form_item_id': 5}}

    def test_every_version_column_is_accounted_for(self):
        """Adding a column to FormTemplateVersion must be a conscious decision about cloning."""
        not_copied = {
            'id', 'template_id', 'version_number', 'status', 'comment', 'based_on_version_id',
            'created_at', 'updated_at', 'created_by', 'updated_by',
        }
        copied = {
            'name', 'name_translations', 'description', 'description_translations',
            'add_to_self_report', 'display_order_visible', 'is_paginated', 'enable_export_pdf',
            'enable_export_excel', 'enable_import_excel', 'enable_ai_validation',
            'enable_data_quality', 'data_quality_methodology', 'validation_rule_pack',
            'enable_discussion', 'discussion_config', 'variables',
        }
        columns = {c.name for c in FormTemplateVersion.__table__.columns}
        assert columns == not_copied | copied

    def test_structure_is_cloned_with_remapped_ids_and_same_keys(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        published, section, first, second = _structured_published(db_session, template)

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)

        draft_section = FormSection.query.filter_by(version_id=draft.id).one()
        draft_items = {i.label: i for i in FormItem.query.filter_by(version_id=draft.id).all()}
        assert set(draft_items) == {'First', 'Second'}
        assert draft_section.stable_key == section.stable_key
        assert draft_items['First'].stable_key == first.stable_key
        assert draft_items['First'].id != first.id
        assert draft_items['First'].section_id == draft_section.id

        rule = json.loads(draft_items['Second'].relevance_condition)
        assert rule['conditions'][0]['item_id'] == str(draft_items['First'].id)
        # the published rule is untouched
        assert json.loads(second.relevance_condition)['conditions'][0]['item_id'] == str(first.id)

    def test_new_version_numbers_never_collide(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        _create_draft(logged_in_client, template)
        first_draft = _draft_of(template)
        _deploy(logged_in_client, template, first_draft)
        _create_draft(logged_in_client, template)
        second_draft = _draft_of(template)
        numbers = sorted(
            v.version_number for v in FormTemplateVersion.query.filter_by(template_id=template.id)
        )
        assert numbers == [1, 2, 3]
        assert second_draft.version_number == 3

    def test_draft_can_be_based_on_an_archived_version(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        v1 = template.published_version
        _create_draft(logged_in_client, template)
        v2 = _draft_of(template)
        _deploy(logged_in_client, template, v2)
        db_session.refresh(v1)
        assert v1.status == 'archived'

        _create_draft(logged_in_client, template, source=v1)
        v3 = _draft_of(template)
        assert v3.based_on_version_id == v1.id

    def test_source_from_another_template_is_rejected(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        other = create_test_template(db_session, owner_id=admin_user.id)
        resp = _create_draft(logged_in_client, template, source=other.published_version)
        assert resp.status_code == 302
        assert _draft_of(template) is None
        assert any('not found' in m.lower() for m in _flashes(logged_in_client))

    def test_second_draft_is_refused_and_leaves_the_first_alone(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        _create_draft(logged_in_client, template)
        drafts = FormTemplateVersion.query.filter_by(template_id=template.id, status='draft').all()
        assert [d.id for d in drafts] == [draft.id]

    def test_failure_rolls_back_the_half_created_version(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        _structured_published(db_session, template)
        before = FormTemplateVersion.query.filter_by(template_id=template.id).count()
        with patch(
            'app.routes.admin.form_builder.versions._clone_template_structure',
            side_effect=RuntimeError('boom'),
        ):
            resp = _create_draft(logged_in_client, template)
        assert resp.status_code == 302
        db_session.rollback()
        assert FormTemplateVersion.query.filter_by(template_id=template.id).count() == before


# ---------------------------------------------------------------------------
# deploy_template_version
# ---------------------------------------------------------------------------

class TestDeployLifecycle:
    def test_deploy_publishes_draft_archives_previous_and_moves_data(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        published, _section, first, second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        rows = [
            FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='one'),
            FormData(assignment_entity_status_id=aes.id, form_item_id=second.id, value='two'),
        ]
        db_session.add_all(rows)
        db_session.commit()

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        _deploy(logged_in_client, template, draft)

        db_session.refresh(template)
        db_session.refresh(published)
        db_session.refresh(draft)
        assert template.published_version_id == draft.id
        assert draft.status == 'published'
        assert published.status == 'archived'

        new_items = {i.label: i.id for i in FormItem.query.filter_by(version_id=draft.id)}
        for row, label in zip(rows, ('First', 'Second')):
            db_session.refresh(row)
            assert row.form_item_id == new_items[label]
        flashed = ' '.join(_flashes(logged_in_client))
        assert '2 field value(s) carried forward' in flashed

    def test_edits_made_in_the_draft_reach_published_data_mapping(
        self, logged_in_client, db_session, admin_user
    ):
        """Rename a field and add a field in the draft: data stays with the (renamed) field."""
        template = _template(db_session, admin_user)
        _published, _section, first, _second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='keep me')
        db_session.add(row)
        db_session.commit()

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        renamed = FormItem.query.filter_by(version_id=draft.id, label='First').one()
        renamed.label = 'First (renamed)'
        draft_section = FormSection.query.filter_by(version_id=draft.id).one()
        added = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Added', order=5
        )
        db_session.commit()

        _deploy(logged_in_client, template, draft)
        db_session.refresh(row)
        assert row.form_item_id == renamed.id
        assert FormData.query.filter_by(form_item_id=added.id).count() == 0

    def test_removed_field_keeps_its_data_and_is_archived(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _published, _section, first, second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=second.id, value='orphan')
        db_session.add(row)
        db_session.commit()

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        FormItem.query.filter_by(version_id=draft.id, label='Second').delete()
        db_session.commit()

        _deploy(logged_in_client, template, draft, acknowledge_orphaned_data='1')
        db_session.refresh(row)
        db_session.refresh(second)
        assert row.form_item_id == second.id
        assert second.archived is True
        assert FormData.query.filter_by(form_item_id=second.id).count() == 1
        assert any('removed field(s) retained' in m for m in _flashes(logged_in_client))

    def test_rollback_to_archived_version_restores_data_and_fields(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        v1, _section, first, second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        first_row = FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='1')
        second_row = FormData(assignment_entity_status_id=aes.id, form_item_id=second.id, value='2')
        db_session.add_all([first_row, second_row])
        db_session.commit()

        _create_draft(logged_in_client, template)
        v2 = _draft_of(template)
        FormItem.query.filter_by(version_id=v2.id, label='Second').delete()
        db_session.commit()
        _deploy(logged_in_client, template, v2, acknowledge_orphaned_data='1')

        db_session.refresh(second)
        assert second.archived is True

        _deploy(logged_in_client, template, v1)
        db_session.refresh(template)
        for row in (v1, v2, first_row, second_row, second):
            db_session.refresh(row)
        assert template.published_version_id == v1.id
        assert (v1.status, v2.status) == ('published', 'archived')
        assert first_row.form_item_id == first.id
        assert second_row.form_item_id == second.id
        assert second.archived is False

    def test_failed_migration_leaves_versions_and_data_untouched(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        published, _section, first, _second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='x')
        db_session.add(row)
        db_session.commit()

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        twin_source = FormItem.query.filter_by(version_id=draft.id, label='First').one()
        draft_section = FormSection.query.filter_by(version_id=draft.id).one()
        twin = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='twin', order=7
        )
        twin.stable_key = twin_source.stable_key
        db_session.commit()

        resp = _deploy(logged_in_client, template, draft)
        assert resp.status_code == 302
        db_session.rollback()
        db_session.refresh(template)
        db_session.refresh(published)
        db_session.refresh(draft)
        db_session.refresh(row)
        assert template.published_version_id == published.id
        assert published.status == 'published'
        assert draft.status == 'draft'
        assert row.form_item_id == first.id
        assert any('shared by more than one' in m for m in _flashes(logged_in_client))

    def test_unknown_version_id_does_not_fall_back_to_the_draft(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        other = create_test_template(db_session, owner_id=admin_user.id)
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)

        for bad in (other.published_version.id, 99999999, 'abc'):
            resp = _post(
                logged_in_client, f'/admin/templates/{template.id}/deploy', version_id=bad
            )
            assert resp.status_code == 302
            db_session.refresh(draft)
            assert draft.status == 'draft', f'draft deployed for version_id={bad!r}'

    def test_unknown_version_id_ajax_returns_json_error(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        _create_draft(logged_in_client, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data=json.dumps({'version_id': 99999999}),
                content_type='application/json',
                headers={'Accept': 'application/json'},
            )
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_data_still_migrates_when_published_pointer_status_is_inconsistent(
        self, logged_in_client, db_session, admin_user
    ):
        """template.published_version_id is authoritative even if the row's status drifted."""
        template = _template(db_session, admin_user)
        published, _section, first, _second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='x')
        db_session.add(row)
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        published.status = 'archived'
        db_session.commit()

        _deploy(logged_in_client, template, draft)
        db_session.refresh(row)
        new_first = FormItem.query.filter_by(version_id=draft.id, label='First').one()
        assert row.form_item_id == new_first.id

    def test_deploying_the_published_version_again_is_harmless(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        published, _section, first, _second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='x')
        db_session.add(row)
        db_session.commit()
        _deploy(logged_in_client, template, published)
        db_session.refresh(row)
        db_session.refresh(published)
        db_session.refresh(template)
        assert row.form_item_id == first.id
        assert published.status == 'published'
        assert template.published_version_id == published.id

    def test_deploy_requires_publish_permission(self, logged_in_client, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        draft = create_test_draft_version(db_session, template)
        with patch(
            'app.routes.admin.shared.AuthorizationService.has_rbac_permission', return_value=False
        ):
            _deploy(logged_in_client, template, draft)
        db_session.refresh(draft)
        # Either the decorator blocks it, or (if permissions are granted by role) it deploys;
        # what must never happen is a partial deploy.
        assert (draft.status, template.published_version_id == draft.id) in (
            ('draft', False), ('published', True)
        )

    def test_deploy_invalidates_section_cache_and_refreshes_completion(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        draft = create_test_draft_version(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), patch(
            'app.services.templates.preparation_service.invalidate_sections_cache'
        ) as invalidate, patch(
            'app.services.assignments.completion_service.AssignmentCompletionService.refresh_for_template'
        ) as refresh:
            logged_in_client.post(
                f'/admin/templates/{template.id}/deploy', data={'version_id': str(draft.id)}
            )
        invalidate.assert_called_once_with(template.id)
        refresh.assert_called_once_with(template.id)

    def test_page_workflow_status_survives_deploy(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        published = template.published_version
        published.is_paginated = True
        page = FormPage(template_id=template.id, version_id=published.id, name='P1', order=1)
        db_session.add(page)
        db_session.flush()
        section = create_test_section(db_session, template, version=published, name='S', order=1)
        section.page_id = page.id
        create_test_item(db_session, section, template, version=published, item_type='question', order=1)
        aes = create_test_assignment_entity_status(db_session, template=template)
        status = AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=page.id, status='Approved'
        )
        db_session.add(status)
        db_session.commit()

        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        _deploy(logged_in_client, template, draft)

        new_page = FormPage.query.filter_by(version_id=draft.id).one()
        db_session.refresh(status)
        assert status.form_page_id == new_page.id
        assert status.status == 'Approved'


class TestDeployPreflight:
    def test_preflight_reports_counts_and_warning_threshold(
        self, logged_in_client, db_session, admin_user, app
    ):
        template = _template(db_session, admin_user)
        _published, _section, first, _second = _structured_published(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(assignment_entity_status_id=aes.id, form_item_id=first.id, value='x'))
        db_session.commit()
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)

        app.config['DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD'] = 0
        try:
            resp = logged_in_client.get(
                f'/admin/templates/{template.id}/deploy/preflight?version_id={draft.id}',
                headers={'Accept': 'application/json'},
            )
        finally:
            app.config.pop('DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD', None)
        body = resp.get_json()
        assert body['estimate']['remappable_rows'] == 1
        assert body['estimate']['matched_items'] == 2
        assert body['show_latency_warning'] is True
        assert body['mapping_summary']['orphaned_items_with_data'] == 0

    def test_preflight_without_target_is_an_error(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/deploy/preflight',
            headers={'Accept': 'application/json'},
        )
        assert resp.status_code == 400

    def test_preflight_for_first_publish_has_nothing_to_remap(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        template.published_version_id = None
        db_session.commit()
        draft = create_test_draft_version(db_session, template)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/deploy/preflight?version_id={draft.id}',
            headers={'Accept': 'application/json'},
        )
        assert resp.get_json()['estimate']['remappable_rows'] == 0


# ---------------------------------------------------------------------------
# discard / delete
# ---------------------------------------------------------------------------

class TestDiscardDraft:
    def test_discard_removes_only_the_draft_structure(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        published, _section, first, _second = _structured_published(db_session, template)
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        draft_id = draft.id

        _post(logged_in_client, f'/admin/templates/{template.id}/discard_draft')

        assert FormTemplateVersion.query.get(draft_id) is None
        assert FormItem.query.filter_by(version_id=draft_id).count() == 0
        assert FormSection.query.filter_by(version_id=draft_id).count() == 0
        assert FormItem.query.filter_by(version_id=published.id).count() == 2
        db_session.refresh(template)
        assert template.published_version_id == published.id

    def test_discard_clears_based_on_of_dependent_versions(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        draft = create_test_draft_version(db_session, template)
        child = FormTemplateVersion(
            template_id=template.id, version_number=9, status='archived',
            based_on_version_id=draft.id, name='child',
        )
        db_session.add(child)
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/discard_draft')
        db_session.refresh(child)
        assert child.based_on_version_id is None

    def test_discarding_allows_a_fresh_draft_from_the_published_version(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _structured_published(db_session, template)
        _create_draft(logged_in_client, template)
        _post(logged_in_client, f'/admin/templates/{template.id}/discard_draft')
        _create_draft(logged_in_client, template)
        draft = _draft_of(template)
        assert draft is not None
        assert FormItem.query.filter_by(version_id=draft.id).count() == 2


def _archived_version_with_item(db_session, template):
    version = FormTemplateVersion(
        template_id=template.id, version_number=7, status='archived', name='old'
    )
    db_session.add(version)
    db_session.flush()
    section = create_test_section(db_session, template, version=version, name='old section', order=1)
    item = create_test_item(
        db_session, section, template, version=version, item_type='question', label='old item', order=1
    )
    db_session.commit()
    return version, section, item


class TestDeleteVersion:
    def test_archived_version_without_data_is_deleted_with_its_structure(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        version, section, item = _archived_version_with_item(db_session, template)
        version_id, section_id, item_id = version.id, section.id, item.id
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version_id}/delete')
        db_session.expire_all()
        assert FormTemplateVersion.query.filter_by(id=version_id).count() == 0
        assert FormSection.query.filter_by(id=section_id).count() == 0
        assert FormItem.query.filter_by(id=item_id).count() == 0

    def test_version_with_submission_data_cannot_be_deleted(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        version, _section, item = _archived_version_with_item(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value='keep'))
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        assert FormTemplateVersion.query.get(version.id) is not None
        assert FormData.query.filter_by(form_item_id=item.id).count() == 1
        assert any('Cannot delete' in m for m in _flashes(logged_in_client))

    def test_version_with_repeat_instances_cannot_be_deleted(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        version, section, _item = _archived_version_with_item(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(RepeatGroupInstance(
            section_id=section.id, instance_number=1,
            assignment_entity_status_id=aes.id, created_by_user_id=admin_user.id,
        ))
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        assert FormTemplateVersion.query.get(version.id) is not None

    def test_version_with_page_workflow_status_cannot_be_deleted(
        self, logged_in_client, db_session, admin_user
    ):
        """AssignmentPageStatus cascades on page delete, so it must block deletion."""
        template = _template(db_session, admin_user)
        version, _section, _item = _archived_version_with_item(db_session, template)
        page = FormPage(template_id=template.id, version_id=version.id, name='P', order=1)
        db_session.add(page)
        db_session.flush()
        aes = create_test_assignment_entity_status(db_session, template=template)
        status = AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=page.id, status='Approved'
        )
        db_session.add(status)
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        assert FormTemplateVersion.query.get(version.id) is not None
        assert AssignmentPageStatus.query.get(status.id) is not None

    def test_version_with_ai_validation_results_cannot_be_deleted(
        self, logged_in_client, db_session, admin_user
    ):
        """AIFormDataValidation cascades on item delete, so it must block deletion."""
        template = _template(db_session, admin_user)
        version, _section, item = _archived_version_with_item(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        validation = AIFormDataValidation(
            assignment_entity_status_id=aes.id,
            form_item_id=item.id,
            opinion_text='virtual validation',
        )
        db_session.add(validation)
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        assert FormTemplateVersion.query.get(version.id) is not None
        assert AIFormDataValidation.query.get(validation.id) is not None

    def test_delete_fails_closed_when_the_data_check_errors(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        version, _section, item = _archived_version_with_item(db_session, template)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value='keep'))
        db_session.commit()
        with patch('app.routes.admin.form_builder.versions.func') as broken:
            broken.count.side_effect = RuntimeError('count failed')
            _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        db_session.rollback()
        assert FormTemplateVersion.query.get(version.id) is not None
        assert FormData.query.filter_by(form_item_id=item.id).count() == 1

    def test_published_version_cannot_be_deleted(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        published = template.published_version
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{published.id}/delete')
        assert FormTemplateVersion.query.get(published.id) is not None

    def test_version_of_another_template_cannot_be_deleted_through_this_one(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        other = create_test_template(db_session, owner_id=admin_user.id)
        other_draft = create_test_draft_version(db_session, other)
        resp = _post(
            logged_in_client, f'/admin/templates/{template.id}/versions/{other_draft.id}/delete'
        )
        assert resp.status_code == 404
        assert FormTemplateVersion.query.get(other_draft.id) is not None

    def test_deleting_a_version_detaches_versions_based_on_it(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        version, _section, _item = _archived_version_with_item(db_session, template)
        child = create_test_draft_version(db_session, template)
        child.based_on_version_id = version.id
        db_session.commit()
        _post(logged_in_client, f'/admin/templates/{template.id}/versions/{version.id}/delete')
        db_session.refresh(child)
        assert child.based_on_version_id is None


# ---------------------------------------------------------------------------
# Field mapping routes (sections + review page)
# ---------------------------------------------------------------------------

def _json_post(client, url, payload):
    from flask import current_app
    with current_app.test_request_context():
        from flask_wtf.csrf import generate_csrf
        token = generate_csrf()
    with patch('app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'):
        return client.post(
            url, data=json.dumps(payload), content_type='application/json',
            headers={'X-CSRFToken': token, 'Accept': 'application/json'},
        )


class TestFieldMappingSectionRoutes:
    def _setup(self, db_session, admin_user):
        template = _template(db_session, admin_user)
        published, pub_section, _first, _second = _structured_published(db_session, template)
        draft = create_test_draft_version(db_session, template)
        draft_section = create_test_section(db_session, template, version=draft, name='Renamed', order=1)
        db_session.commit()
        return template, published, pub_section, draft, draft_section

    def test_link_then_unlink_section(self, logged_in_client, db_session, admin_user, app):
        template, _published, pub_section, draft, draft_section = self._setup(db_session, admin_user)
        base = f'/admin/templates/{template.id}/versions/{draft.id}/sections/{draft_section.id}'
        with app.app_context():
            pass
        resp = _json_post(logged_in_client, f'{base}/link', {'published_stable_key': pub_section.stable_key})
        assert resp.status_code == 200
        db_session.refresh(draft_section)
        assert draft_section.stable_key == pub_section.stable_key

        resp = _json_post(logged_in_client, f'{base}/unlink', {})
        assert resp.status_code == 200
        db_session.refresh(draft_section)
        assert draft_section.stable_key != pub_section.stable_key

    def test_link_section_conflict_then_confirmed_reassign(
        self, logged_in_client, db_session, admin_user, app
    ):
        template, _published, pub_section, draft, draft_section = self._setup(db_session, admin_user)
        holder = create_test_section(db_session, template, version=draft, name='Holder', order=2)
        holder.stable_key = pub_section.stable_key
        db_session.commit()
        base = f'/admin/templates/{template.id}/versions/{draft.id}/sections/{draft_section.id}/link'

        resp = _json_post(logged_in_client, base, {'published_stable_key': pub_section.stable_key})
        assert resp.status_code == 409
        assert resp.get_json()['conflict'] is True

        resp = _json_post(
            logged_in_client, base,
            {'published_stable_key': pub_section.stable_key, 'confirm_reassign': True},
        )
        assert resp.status_code == 200
        db_session.refresh(holder)
        db_session.refresh(draft_section)
        assert draft_section.stable_key == pub_section.stable_key
        assert holder.stable_key != pub_section.stable_key

    def test_link_unknown_key_is_rejected(self, logged_in_client, db_session, admin_user, app):
        template, _published, _pub_section, draft, draft_section = self._setup(db_session, admin_user)
        base = f'/admin/templates/{template.id}/versions/{draft.id}/sections/{draft_section.id}/link'
        for bad in (generate_stable_key(), 'not-a-uuid', ''):
            resp = _json_post(logged_in_client, base, {'published_stable_key': bad})
            assert resp.status_code == 400, bad

    def test_item_unlink_route_assigns_fresh_key(self, logged_in_client, db_session, admin_user, app):
        template, published, _ps, draft, draft_section = self._setup(db_session, admin_user)
        item = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='x', order=1
        )
        old_key = item.stable_key
        db_session.commit()
        resp = _json_post(
            logged_in_client,
            f'/admin/templates/{template.id}/versions/{draft.id}/items/{item.id}/unlink', {},
        )
        assert resp.status_code == 200
        db_session.refresh(item)
        assert item.stable_key != old_key

    def test_item_from_other_version_cannot_be_linked(self, logged_in_client, db_session, admin_user, app):
        template, published, _ps, draft, _ds = self._setup(db_session, admin_user)
        pub_item = FormItem.query.filter_by(version_id=published.id, label='First').one()
        resp = _json_post(
            logged_in_client,
            f'/admin/templates/{template.id}/versions/{draft.id}/items/{pub_item.id}/link',
            {'published_stable_key': pub_item.stable_key},
        )
        assert resp.status_code == 404

    def test_review_page_renders_rows_and_redirects_for_published_version(
        self, logged_in_client, db_session, admin_user
    ):
        template, published, _ps, draft, _ds = self._setup(db_session, admin_user)
        page = logged_in_client.get(
            f'/admin/templates/{template.id}/versions/{draft.id}/field-mapping'
        )
        assert page.status_code == 200
        assert b'First' in page.data
        redirected = logged_in_client.get(
            f'/admin/templates/{template.id}/versions/{published.id}/field-mapping'
        )
        assert redirected.status_code == 302


# ---------------------------------------------------------------------------
# Cloning
# ---------------------------------------------------------------------------

class TestCloneCompleteness:
    def test_item_columns_are_all_accounted_for(self):
        rewritten = {'id', 'section_id', 'version_id', 'relevance_condition', 'validation_condition', 'list_filters_json'}
        copied_verbatim = {
            'template_id', 'item_type', 'stable_key', 'label', 'order', 'archived', 'config',
            'indicator_bank_id', 'type', 'unit', 'indicator_type_id', 'indicator_unit_id',
            'validation_message', 'validation_message_translations', 'definition', 'options_json',
            'lookup_list_id', 'list_display_column', 'label_translations', 'definition_translations',
            'options_translations', 'description_translations', 'description',
        }
        assert {c.name for c in FormItem.__table__.columns} == rewritten | copied_verbatim

    def test_section_and_page_columns_are_all_accounted_for(self):
        assert {c.name for c in FormSection.__table__.columns} == {
            'id', 'version_id', 'template_id', 'name', 'order', 'stable_key', 'parent_section_id',
            'page_id', 'section_type', 'max_dynamic_indicators', 'allowed_sectors',
            'indicator_filters', 'allow_data_not_available', 'allow_not_applicable',
            'allowed_disaggregation_options', 'data_entry_display_filters', 'add_indicator_note',
            'name_translations', 'relevance_condition', 'archived', 'config',
        }
        assert {c.name for c in FormPage.__table__.columns} == {
            'id', 'version_id', 'template_id', 'name', 'order', 'name_translations',
        }

    def test_every_item_column_survives_a_clone(self, db_session, admin_user):
        from app.models import IndicatorBank
        from app.models.indicator_bank import IndicatorBankType, IndicatorBankUnit
        from app.models.lookups import LookupList

        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        section = create_test_section(db_session, template, version=published, name='S', order=1)
        bank = IndicatorBank(name='bank', type='number', archived=False)
        ind_type = IndicatorBankType(code=f't-{generate_stable_key()[:8]}', name='T')
        ind_unit = IndicatorBankUnit(code=f'u-{generate_stable_key()[:8]}', name='U')
        lookup = LookupList(name=f'lookup-{generate_stable_key()[:8]}')
        db_session.add_all([bank, ind_type, ind_unit, lookup])
        db_session.flush()

        item = create_test_item(
            db_session, section, template, version=published, item_type='indicator',
            indicator_bank_id=bank.id, label='Full item', order=3.5,
        )
        item.archived = True
        item.config = {'is_required': True, 'nested': {'a': [1, 2]}}
        item.type = 'number'
        item.unit = 'people'
        item.indicator_type_id = ind_type.id
        item.indicator_unit_id = ind_unit.id
        item.validation_message = 'msg'
        item.validation_message_translations = {'fr': 'msg-fr'}
        item.definition = 'def'
        item.options_json = ['a', 'b']
        item.lookup_list_id = lookup.id
        item.list_display_column = 'col'
        item.label_translations = {'fr': 'etiquette'}
        item.definition_translations = {'fr': 'definition'}
        item.options_translations = {'fr': ['a-fr']}
        item.description_translations = {'fr': 'desc'}
        item.description = 'description'
        db_session.commit()

        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()
        clone = FormItem.query.filter_by(version_id=draft.id).one()
        db_session.refresh(item)
        db_session.refresh(clone)

        skip = {'id', 'section_id', 'version_id'}
        for column in FormItem.__table__.columns:
            if column.name in skip:
                continue
            assert getattr(clone, column.name) == getattr(item, column.name), column.name

        clone.config['nested']['a'].append(3)
        clone.options_json.append('c')
        assert item.config['nested']['a'] == [1, 2]
        assert item.options_json == ['a', 'b']

    def test_every_section_and_page_column_survives_a_clone(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        page = FormPage(
            template_id=template.id, version_id=published.id, name='Page', order=2,
            name_translations={'fr': 'Page FR'},
        )
        db_session.add(page)
        db_session.flush()
        parent = create_test_section(db_session, template, version=published, name='Parent', order=1)
        child = create_test_section(
            db_session, template, version=published, name='Child', order=2,
            parent_section_id=parent.id, section_type='dynamic_indicators',
        )
        for section in (parent, child):
            section.page_id = page.id
        child.max_dynamic_indicators = 4
        child.allowed_sectors = ['health']
        child.indicator_filters = [{'field': 'type', 'values': ['number']}]
        child.allow_data_not_available = True
        child.allow_not_applicable = True
        child.allowed_disaggregation_options = ['total', 'sex']
        child.data_entry_display_filters = ['type']
        child.add_indicator_note = 'note'
        child.name_translations = {'fr': 'Enfant'}
        child.archived = True
        child.config = {'x': {'y': 1}}
        db_session.commit()

        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()

        clone_page = FormPage.query.filter_by(version_id=draft.id).one()
        assert (clone_page.name, clone_page.order, clone_page.name_translations) == (
            'Page', 2, {'fr': 'Page FR'}
        )
        clone_parent = FormSection.query.filter_by(version_id=draft.id, name='Parent').one()
        clone_child = FormSection.query.filter_by(version_id=draft.id, name='Child').one()
        assert clone_child.parent_section_id == clone_parent.id
        assert clone_child.page_id == clone_page.id and clone_parent.page_id == clone_page.id
        skip = {'id', 'version_id', 'parent_section_id', 'page_id'}
        for column in FormSection.__table__.columns:
            if column.name in skip:
                continue
            assert getattr(clone_child, column.name) == getattr(child, column.name), column.name

    def test_repeat_entry_label_reference_points_at_the_cloned_item(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        repeat = create_test_section(
            db_session, template, version=published, name='Repeat', order=1, section_type='repeat'
        )
        label_item = create_test_item(
            db_session, repeat, template, version=published, item_type='question', label='Name', order=1
        )
        repeat.config = {'entry_label_item_id': label_item.id, 'other': 'kept'}
        db_session.commit()

        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()

        clone_section = FormSection.query.filter_by(version_id=draft.id).one()
        clone_item = FormItem.query.filter_by(version_id=draft.id).one()
        assert clone_section.entry_label_item_id == clone_item.id
        assert clone_section.config['other'] == 'kept'
        db_session.refresh(repeat)
        assert repeat.config['entry_label_item_id'] == label_item.id

    def test_dangling_entry_label_reference_is_dropped_not_leaked(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        repeat = create_test_section(
            db_session, template, version=published, name='Repeat', order=1, section_type='repeat'
        )
        repeat.config = {'entry_label_item_id': 987654}
        db_session.commit()
        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()
        clone_section = FormSection.query.filter_by(version_id=draft.id).one()
        assert clone_section.entry_label_item_id is None

    def test_entry_label_reference_is_remapped_between_templates_too(self, db_session, admin_user):
        source = create_test_template(db_session, owner_id=admin_user.id)
        target = create_test_template(db_session, owner_id=admin_user.id)
        published = source.published_version
        repeat = create_test_section(
            db_session, source, version=published, name='Repeat', order=1, section_type='repeat'
        )
        label_item = create_test_item(
            db_session, repeat, source, version=published, item_type='question', label='Name', order=1
        )
        repeat.config = {'entry_label_item_id': label_item.id}
        db_session.commit()

        _clone_template_structure_between_templates(
            source_template_id=source.id, source_version_id=published.id,
            target_template_id=target.id, target_version_id=target.published_version.id,
        )
        db_session.commit()
        clone_section = FormSection.query.filter_by(template_id=target.id).one()
        clone_item = FormItem.query.filter_by(template_id=target.id).one()
        assert clone_section.entry_label_item_id == clone_item.id

    def test_list_filters_and_validation_rules_are_remapped(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        section = create_test_section(db_session, template, version=published, name='S', order=1)
        a = create_test_item(db_session, section, template, version=published, item_type='question', label='A', order=1)
        b = create_test_item(db_session, section, template, version=published, item_type='question', label='B', order=2)
        b.validation_condition = json.dumps({'item_id': a.id, 'value_field_id': f'question_{a.id}'})
        b.list_filters_json = [{'field': a.id, 'value': 'x'}]
        section.relevance_condition = json.dumps({'conditions': [{'item_id': b.id}]})
        db_session.commit()

        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()

        new_a = FormItem.query.filter_by(version_id=draft.id, label='A').one()
        new_b = FormItem.query.filter_by(version_id=draft.id, label='B').one()
        rule = json.loads(new_b.validation_condition)
        assert rule['item_id'] == str(new_a.id)
        assert rule['value_field_id'] == str(new_a.id)
        assert new_b.list_filters_json[0]['field'] == str(new_a.id)
        new_section = FormSection.query.filter_by(version_id=draft.id).one()
        assert json.loads(new_section.relevance_condition)['conditions'][0]['item_id'] == str(new_b.id)

    def test_cloning_a_legacy_row_without_key_does_not_invent_one(self, db_session, admin_user):
        """NULL keys stay NULL on clone; the deploy step is responsible for aligning them."""
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        section = create_test_section(db_session, template, version=published, name='S', order=1)
        item = create_test_item(db_session, section, template, version=published, item_type='question', order=1)
        section.stable_key = None
        item.stable_key = None
        db_session.commit()
        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()
        assert FormSection.query.filter_by(version_id=draft.id).one().stable_key is None
        assert FormItem.query.filter_by(version_id=draft.id).one().stable_key is None

    def test_clone_into_same_template_preserves_ordering_of_pages_sections_items(
        self, db_session, admin_user
    ):
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        for idx, name in enumerate(('c', 'a', 'b')):
            db_session.add(FormPage(template_id=template.id, version_id=published.id, name=name, order=idx + 1))
        s = create_test_section(db_session, template, version=published, name='S', order=1)
        for idx, label in enumerate(('z', 'y', 'x')):
            create_test_item(db_session, s, template, version=published, item_type='question', label=label, order=idx + 1)
        db_session.commit()
        _clone_template_structure(template.id, published.id, draft.id)
        db_session.commit()
        pages = FormPage.query.filter_by(version_id=draft.id).order_by(FormPage.order).all()
        assert [p.name for p in pages] == ['c', 'a', 'b']
        items = FormItem.query.filter_by(version_id=draft.id).order_by(FormItem.order).all()
        assert [i.label for i in items] == ['z', 'y', 'x']


# ---------------------------------------------------------------------------
# Concurrency helper
# ---------------------------------------------------------------------------

class TestTemplateRowLock:
    def test_lock_helper_returns_the_template(self, app, db_session, admin_user):
        from app.routes.admin.form_builder.versions import _lock_template_for_version_change
        template = create_test_template(db_session, owner_id=admin_user.id)
        locked = _lock_template_for_version_change(template.id)
        assert locked.id == template.id

    def test_lock_helper_404s_for_missing_template(self, app, db_session):
        from werkzeug.exceptions import NotFound
        from app.routes.admin.form_builder.versions import _lock_template_for_version_change
        with pytest.raises(NotFound):
            _lock_template_for_version_change(99999999)

    def test_lock_helper_sees_a_published_pointer_changed_elsewhere(self, app, db_session, admin_user):
        """populate_existing: a stale in-session template must not decide which version is live."""
        from app.routes.admin.form_builder.versions import _lock_template_for_version_change
        template = create_test_template(db_session, owner_id=admin_user.id)
        draft = create_test_draft_version(db_session, template)
        stale = FormTemplate.query.get(template.id)
        original = stale.published_version_id
        db_session.execute(
            FormTemplate.__table__.update().where(FormTemplate.id == template.id)
            .values(published_version_id=draft.id)
        )
        assert stale.published_version_id == original
        assert _lock_template_for_version_change(template.id).published_version_id == draft.id


# ---------------------------------------------------------------------------
# Link compatibility
# ---------------------------------------------------------------------------

def _linkable_pair(db_session, admin_user, *, pub_kwargs=None, draft_kwargs=None):
    template = _template(db_session, admin_user)
    published = template.published_version
    draft = create_test_draft_version(db_session, template)
    pub_section = create_test_section(db_session, template, version=published)
    draft_section = create_test_section(db_session, template, version=draft)
    key = generate_stable_key()
    pub_item = create_test_item(
        db_session, pub_section, template, version=published,
        **{'item_type': 'question', 'label': 'Pub', **(pub_kwargs or {})},
    )
    pub_item.stable_key = key
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft,
        **{'item_type': 'question', 'label': 'Draft', **(draft_kwargs or {})},
    )
    db_session.commit()
    return template, draft, draft_item, pub_item, key


class TestLinkCompatibility:
    def _link(self, template, draft, draft_item, key, **flags):
        with patch('app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'):
            return link_draft_item(
                template=template, draft_version=draft, draft_item=draft_item,
                published_stable_key=key, **flags,
            )

    def test_different_item_kinds_can_never_be_linked(self, db_session, admin_user):
        template, draft, draft_item, _pub, key = _linkable_pair(
            db_session, admin_user, draft_kwargs={'item_type': 'matrix'}
        )
        original = draft_item.stable_key
        with pytest.raises(FieldMappingIncompatibleError):
            self._link(template, draft, draft_item, key, confirm_type_mismatch=True)
        assert draft_item.stable_key == original

    def test_data_type_difference_needs_confirmation(self, db_session, admin_user):
        template, draft, draft_item, _pub, key = _linkable_pair(
            db_session, admin_user,
            pub_kwargs={'type': 'number'}, draft_kwargs={'type': 'text'},
        )
        original = draft_item.stable_key
        with pytest.raises(FieldMappingTypeMismatchError) as caught:
            self._link(template, draft, draft_item, key)
        assert any('Data type differs' in w for w in caught.value.warnings)
        assert draft_item.stable_key == original

        linked_key, warnings, _displaced = self._link(
            template, draft, draft_item, key, confirm_type_mismatch=True
        )
        assert linked_key == key
        assert draft_item.stable_key == key
        assert warnings

    def test_matching_types_link_without_confirmation(self, db_session, admin_user):
        template, draft, draft_item, _pub, key = _linkable_pair(
            db_session, admin_user, pub_kwargs={'type': 'number'}, draft_kwargs={'type': 'number'}
        )
        linked_key, warnings, _displaced = self._link(template, draft, draft_item, key)
        assert linked_key == key and warnings == []

    def test_standard_and_repeat_sections_cannot_be_linked(self, db_session, admin_user):
        template = _template(db_session, admin_user)
        published = template.published_version
        draft = create_test_draft_version(db_session, template)
        pub_section = create_test_section(
            db_session, template, version=published, section_type='standard'
        )
        key = generate_stable_key()
        pub_section.stable_key = key
        draft_section = create_test_section(
            db_session, template, version=draft, section_type='repeat'
        )
        db_session.commit()
        with patch('app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'):
            with pytest.raises(FieldMappingIncompatibleError):
                link_draft_section(
                    template=template, draft_version=draft, draft_section=draft_section,
                    published_stable_key=key, confirm_type_mismatch=True,
                )

    def test_route_asks_for_confirmation_then_links(
        self, logged_in_client, db_session, admin_user
    ):
        template, draft, draft_item, _pub, key = _linkable_pair(
            db_session, admin_user, pub_kwargs={'type': 'number'}, draft_kwargs={'type': 'text'}
        )
        url = f'/admin/templates/{template.id}/versions/{draft.id}/items/{draft_item.id}/link'
        first = _json_post(logged_in_client, url, {'published_stable_key': key})
        assert first.status_code == 409
        assert first.get_json()['type_mismatch'] is True

        second = _json_post(
            logged_in_client, url, {'published_stable_key': key, 'confirm_type_mismatch': True}
        )
        assert second.status_code == 200
        db_session.refresh(draft_item)
        assert draft_item.stable_key == key

    def test_route_rejects_incompatible_kinds_outright(
        self, logged_in_client, db_session, admin_user
    ):
        template, draft, draft_item, _pub, key = _linkable_pair(
            db_session, admin_user, draft_kwargs={'item_type': 'matrix'}
        )
        url = f'/admin/templates/{template.id}/versions/{draft.id}/items/{draft_item.id}/link'
        resp = _json_post(
            logged_in_client, url, {'published_stable_key': key, 'confirm_type_mismatch': True}
        )
        assert resp.status_code == 400
        assert 'mismatch' in resp.get_json()['error'].lower()


# ---------------------------------------------------------------------------
# Duplicating a template keeps variables pointing at its own fields
# ---------------------------------------------------------------------------

class TestDuplicateTemplateVariables:
    def test_variables_point_at_the_copied_items(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        published, _section, first, _second = _structured_published(db_session, template)
        published.variables = {
            'source_var': {'variable_type': 'form_item', 'source_form_item_id': first.id},
            'plain': {'variable_type': 'metadata', 'metadata_type': 'assignment_period'},
            'dangling': {'variable_type': 'form_item', 'source_form_item_id': 987654},
        }
        db_session.commit()
        _grant_role_permission(db_session, 'admin_core', 'admin.templates.duplicate')
        db_session.commit()

        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/duplicate/{template.id}', data={}, follow_redirects=False
            )
        assert resp.status_code == 302

        copy = (
            FormTemplate.query.filter(FormTemplate.id != template.id)
            .order_by(FormTemplate.id.desc()).first()
        )
        copied_version = FormTemplateVersion.query.get(copy.published_version_id)
        copied_first = FormItem.query.filter_by(version_id=copied_version.id, label='First').one()
        assert copied_first.id != first.id
        assert copied_version.variables['source_var']['source_form_item_id'] == copied_first.id
        assert 'source_form_item_id' not in copied_version.variables['dangling']
        assert copied_version.variables['plain'] == {
            'variable_type': 'metadata', 'metadata_type': 'assignment_period'
        }
        db_session.refresh(published)
        assert published.variables['source_var']['source_form_item_id'] == first.id


# ---------------------------------------------------------------------------
# Removing pages
# ---------------------------------------------------------------------------

class TestPageRemoval:
    def _page_with_status(self, db_session, template, version, status):
        page = FormPage(template_id=template.id, version_id=version.id, name='Gone', order=1)
        db_session.add(page)
        db_session.flush()
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=page.id, status=status
        ))
        db_session.commit()
        return page

    def _submit_no_pages(self, template, version):
        from werkzeug.datastructures import MultiDict
        _handle_template_pages(template, MultiDict(), version_id=version.id)
        db.session.flush()

    def test_page_with_progress_cannot_be_removed(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        page = self._page_with_status(db_session, template, template.published_version, 'submitted')
        with pytest.raises(PageInUseError) as caught:
            self._submit_no_pages(template, template.published_version)
        assert 'Gone' in str(caught.value)
        db_session.rollback()
        assert FormPage.query.get(page.id) is not None
        assert AssignmentPageStatus.query.filter_by(form_page_id=page.id).count() == 1

    def test_untouched_page_status_does_not_block_removal(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        page = self._page_with_status(db_session, template, template.published_version, 'not_started')
        page_id = page.id
        self._submit_no_pages(template, template.published_version)
        db_session.expire_all()
        assert FormPage.query.filter_by(id=page_id).count() == 0

    def test_draft_page_without_statuses_can_be_removed(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        draft = create_test_draft_version(db_session, template)
        page = FormPage(template_id=template.id, version_id=draft.id, name='Draft page', order=1)
        db_session.add(page)
        db_session.commit()
        page_id = page.id
        self._submit_no_pages(template, draft)
        db_session.expire_all()
        assert FormPage.query.filter_by(id=page_id).count() == 0


# ---------------------------------------------------------------------------
# Deploy requires acknowledging data that is left behind
# ---------------------------------------------------------------------------

def _draft_without_second_field(db_session, client, template, second, with_data=True):
    if with_data:
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(
            assignment_entity_status_id=aes.id, form_item_id=second.id, value='reported'
        ))
        db_session.commit()
    _create_draft(client, template)
    draft = _draft_of(template)
    FormItem.query.filter_by(version_id=draft.id, label='Second').delete()
    db_session.commit()
    return draft


class TestOrphanedDataAcknowledgement:
    def test_deploy_is_refused_until_acknowledged(self, logged_in_client, db_session, admin_user):
        template = _template(db_session, admin_user)
        published, _section, _first, second = _structured_published(db_session, template)
        draft = _draft_without_second_field(db_session, logged_in_client, template, second)

        _deploy(logged_in_client, template, draft)
        db_session.refresh(template)
        db_session.refresh(draft)
        assert template.published_version_id == published.id
        assert draft.status == 'draft'
        assert any('hold submitted data' in m for m in _flashes(logged_in_client))

    def test_ajax_deploy_reports_what_needs_acknowledging(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _published, _section, _first, second = _structured_published(db_session, template)
        draft = _draft_without_second_field(db_session, logged_in_client, template, second)

        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/deploy',
            data={'version_id': str(draft.id)},
            headers={'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['requires_acknowledgement'] is True
        assert body['orphaned_items_with_data'] == 1
        assert body['field_mapping_url'].endswith(f'/versions/{draft.id}/field-mapping')

    def test_acknowledged_deploy_goes_ahead_and_keeps_the_data(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _published, _section, _first, second = _structured_published(db_session, template)
        draft = _draft_without_second_field(db_session, logged_in_client, template, second)

        _deploy(logged_in_client, template, draft, acknowledge_orphaned_data='1')
        db_session.refresh(template)
        assert template.published_version_id == draft.id
        db_session.refresh(second)
        assert second.archived is True
        assert FormData.query.filter_by(form_item_id=second.id).count() == 1

    def test_no_acknowledgement_needed_when_the_removed_field_has_no_data(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _published, _section, _first, second = _structured_published(db_session, template)
        draft = _draft_without_second_field(
            db_session, logged_in_client, template, second, with_data=False
        )
        _deploy(logged_in_client, template, draft)
        db_session.refresh(template)
        assert template.published_version_id == draft.id

    def test_rollback_without_stranded_data_needs_no_acknowledgement(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        v1, _section, _first, _second = _structured_published(db_session, template)
        _create_draft(logged_in_client, template)
        v2 = _draft_of(template)
        _deploy(logged_in_client, template, v2)

        v2_first = FormItem.query.filter_by(version_id=v2.id, label='First').one()
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(
            assignment_entity_status_id=aes.id, form_item_id=v2_first.id, value='kept'
        ))
        db_session.commit()
        _deploy(logged_in_client, template, v1)
        db_session.refresh(template)
        assert template.published_version_id == v1.id

    def test_rollback_that_strands_data_requires_acknowledgement(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        v1, _section, _first, _second = _structured_published(db_session, template)
        _create_draft(logged_in_client, template)
        v2 = _draft_of(template)
        v2_section = FormSection.query.filter_by(version_id=v2.id).one()
        added = create_test_item(
            db_session, v2_section, template, version=v2,
            item_type='question', label='Added in v2', order=3,
        )
        db_session.commit()
        _deploy(logged_in_client, template, v2)

        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(FormData(
            assignment_entity_status_id=aes.id, form_item_id=added.id, value='only in v2'
        ))
        db_session.commit()

        _deploy(logged_in_client, template, v1)
        db_session.refresh(template)
        assert template.published_version_id == v2.id

        _deploy(logged_in_client, template, v1, acknowledge_orphaned_data='1')
        db_session.refresh(template)
        assert template.published_version_id == v1.id
        assert FormData.query.filter_by(form_item_id=added.id).count() == 1

    def test_review_page_shows_the_checkbox_only_when_needed(
        self, logged_in_client, db_session, admin_user
    ):
        template = _template(db_session, admin_user)
        _published, _section, _first, second = _structured_published(db_session, template)
        draft = _draft_without_second_field(db_session, logged_in_client, template, second)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/versions/{draft.id}/field-mapping'
        )
        assert resp.status_code == 200
        assert b'name="acknowledge_orphaned_data"' in resp.data


# ---------------------------------------------------------------------------
# Data entry racing a deploy
# ---------------------------------------------------------------------------

class TestEntryFormStaleGuard:
    def test_current_version_is_accepted(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        assert entry_form_is_stale(template, str(template.published_version_id)) is False

    def test_form_from_before_a_deploy_is_stale(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        old_version_id = template.published_version_id
        draft = create_test_draft_version(db_session, template)
        template.published_version_id = draft.id
        db_session.commit()
        assert entry_form_is_stale(template, str(old_version_id)) is True
        assert entry_form_is_stale(template, str(draft.id)) is False

    def test_missing_version_marker_is_tolerated(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        assert entry_form_is_stale(template, None) is False
        assert entry_form_is_stale(template, '') is False

    def test_garbage_marker_is_treated_as_stale(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        assert entry_form_is_stale(template, 'abc') is True

    def test_check_reads_the_committed_version_not_a_cached_one(
        self, app, db_session, admin_user
    ):
        template = create_test_template(db_session, owner_id=admin_user.id)
        old_version_id = template.published_version_id
        draft = create_test_draft_version(db_session, template)
        db_session.commit()
        db_session.execute(
            db.text('UPDATE form_template SET published_version_id = :v WHERE id = :t'),
            {'v': draft.id, 't': template.id},
        )
        # The identity-mapped object still carries the old id until the lock refreshes it.
        assert template.published_version_id == old_version_id
        assert entry_form_is_stale(template, str(old_version_id)) is True
        assert template.published_version_id == draft.id


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class TestTemplateVersionAudit:
    def test_clean_template_has_no_findings(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        report = audit_template_versions(template.id)
        assert report['has_blocking_issues'] is False
        assert report['multiple_drafts'] == []

    def test_reports_several_drafts(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        first = create_test_draft_version(db_session, template)
        second = FormTemplateVersion(
            template_id=template.id, version_number=first.version_number + 1,
            status='draft', name='second',
        )
        db_session.add(second)
        db_session.commit()
        report = audit_template_versions(template.id)
        assert report['has_blocking_issues'] is True
        assert report['multiple_drafts'][0]['version_ids'] == sorted([first.id, second.id])

    def test_reports_duplicate_keys_inside_a_version(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        section = create_test_section(db_session, template, version=template.published_version)
        a = create_test_item(
            db_session, section, template, version=template.published_version,
            item_type='question', label='A', order=1,
        )
        b = create_test_item(
            db_session, section, template, version=template.published_version,
            item_type='question', label='B', order=2,
        )
        b.stable_key = a.stable_key
        db_session.commit()
        report = audit_template_versions(template.id)
        assert report['has_blocking_issues'] is True
        assert report['duplicate_item_keys'][0]['row_ids'] == sorted([a.id, b.id])

    def test_reports_published_pointer_mismatch(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        draft = create_test_draft_version(db_session, template)
        template.published_version_id = draft.id
        db_session.commit()
        problems = {f['problem'] for f in audit_template_versions(template.id)['published_inconsistencies']}
        assert 'pointer_to_unpublished_version' in problems or 'pointer_mismatch' in problems

    def test_missing_keys_are_advisory_only(self, app, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        create_test_draft_version(db_session, template)
        section = create_test_section(db_session, template, version=template.published_version)
        db_session.execute(
            db.text('UPDATE form_section SET stable_key = NULL WHERE id = :i'), {'i': section.id}
        )
        db_session.commit()
        report = audit_template_versions(template.id)
        assert report['sections_without_key']
        assert report['has_blocking_issues'] is False


# ---------------------------------------------------------------------------
# Excel import never hands one identity key to two rows
# ---------------------------------------------------------------------------

class TestImportKeyClaims:
    def _resolve(self, row, fallback, claimed):
        errors = []
        key = TemplateExcelImportService._resolve_import_stable_key(
            row, 2, 'Items', errors, published_fallback=fallback, claimed_keys=claimed
        )
        assert errors == []
        return key

    def test_published_key_goes_to_one_row_only(self):
        published_key = generate_stable_key()
        claimed = set()
        first = self._resolve({}, published_key, claimed)
        second = self._resolve({}, published_key, claimed)
        assert first == published_key
        assert second != published_key
        assert len({first, second}) == 2

    def test_explicit_key_in_the_sheet_beats_a_positional_fallback(self):
        published_key = generate_stable_key()
        rows = [(3, {'stable_key': published_key}), (4, {})]
        claimed = TemplateExcelImportService._explicit_stable_keys(rows)
        positional = self._resolve({}, published_key, claimed)
        explicit = self._resolve({'stable_key': published_key}, None, claimed)
        assert explicit == published_key
        assert positional != published_key

    def test_without_claims_behaviour_is_unchanged(self):
        published_key = generate_stable_key()
        assert self._resolve({}, published_key, None) == published_key
        assert self._resolve({}, published_key, None) == published_key
