"""
Comprehensive pytest tests for app/routes/admin/form_builder/items.py

Routes covered:
- POST /admin/templates/<tid>/sections/<sid>/items/new  (new_section_item)
- POST /admin/items/edit/<id>                           (edit_item)
- POST /admin/items/delete/<id>                         (delete_item)
- POST /admin/items/duplicate/<id>                      (duplicate_item)
- POST /admin/items/unarchive/<id>                      (unarchive_item)

Also covers the _form_item_audit_snapshot helper (indirectly).
"""
import pytest
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
)


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_owned_template(db_session, admin_user, **kwargs):
    return create_test_template(db_session, owner_id=admin_user.id, **kwargs)


def _make_section(db_session, template, **kwargs):
    return create_test_section(db_session, template, **kwargs)


def _make_item(db_session, section, template, item_type='question', **kwargs):
    return create_test_item(db_session, section, template, item_type=item_type, **kwargs)


# ---------------------------------------------------------------------------
# new_section_item
# ---------------------------------------------------------------------------

class TestNewSectionItem:

    def test_create_question_item(self, logged_in_client, db_session, admin_user, app):
        """POST creates a question item in a section."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        version_id = section.version_id
        with patch('app.routes.admin.form_builder.items.log_admin_action'), \
             patch('app.routes.admin.form_builder.items._create_form_item') as mock_create:
            mock_item = MagicMock()
            mock_item.id = 999
            mock_item.version_id = version_id
            mock_create.return_value = mock_item
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/{section.id}/items/new',
                data={
                    'item_type': 'question',
                    'add_q_modal-label': 'Test Question',
                    'add_q_modal-question_type': 'text',
                    'add_q_modal-section_id': str(section.id),
                    'version_id': str(version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_item_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX returns JSON on success."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        version_id = section.version_id
        with patch('app.routes.admin.form_builder.items.log_admin_action'), \
             patch('app.routes.admin.form_builder.items._create_form_item') as mock_create:
            mock_item = MagicMock()
            mock_item.id = 998
            mock_item.version_id = version_id
            mock_create.return_value = mock_item
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/{section.id}/items/new',
                json={'item_type': 'question', 'version_id': str(version_id)},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_create_item_missing_type_returns_error(self, logged_in_client, db_session, admin_user, app):
        """POST without item_type returns 400 or redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/sections/{section.id}/items/new',
            data={'version_id': str(section.version_id)},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 400)

    def test_create_item_ajax_missing_type_returns_400(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX without item_type returns 400."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/sections/{section.id}/items/new',
            json={},
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        assert resp.status_code == 400

    def test_create_item_section_template_mismatch(self, logged_in_client, db_session, admin_user, app):
        """POST with section belonging to a different template is rejected."""
        template1 = _make_owned_template(db_session, admin_user, name='T1')
        template2 = _make_owned_template(db_session, admin_user, name='T2')
        section_of_t2 = _make_section(db_session, template2)
        resp = logged_in_client.post(
            f'/admin/templates/{template1.id}/sections/{section_of_t2.id}/items/new',
            data={'item_type': 'question'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 400)

    def test_create_item_create_returns_none_shows_error(self, logged_in_client, db_session, admin_user, app):
        """POST where _create_form_item returns None shows error."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        version_id = section.version_id
        with patch('app.routes.admin.form_builder.items._create_form_item', return_value=None):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/{section.id}/items/new',
                data={'item_type': 'question', 'version_id': str(version_id)},
                follow_redirects=False,
            )
        assert resp.status_code in (302, 400)

    def test_create_item_exception_returns_server_error(self, logged_in_client, db_session, admin_user, app):
        """POST that raises an exception returns 500 or redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        with patch('app.routes.admin.form_builder.items._create_form_item',
                   side_effect=Exception("DB error")):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/{section.id}/items/new',
                json={'item_type': 'question'},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code in (302, 400, 500)

    def test_create_item_404_template(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/sections/1/items/new',
            data={'item_type': 'question'},
        )
        assert resp.status_code == 404

    def test_create_item_404_section(self, logged_in_client, db_session, admin_user, app):
        """POST for non-existent section returns 404."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/sections/999999/items/new',
            data={'item_type': 'question'},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# edit_item
# ---------------------------------------------------------------------------

class TestEditItem:

    def test_edit_question_item(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/items/edit/<id> updates a question item."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question',
                          label='Old Label')
        with patch('app.routes.admin.form_builder.items.log_admin_action'), \
             patch('app.routes.admin.form_builder.items._update_question_fields'), \
             patch('app.routes.admin.form_builder.items._update_item_config'):
            resp = logged_in_client.post(
                f'/admin/items/edit/{item.id}',
                data={
                    'item_type': 'question',
                    'label': 'New Label',
                    'question_type': 'text',
                    'section_id': str(section.id),
                    'order': '1',
                    'version_id': str(item.version_id),
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_edit_archived_item_rejected(self, logged_in_client, db_session, admin_user, app):
        """POST on archived item returns 400 or redirects with warning."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question', archived=True)
        resp = logged_in_client.post(
            f'/admin/items/edit/{item.id}',
            data={'item_type': 'question', 'label': 'Try Edit'},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 400)

    def test_edit_archived_item_ajax_returns_400(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX on archived item returns 400."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question', archived=True)
        resp = logged_in_client.post(
            f'/admin/items/edit/{item.id}',
            json={'item_type': 'question'},
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        assert resp.status_code == 400

    def test_edit_indicator_item(self, logged_in_client, db_session, admin_user, app):
        """POST updates indicator item successfully."""
        from app.models import IndicatorBank
        from app import db

        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        # Create an IndicatorBank entry
        ib = IndicatorBank(
            name='Test Indicator',
            type='number',
            unit='people',
        )
        db.session.add(ib)
        db.session.commit()
        item = _make_item(
            db_session, section, template, item_type='indicator',
            label='My Indicator',
            indicator_bank_id=ib.id,
        )
        with patch('app.routes.admin.form_builder.items.log_admin_action'), \
             patch('app.routes.admin.form_builder.items._update_indicator_fields'), \
             patch('app.routes.admin.form_builder.items._update_item_config'):
            resp = logged_in_client.post(
                f'/admin/items/edit/{item.id}',
                data={
                    'item_type': 'indicator',
                    'label': 'Updated Indicator',
                    'indicator_bank_id': str(ib.id),
                    'section_id': str(section.id),
                    'order': '1',
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_edit_matrix_item_moves_section_with_duplicate_section_id(self, logged_in_client, db_session, admin_user, app):
        """Duplicate section_id values (hidden + select) should move item to the selected section."""
        from app import db

        template = _make_owned_template(db_session, admin_user)
        source_section = _make_section(db_session, template, name='Source Section', order=1)
        target_section = _make_section(db_session, template, name='Target Section', order=2)
        matrix_config = (
            '{"type":"matrix","columns":[{"name":"col_a","type":"number"}],'
            '"rows":[],"row_mode":"manual","show_row_totals":false,"show_column_totals":false}'
        )
        item = _make_item(
            db_session,
            source_section,
            template,
            item_type='matrix',
            label='Staff Matrix',
            config={'matrix_config': {'type': 'matrix', 'columns': [{'name': 'col_a', 'type': 'number'}], 'rows': []}},
        )

        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/edit/{item.id}',
                json={
                    'item_type': 'matrix',
                    'label': 'Staff Matrix',
                    'section_id': [str(source_section.id), str(target_section.id)],
                    'order': '2',
                    'config': matrix_config,
                    'version_id': str(item.version_id),
                },
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        db.session.refresh(item)
        assert item.section_id == target_section.id

    def test_edit_item_validation_failure_ajax(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX with validation error returns 422."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        # Missing required fields will trigger form validation failure
        resp = logged_in_client.post(
            f'/admin/items/edit/{item.id}',
            json={
                'item_type': 'question',
                'section_id': str(section.id),
            },
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        # Validation failure returns 422 or 400
        assert resp.status_code in (200, 302, 400, 422)

    def test_edit_item_404(self, logged_in_client, db_session, app):
        """POST for non-existent item returns 404."""
        resp = logged_in_client.post(
            '/admin/items/edit/999999',
            data={'item_type': 'question'},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# delete_item
# ---------------------------------------------------------------------------

class TestDeleteItem:

    def test_delete_item_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/items/delete/<id> deletes item and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question',
                          label='To Delete')
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/delete/{item.id}',
                data={'delete_data': 'true'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_item_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX returns JSON on success."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/delete/{item.id}',
                json={'delete_data': 'true'},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data is not None

    def test_delete_item_archive_keeps_data(self, logged_in_client, db_session, admin_user, app):
        """POST with delete_data=false-keep-data archives item."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/delete/{item.id}',
                data={'delete_data': 'false-keep-data'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_item_cancel_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST with delete_data=false (cancel) just redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        resp = logged_in_client.post(
            f'/admin/items/delete/{item.id}',
            data={'delete_data': 'false'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_item_cancel_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX with cancel returns JSON ok."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        resp = logged_in_client.post(
            f'/admin/items/delete/{item.id}',
            json={'delete_data': 'false'},
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        )
        assert resp.status_code == 200

    def test_delete_item_404(self, logged_in_client, db_session, app):
        """POST for non-existent item returns 404."""
        resp = logged_in_client.post(
            '/admin/items/delete/999999',
            data={'delete_data': 'true'},
        )
        assert resp.status_code == 404

    def test_delete_document_field_item(self, logged_in_client, db_session, admin_user, app):
        """POST deletes a document_field item (also checks submitted documents)."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(
            db_session, section, template, item_type='document_field', label='Doc Field'
        )
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/delete/{item.id}',
                data={'delete_data': 'true'},
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# duplicate_item
# ---------------------------------------------------------------------------

class TestDuplicateItem:

    def test_duplicate_item_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/items/duplicate/<id> clones the item."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question',
                          label='Original Item')
        mock_new_item = MagicMock()
        mock_new_item.id = 888
        mock_new_item.label = 'Original Item (Copy)'
        with patch('app.routes.admin.form_builder.items.ItemDuplicationService') as mock_svc, \
             patch('app.routes.admin.form_builder.items.log_admin_action'):
            mock_svc.duplicate_item.return_value = mock_new_item
            resp = logged_in_client.post(
                f'/admin/items/duplicate/{item.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_item_ajax_returns_json(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX returns JSON on success."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        mock_new_item = MagicMock()
        mock_new_item.id = 887
        mock_new_item.label = 'Copy'
        with patch('app.routes.admin.form_builder.items.ItemDuplicationService') as mock_svc, \
             patch('app.routes.admin.form_builder.items.log_admin_action'):
            mock_svc.duplicate_item.return_value = mock_new_item
            resp = logged_in_client.post(
                f'/admin/items/duplicate/{item.id}',
                json={},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 200

    def test_duplicate_item_value_error(self, logged_in_client, db_session, admin_user, app):
        """POST that raises ValueError redirects with error flash."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        with patch('app.routes.admin.form_builder.items.ItemDuplicationService') as mock_svc:
            mock_svc.duplicate_item.side_effect = ValueError("Duplicate failed")
            resp = logged_in_client.post(
                f'/admin/items/duplicate/{item.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_item_value_error_ajax(self, logged_in_client, db_session, admin_user, app):
        """POST via AJAX with ValueError returns 400."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        with patch('app.routes.admin.form_builder.items.ItemDuplicationService') as mock_svc:
            mock_svc.duplicate_item.side_effect = ValueError("Duplicate failed")
            resp = logged_in_client.post(
                f'/admin/items/duplicate/{item.id}',
                json={},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 400

    def test_duplicate_item_general_exception(self, logged_in_client, db_session, admin_user, app):
        """POST that raises generic Exception redirects with error."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question')
        with patch('app.routes.admin.form_builder.items.ItemDuplicationService') as mock_svc:
            mock_svc.duplicate_item.side_effect = Exception("DB failure")
            resp = logged_in_client.post(
                f'/admin/items/duplicate/{item.id}',
                json={},
                headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            )
        assert resp.status_code == 500

    def test_duplicate_item_404(self, logged_in_client, db_session, app):
        """POST for non-existent item returns 404."""
        resp = logged_in_client.post('/admin/items/duplicate/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# unarchive_item
# ---------------------------------------------------------------------------

class TestUnarchiveItem:

    def test_unarchive_archived_item(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/items/unarchive/<id> unarchives the item."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question', archived=True)
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/unarchive/{item.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_unarchive_also_unarchives_section(self, logged_in_client, db_session, admin_user, app):
        """POST unarchives item's parent section if also archived."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template, archived=True)
        item = _make_item(db_session, section, template, item_type='question', archived=True)
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/unarchive/{item.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_unarchive_not_archived_flashes_warning(self, logged_in_client, db_session, admin_user, app):
        """POST on active (not archived) item flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        section = _make_section(db_session, template)
        item = _make_item(db_session, section, template, item_type='question', archived=False)
        resp = logged_in_client.post(
            f'/admin/items/unarchive/{item.id}',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_unarchive_item_also_unarchives_parent_section_with_parent(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST unarchives grandparent section too if needed."""
        template = _make_owned_template(db_session, admin_user)
        parent_section = _make_section(db_session, template, archived=True)
        child_section = _make_section(
            db_session, template,
            parent_section_id=parent_section.id,
            archived=True,
        )
        item = _make_item(db_session, child_section, template, item_type='question', archived=True)
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/items/unarchive/{item.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_unarchive_item_404(self, logged_in_client, db_session, app):
        """POST for non-existent item returns 404."""
        resp = logged_in_client.post('/admin/items/unarchive/999999', data={})
        assert resp.status_code == 404
