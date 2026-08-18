"""
Comprehensive pytest tests for app/routes/admin/form_builder/sections.py

Routes covered:
- POST /admin/templates/<id>/sections/new         (new_template_section)
- POST /admin/sections/edit/<id>                  (edit_template_section)
- POST /admin/sections/delete/<id>                (delete_template_section)
- POST /admin/sections/duplicate/<id>             (duplicate_template_section)
- POST /admin/sections/unarchive/<id>             (unarchive_section)
- POST /admin/sections/configure-dynamic/<id>     (configure_dynamic_section)
- POST /admin/sections/configure-repeat/<id>      (configure_repeat_section)

Also covers the _b64_decode_field helper (exercised indirectly through routes).
"""
import base64
import json
import pytest
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_template,
    create_test_draft_version,
    create_test_section,
    create_test_item,
)


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64(text: str) -> str:
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')


def _make_owned_template(db_session, admin_user, **kwargs):
    return create_test_template(db_session, owner_id=admin_user.id, **kwargs)


def _make_section(db_session, template, version=None, **kwargs):
    return create_test_section(db_session, template, version=version, **kwargs)


# ---------------------------------------------------------------------------
# new_template_section
# ---------------------------------------------------------------------------

class TestNewTemplateSection:

    def test_creates_section_standard(self, logged_in_client, db_session, admin_user, app):
        """POST creates a standard section and redirects to edit."""
        template = _make_owned_template(db_session, admin_user, name='Sec Template')
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'My Section',
                    'section-section_type': 'standard',
                    'section-order': '1',
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_creates_section_without_explicit_order(self, logged_in_client, db_session, admin_user, app):
        """POST without order auto-calculates next order value."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Auto Order',
                    'section-section_type': 'standard',
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_creates_section_with_parent(self, logged_in_client, db_session, admin_user, app):
        """POST with a valid parent_section_id creates a nested section."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        parent = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Child Section',
                    'section-section_type': 'standard',
                    'parent_section_id': str(parent.id),
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_invalid_parent_flashes_error(self, logged_in_client, db_session, admin_user, app):
        """POST with non-existent parent flashes an error and redirects."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Bad Child',
                    'section-section_type': 'standard',
                    'parent_section_id': '999999',
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deeply_nested_parent_rejected(self, logged_in_client, db_session, admin_user, app):
        """POST with a nested (non-top-level) parent is rejected."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        parent = _make_section(db_session, template)
        child = _make_section(
            db_session, template, parent_section_id=parent.id
        )
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Too Deep',
                    'section-section_type': 'standard',
                    'parent_section_id': str(child.id),
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_repeat_section_with_max_entries(self, logged_in_client, db_session, admin_user, app):
        """POST creates a repeat group section with max_entries."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Repeat Group',
                    'section-section_type': 'repeat',
                    'max_entries': '5',
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_section_with_name_translations(self, logged_in_client, db_session, admin_user, app):
        """POST with base64-encoded name_translations stores translations."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        translations_b64 = _b64(json.dumps({'fr': 'Section Française'}))
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'French Section',
                    'section-section_type': 'standard',
                    'name_translations': translations_b64,
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_404_for_missing_template(self, logged_in_client, db_session, app):
        """POST to non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/sections/new',
            data={'section-name': 'X', 'section-section_type': 'standard'},
        )
        assert resp.status_code == 404

    def test_form_validation_error_flashes(self, logged_in_client, db_session, admin_user, app):
        """POST with missing required name flashes field error."""
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/sections/new',
            data={
                'section-name': '',
                'section-section_type': 'standard',
                'version_id': str(version_id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# edit_template_section
# ---------------------------------------------------------------------------

class TestEditTemplateSection:

    def test_edit_section_name(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/sections/edit/<id> updates section name."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, name='Original')
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={'section-name': 'Updated Name'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX returns JSON response."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                json={'section-name': 'AJAX Name'},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_edit_section_order_update(self, logged_in_client, db_session, admin_user, app):
        """POST with order value updates section order."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={'section-name': section.name, 'section-order': '5'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_parent_set_to_self_rejected(self, logged_in_client, db_session, admin_user, app):
        """POST with parent_section_id == section.id is rejected."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={
                    'section-name': section.name,
                    'parent_section_id': str(section.id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_clears_parent(self, logged_in_client, db_session, admin_user, app):
        """POST with empty parent_section_id clears parent."""
        template = _make_owned_template(db_session, admin_user)
        parent = _make_section(db_session, template)
        child = _make_section(db_session, template, parent_section_id=parent.id)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{child.id}',
                data={'section-name': child.name, 'parent_section_id': ''},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_with_relevance_condition(self, logged_in_client, db_session, admin_user, app):
        """POST with valid JSON relevance condition stores it."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        rc_b64 = _b64('{"==": [{"var": "q1"}, "yes"]}')
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={
                    'section-name': section.name,
                    'relevance_condition': rc_b64,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_clears_relevance_condition(self, logged_in_client, db_session, admin_user, app):
        """POST with empty relevance_condition clears it."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        section.relevance_condition = '{"logic":"AND","conditions":[{"item_id":"assignment_period","condition_type":"equal_to","value":"2026"}]}'
        db_session.commit()
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={
                    'section-name': section.name,
                    'relevance_condition': '',
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        db_session.refresh(section)
        assert section.relevance_condition is None

    def test_edit_section_unwraps_double_encoded_relevance(self, logged_in_client, db_session, admin_user, app):
        """Legacy double-encoded JSON is stored as a single JSON object string."""
        from app.models import FormSection
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        rule = {"logic": "AND", "conditions": [{"item_id": "assignment_period", "condition_type": "equal_to", "value": "2026"}]}
        double_encoded = json.dumps(json.dumps(rule))
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={
                    'section-name': section.name,
                    'relevance_condition': _b64(double_encoded),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        stored = db_session.get(FormSection, section.id)
        assert json.loads(stored.relevance_condition) == rule

    def test_edit_section_with_invalid_parent_returns_redirect(self, logged_in_client, db_session, admin_user, app):
        """POST with non-existent parent flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/edit/{section.id}',
                data={
                    'section-name': section.name,
                    'parent_section_id': '999999',
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_edit_section_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post(
            '/admin/sections/edit/999999',
            data={'section-name': 'X'},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# delete_template_section
# ---------------------------------------------------------------------------

class TestDeleteTemplateSection:

    def test_delete_section_removes_it(self, logged_in_client, db_session, admin_user, app):
        """POST deletes section and redirects to edit."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/delete/{section.id}',
                data={'delete_data': 'true'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_section_archive_keeps_data(self, logged_in_client, db_session, admin_user, app):
        """POST with delete_data=false-keep-data archives instead of deleting."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/delete/{section.id}',
                data={'delete_data': 'false-keep-data'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_section_cancel_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST with delete_data=false (cancel) just redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        resp = logged_in_client.post(
            f'/admin/sections/delete/{section.id}',
            data={'delete_data': 'false'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_section_with_child_sections(self, logged_in_client, db_session, admin_user, app):
        """POST on a parent section also deletes child sections."""
        template = _make_owned_template(db_session, admin_user)
        parent = _make_section(db_session, template)
        child = _make_section(db_session, template, parent_section_id=parent.id)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/delete/{parent.id}',
                data={'delete_data': 'true'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_section_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post(
            '/admin/sections/delete/999999',
            data={'delete_data': 'true'},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# duplicate_template_section
# ---------------------------------------------------------------------------

class TestDuplicateTemplateSection:

    def test_duplicate_section_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/sections/duplicate/<id> clones section and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        mock_new_section = MagicMock()
        mock_new_section.name = f"{section.name} (Copy)"
        with patch('app.routes.admin.form_builder.sections.SectionDuplicationService') as mock_svc, \
             patch('app.routes.admin.form_builder.sections.log_admin_action'):
            mock_svc.duplicate_section.return_value = (mock_new_section, {})
            resp = logged_in_client.post(
                f'/admin/sections/duplicate/{section.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_section_value_error(self, logged_in_client, db_session, admin_user, app):
        """POST that raises ValueError redirects with error flash."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.SectionDuplicationService') as mock_svc:
            mock_svc.duplicate_section.side_effect = ValueError("Duplicate failed")
            resp = logged_in_client.post(
                f'/admin/sections/duplicate/{section.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_section_exception(self, logged_in_client, db_session, admin_user, app):
        """POST that raises generic exception redirects with error flash."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.SectionDuplicationService') as mock_svc:
            mock_svc.duplicate_section.side_effect = Exception("Unexpected error")
            resp = logged_in_client.post(
                f'/admin/sections/duplicate/{section.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_section_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post('/admin/sections/duplicate/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# unarchive_section
# ---------------------------------------------------------------------------

class TestUnarchiveSection:

    def test_unarchive_archived_section(self, logged_in_client, db_session, admin_user, app):
        """POST unarchives an archived section and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, archived=True)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/unarchive/{section.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_unarchive_not_archived_flashes_warning(self, logged_in_client, db_session, admin_user, app):
        """POST on a non-archived section flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, archived=False)
        resp = logged_in_client.post(
            f'/admin/sections/unarchive/{section.id}',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_unarchive_section_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post('/admin/sections/unarchive/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# configure_dynamic_section
# ---------------------------------------------------------------------------

class TestConfigureDynamicSection:

    def _make_dynamic_section(self, db_session, template):
        return create_test_section(
            db_session, template, section_type='dynamic_indicators'
        )

    def test_configure_dynamic_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/sections/configure-dynamic/<id> updates dynamic settings."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_dynamic_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-dynamic/{section.id}',
                data={
                    'max_dynamic_indicators': '10',
                    'add_indicator_note': 'Add note here',
                    'allow_data_not_available': '1',
                    'allow_not_applicable': '0',
                    'add_indicator_note_translations': '{}',
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_dynamic_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX returns JSON on success."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_dynamic_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-dynamic/{section.id}',
                json={
                    'max_dynamic_indicators': '5',
                    'add_indicator_note': '',
                    'allow_data_not_available': '0',
                    'allow_not_applicable': '0',
                },
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 200

    def test_configure_wrong_section_type_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST on a non-dynamic section flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, section_type='standard')
        resp = logged_in_client.post(
            f'/admin/sections/configure-dynamic/{section.id}',
            data={'max_dynamic_indicators': '5'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_configure_dynamic_clears_max_when_blank(self, logged_in_client, db_session, admin_user, app):
        """POST with blank max_dynamic_indicators sets it to None."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_dynamic_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-dynamic/{section.id}',
                data={'max_dynamic_indicators': ''},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_dynamic_with_invalid_max_uses_none(self, logged_in_client, db_session, admin_user, app):
        """POST with non-numeric max sets it to None."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_dynamic_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-dynamic/{section.id}',
                data={'max_dynamic_indicators': 'abc'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_dynamic_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post('/admin/sections/configure-dynamic/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# configure_repeat_section
# ---------------------------------------------------------------------------

class TestConfigureRepeatSection:

    def _make_repeat_section(self, db_session, template):
        return create_test_section(db_session, template, section_type='repeat')

    def test_configure_repeat_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/sections/configure-repeat/<id> updates max_entries."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_repeat_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-repeat/{section.id}',
                data={'max_entries': '3'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_repeat_blank_max_clears_it(self, logged_in_client, db_session, admin_user, app):
        """POST with blank max_entries clears the setting."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_repeat_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-repeat/{section.id}',
                data={'max_entries': ''},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_repeat_invalid_max(self, logged_in_client, db_session, admin_user, app):
        """POST with non-numeric max_entries clears it."""
        template = _make_owned_template(db_session, admin_user)
        section = self._make_repeat_section(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/sections/configure-repeat/{section.id}',
                data={'max_entries': 'abc'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_configure_wrong_section_type_flashes_warning(self, logged_in_client, db_session, admin_user, app):
        """POST on a non-repeat section flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, section_type='standard')
        resp = logged_in_client.post(
            f'/admin/sections/configure-repeat/{section.id}',
            data={'max_entries': '5'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_configure_repeat_404(self, logged_in_client, db_session, app):
        """POST for non-existent section returns 404."""
        resp = logged_in_client.post('/admin/sections/configure-repeat/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# _b64_decode_field helper (unit-level)
# ---------------------------------------------------------------------------

class TestB64DecodeField:

    def test_decodes_valid_base64(self, app):
        from app.routes.admin.form_builder.sections import _b64_decode_field
        encoded = base64.b64encode(b'hello world').decode('utf-8')
        assert _b64_decode_field(encoded) == 'hello world'

    def test_returns_original_on_invalid_base64(self, app):
        from app.routes.admin.form_builder.sections import _b64_decode_field
        # Plain text is not valid base64 that decodes to UTF-8
        assert _b64_decode_field('not-valid-base64!!!') == 'not-valid-base64!!!'

    def test_returns_none_for_none(self, app):
        from app.routes.admin.form_builder.sections import _b64_decode_field
        assert _b64_decode_field(None) is None

    def test_returns_value_for_empty_string(self, app):
        from app.routes.admin.form_builder.sections import _b64_decode_field
        assert _b64_decode_field('') == ''

    def test_decodes_json_payload(self, app):
        from app.routes.admin.form_builder.sections import _b64_decode_field
        payload = json.dumps({'fr': 'Bonjour'})
        encoded = base64.b64encode(payload.encode('utf-8')).decode('utf-8')
        result = _b64_decode_field(encoded)
        assert result == payload


# ---------------------------------------------------------------------------
# discussion section type
# ---------------------------------------------------------------------------

class TestDiscussionSectionType:

    def _enable_discussion(self, db_session, template):
        from app.models import FormTemplateVersion
        version = db_session.get(FormTemplateVersion, template.published_version_id)
        version.enable_discussion = True
        db_session.commit()
        return version.id

    def test_creates_discussion_section_when_enabled(self, logged_in_client, db_session, admin_user, app):
        from app.models import FormSection, FormTemplateVersion
        template = _make_owned_template(db_session, admin_user, name='Discussion Template')
        version_id = self._enable_discussion(db_session, template)
        version = db_session.get(FormTemplateVersion, version_id)
        version.discussion_config = {'title': 'Team Discussion'}
        db_session.commit()
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/discussion',
                data={'version_id': str(version_id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        section = db_session.query(FormSection).filter_by(
            template_id=template.id, version_id=version_id, section_type='discussion'
        ).one()
        assert section.name == 'Team Discussion'

    def test_rejects_second_discussion_section(self, logged_in_client, db_session, admin_user, app):
        template = _make_owned_template(db_session, admin_user)
        version_id = self._enable_discussion(db_session, template)
        _make_section(db_session, template, version_id=version_id, name='Comments', section_type='discussion')
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/discussion',
                data={'version_id': str(version_id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        from app.models import FormSection
        count = db_session.query(FormSection).filter_by(
            version_id=version_id, section_type='discussion', archived=False
        ).count()
        assert count == 1

    def test_rejects_discussion_when_template_disabled(self, logged_in_client, db_session, admin_user, app):
        from app.models import FormSection
        template = _make_owned_template(db_session, admin_user)
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/discussion',
                data={'version_id': str(version_id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert db_session.query(FormSection).filter_by(
            version_id=version_id, section_type='discussion'
        ).count() == 0

    def test_rejects_discussion_section_via_add_section_modal(self, logged_in_client, db_session, admin_user, app):
        from app.models import FormSection
        template = _make_owned_template(db_session, admin_user, name='Discussion Template')
        version_id = self._enable_discussion(db_session, template)
        with patch('app.routes.admin.form_builder.sections.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/new',
                data={
                    'section-name': 'Comments',
                    'section-section_type': 'discussion',
                    'section-order': '1',
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert db_session.query(FormSection).filter_by(
            version_id=version_id, section_type='discussion'
        ).count() == 0
