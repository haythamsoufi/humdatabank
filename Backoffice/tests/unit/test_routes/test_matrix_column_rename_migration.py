"""Renaming matrix column codes in the form builder migrates saved data on request."""

import json
from unittest.mock import patch

import pytest

from app import db
from app.models import FormData, FormItem, FormTemplateVersion
from tests.factories import (
    _grant_role_permission,
    create_test_assignment_entity_status,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = [pytest.mark.unit]


def _matrix_config(*codes):
    return {
        'type': 'matrix',
        'rows': ['61', '62'],
        'columns': [{'name': code, 'type': 'number_whole'} for code in codes],
        'show_row_totals': False,
    }


def _setup(db_session, admin_user, *, codes=('SP1', 'SP2'), disagg=None):
    for perm in ('admin.templates.edit', 'admin.templates.publish', 'admin.templates.delete'):
        _grant_role_permission(db_session, 'admin_core', perm)
    template = create_test_template(db_session, owner_id=admin_user.id)
    section = create_test_section(db_session, template, name='Main', order=1)
    item = create_test_item(
        db_session, section, template, item_type='matrix', label='Matrix',
        config={'matrix_config': _matrix_config(*codes)},
    )
    aes = create_test_assignment_entity_status(db_session, template=template, period_name='2024')
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item.id,
        disagg_data=disagg if disagg is not None else {'61_SP1': 5, '62_SP1': 6, '61_SP2': 7},
    )
    db_session.add(row)
    db_session.commit()
    return template, section, item, aes, row


def _edit(client, item, section, new_codes, *, renames=None, migrate=False):
    payload = {
        'item_type': 'matrix',
        'label': 'Matrix',
        'section_id': str(section.id),
        'order': '1',
        'config': json.dumps(_matrix_config(*new_codes)),
        'version_id': str(item.version_id),
    }
    if renames is not None:
        payload['matrix_column_renames'] = json.dumps(renames)
    if migrate:
        payload['migrate_matrix_columns'] = '1'
    with patch('app.routes.admin.form_builder.items.log_admin_action'):
        return client.post(f'/admin/items/edit/{item.id}', json=payload)


def _data(row_id):
    db.session.expire_all()
    return FormData.query.get(row_id).disagg_data


def _codes(item_id):
    db.session.expire_all()
    cfg = FormItem.query.get(item_id).config['matrix_config']
    return [c['name'] for c in cfg['columns']]


class TestEditItemColumnRename:
    def test_migrate_moves_saved_cells_to_the_new_code(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, row = _setup(db_session, admin_user)
        resp = _edit(
            logged_in_client, item, section, ['SP1_new', 'SP2'],
            renames=[{'from': 'SP1', 'to': 'SP1_new'}], migrate=True,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _codes(item.id) == ['SP1_new', 'SP2']
        assert _data(row.id) == {'61_SP1_new': 5, '62_SP1_new': 6, '61_SP2': 7}

    def test_without_the_flag_data_is_left_under_the_old_code(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, row = _setup(db_session, admin_user)
        resp = _edit(
            logged_in_client, item, section, ['SP1_new', 'SP2'],
            renames=[{'from': 'SP1', 'to': 'SP1_new'}], migrate=False,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _codes(item.id) == ['SP1_new', 'SP2']
        assert _data(row.id) == {'61_SP1': 5, '62_SP1': 6, '61_SP2': 7}

    def test_templated_code_resolves_for_each_assignment(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, row = _setup(db_session, admin_user)
        resp = _edit(
            logged_in_client, item, section, ['SP1_[assignment_period]', 'SP2'],
            renames=[{'from': 'SP1', 'to': 'SP1_[assignment_period]'}], migrate=True,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _codes(item.id) == ['SP1_[assignment_period]', 'SP2']
        assert _data(row.id) == {'61_SP1_2024': 5, '62_SP1_2024': 6, '61_SP2': 7}

    def test_submitted_at_is_not_bumped(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, row = _setup(db_session, admin_user)
        db.session.expire_all()
        before = FormData.query.get(row.id).submitted_at
        _edit(
            logged_in_client, item, section, ['SP1_new', 'SP2'],
            renames=[{'from': 'SP1', 'to': 'SP1_new'}], migrate=True,
        )
        db.session.expire_all()
        assert FormData.query.get(row.id).submitted_at == before

    def test_forged_rename_for_a_missing_column_is_ignored(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, row = _setup(db_session, admin_user)
        resp = _edit(
            logged_in_client, item, section, ['SP1', 'SP2'],
            renames=[{'from': 'NOPE', 'to': 'SP1'}], migrate=True,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert _data(row.id) == {'61_SP1': 5, '62_SP1': 6, '61_SP2': 7}

    def test_custom_formula_follows_the_rename_even_without_migrating(
        self, logged_in_client, db_session, admin_user
    ):
        _t, section, item, _aes, _row = _setup(db_session, admin_user)
        config = _matrix_config('SP1_new', 'SP2')
        config['columns'].append({
            'name': 'calc', 'type': 'calculated',
            'calculation': {'operation': 'formula', 'formula': 'SP1 + SP2', 'sources': []},
        })
        payload = {
            'item_type': 'matrix', 'label': 'Matrix', 'section_id': str(section.id), 'order': '1',
            'config': json.dumps(config), 'version_id': str(item.version_id),
            'matrix_column_renames': json.dumps([{'from': 'SP1', 'to': 'SP1_new'}]),
        }
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(f'/admin/items/edit/{item.id}', json=payload)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.expire_all()
        columns = FormItem.query.get(item.id).config['matrix_config']['columns']
        assert columns[2]['calculation']['formula'] == 'SP1_new + SP2'

    def test_template_variable_lookup_follows_the_rename(self, logged_in_client, db_session, admin_user):
        template, section, item, _aes, _row = _setup(db_session, admin_user)
        version = FormTemplateVersion.query.get(item.version_id)
        version.variables = {
            'planned': {'source_form_item_id': item.id, 'matrix_column_name': 'SP1'},
            'other': {'source_form_item_id': item.id, 'matrix_column_name': 'SP2'},
        }
        db_session.commit()
        resp = _edit(
            logged_in_client, item, section, ['SP1_new', 'SP2'],
            renames=[{'from': 'SP1', 'to': 'SP1_new'}], migrate=True,
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)
        db.session.expire_all()
        variables = FormTemplateVersion.query.get(item.version_id).variables
        assert variables['planned']['matrix_column_name'] == 'SP1_new'
        assert variables['other']['matrix_column_name'] == 'SP2'


class TestColumnCodeValidationOnSave:
    def test_edit_rejects_duplicate_codes_and_keeps_the_stored_config(
        self, logged_in_client, db_session, admin_user
    ):
        _t, section, item, _aes, _row = _setup(db_session, admin_user)
        resp = _edit(logged_in_client, item, section, ['SP1', 'SP1'])
        assert resp.status_code == 400
        body = resp.get_json()
        assert body['success'] is False
        assert 'unique' in body['error'] or 'unique' in json.dumps(body)
        assert body['errors']['matrix_config']
        assert _codes(item.id) == ['SP1', 'SP2']

    def test_edit_rejects_reserved_code(self, logged_in_client, db_session, admin_user):
        _t, section, item, _aes, _row = _setup(db_session, admin_user)
        resp = _edit(logged_in_client, item, section, ['SP1', 'Total'])
        assert resp.status_code == 400
        assert _codes(item.id) == ['SP1', 'SP2']

    def test_create_rejects_duplicate_codes(self, logged_in_client, db_session, admin_user):
        template, section, _item, _aes, _row = _setup(db_session, admin_user)
        before = FormItem.query.filter_by(section_id=section.id).count()
        payload = {
            'item_type': 'matrix', 'label': 'New matrix', 'section_id': str(section.id),
            'config': json.dumps(_matrix_config('A', 'A')), 'version_id': str(section.version_id),
        }
        with patch('app.routes.admin.form_builder.items.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/sections/{section.id}/items/new', json=payload
            )
        assert resp.status_code == 400
        db.session.expire_all()
        assert FormItem.query.filter_by(section_id=section.id).count() == before


class TestRenamePreviewEndpoint:
    def _preview(self, client, item, renames):
        return client.post(
            f'/admin/items/{item.id}/matrix-column-rename-preview',
            json={'renames': renames, 'version_id': item.version_id},
        )

    def test_counts_what_would_move_without_changing_anything(self, logged_in_client, db_session, admin_user):
        _t, _section, item, _aes, row = _setup(db_session, admin_user)
        resp = self._preview(logged_in_client, item, [{'from': 'SP1', 'to': 'SP1_new'}])
        assert resp.status_code == 200, resp.get_data(as_text=True)
        preview = resp.get_json()['preview']
        assert preview['rows_affected'] == 1
        assert preview['cells'] == 2
        assert preview['assignments'] == 1
        assert _data(row.id) == {'61_SP1': 5, '62_SP1': 6, '61_SP2': 7}

    def test_no_saved_data_means_nothing_to_migrate(self, logged_in_client, db_session, admin_user):
        _t, _section, item, _aes, row = _setup(db_session, admin_user, disagg={'61_SP2': 1})
        preview = self._preview(logged_in_client, item, [{'from': 'SP1', 'to': 'SP1_new'}]).get_json()['preview']
        assert preview['rows_affected'] == 0
        assert preview['variables'] == []

    def test_rejects_non_matrix_items(self, logged_in_client, db_session, admin_user):
        template, section, _item, _aes, _row = _setup(db_session, admin_user)
        question = create_test_item(db_session, section, template, item_type='question', label='Q')
        resp = self._preview(logged_in_client, question, [{'from': 'A', 'to': 'B'}])
        assert resp.status_code == 400
