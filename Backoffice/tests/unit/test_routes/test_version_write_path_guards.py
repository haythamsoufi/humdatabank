"""Version guards on the data write paths other than the main assignment entry form.

Every path that writes submission data must refuse targets that belong to a template version
that is no longer live, because such rows would be invisible to users and skipped by the next
deploy's remap. The main entry form is covered in ``test_form_builder_version_lifecycle``.
"""

import io
import json

import pytest
from openpyxl import Workbook

from app import db
from app.models import (
    AssignmentEntityStatus,
    DynamicIndicatorData,
    FormData,
    FormSection,
    IndicatorBank,
    PublicSubmission,
)
from app.services.imports.kobo_data_import_service import KoboDataImportService
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_draft_version,
    create_test_item,
    create_test_public_submission,
    create_test_section,
    create_test_template,
    create_test_user,
)

pytestmark = [pytest.mark.unit]


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True


def _flashes(client):
    with client.session_transaction() as sess:
        return [message for _category, message in sess.get('_flashes', [])]


def _deploy_new_version(db_session, template):
    """Make a new version live and return (old_version, new_version)."""
    old = template.published_version
    draft = create_test_draft_version(db_session, template)
    template.published_version = draft
    db_session.commit()
    return old, draft


# ---------------------------------------------------------------------------
# Public submission edit / fill
# ---------------------------------------------------------------------------

class TestPublicSubmissionStaleGuard:
    def _form(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        section = create_test_section(db_session, template, name='Main', order=1)
        item = create_test_item(db_session, section, template, item_type='question', label='Q', order=1)
        country = create_test_country(db_session)
        submission, assigned_form, _token = create_test_public_submission(
            db_session, country=country, template=template
        )
        db_session.add(AssignmentEntityStatus(
            assigned_form_id=assigned_form.id,
            entity_type='country',
            entity_id=country.id,
            status='pending',
            is_public_available=True,
        ))
        db_session.commit()
        return template, item, country, submission

    def test_edit_with_outdated_form_is_refused_and_saves_nothing(
        self, client, db_session, admin_user
    ):
        template, item, _country, submission = self._form(db_session, admin_user)
        old_version_id = template.published_version_id
        _deploy_new_version(db_session, template)
        _login(client, admin_user.id)

        resp = client.post(
            f'/forms/public-submission/{submission.id}/edit',
            data={'form_version_id': str(old_version_id), f'field_value_{item.id}': 'x'},
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert f'/public-submission/{submission.id}/edit' in resp.headers['Location']
        assert any('updated while you were working' in m for m in _flashes(client))
        assert FormData.query.filter_by(public_submission_id=submission.id).count() == 0

    def test_edit_page_embeds_the_live_version_marker(self, client, db_session, admin_user):
        template, _item, _country, submission = self._form(db_session, admin_user)
        _login(client, admin_user.id)

        resp = client.get(f'/forms/public-submission/{submission.id}/edit')

        assert resp.status_code == 200
        assert (
            f'name="form_version_id" value="{template.published_version_id}"'
            in resp.get_data(as_text=True)
        )

    def test_fill_with_outdated_form_creates_no_submission(self, client, db_session, admin_user):
        template, _item, country, submission = self._form(db_session, admin_user)
        token = submission.assigned_form.unique_token
        old_version_id = template.published_version_id
        _deploy_new_version(db_session, template)
        before = PublicSubmission.query.count()

        resp = client.post(
            f'/forms/public/{token}',
            data={
                'submit_form': '1',
                'submitter_name': 'Someone',
                'submitter_email': 'someone@example.com',
                'country_id': str(country.id),
                'form_version_id': str(old_version_id),
            },
            follow_redirects=False,
        )

        assert resp.status_code == 302
        assert PublicSubmission.query.count() == before
        assert any('updated while you were working' in m for m in _flashes(client))

    def test_fill_page_embeds_the_live_version_marker(self, client, db_session, admin_user):
        template, _item, _country, submission = self._form(db_session, admin_user)

        resp = client.get(f'/forms/public/{submission.assigned_form.unique_token}')

        assert resp.status_code == 200
        assert (
            f'name="form_version_id" value="{template.published_version_id}"'
            in resp.get_data(as_text=True)
        )


# ---------------------------------------------------------------------------
# Data Explorer: apply imputed value
# ---------------------------------------------------------------------------

class TestApplyImputedValueVersionGuard:
    URL = '/admin/data-exploration/apply-imputed-value'

    def _setup(self, db_session):
        user = create_test_user(db_session, role='system_manager')
        template = create_test_template(db_session, owner_id=user.id)
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, template=template)
        section = create_test_section(db_session, template, name='Old', order=1)
        old_item = create_test_item(db_session, section, template, type='number', label='Old item')
        _old, new_version = _deploy_new_version(db_session, template)
        new_section = create_test_section(db_session, template, version=new_version, name='New', order=1)
        new_item = create_test_item(
            db_session, new_section, template, version=new_version, type='number', label='New item'
        )
        return user, aes, old_item, new_item

    def test_cannot_create_a_value_for_a_field_of_an_older_version(self, client, db_session):
        user, aes, old_item, _new_item = self._setup(db_session)
        _login(client, user.id)

        resp = client.post(
            self.URL,
            json={'submission_id': aes.id, 'form_item_id': old_item.id, 'imputed_value': '5'},
        )

        assert resp.status_code == 400
        assert 'older version' in resp.get_data(as_text=True)
        assert FormData.query.filter_by(
            assignment_entity_status_id=aes.id, form_item_id=old_item.id
        ).count() == 0

    def test_live_field_still_works(self, client, db_session):
        user, aes, _old_item, new_item = self._setup(db_session)
        _login(client, user.id)

        resp = client.post(
            self.URL,
            json={'submission_id': aes.id, 'form_item_id': new_item.id, 'imputed_value': '5'},
        )

        assert resp.status_code == 200, resp.get_data(as_text=True)
        row = FormData.query.filter_by(
            assignment_entity_status_id=aes.id, form_item_id=new_item.id
        ).one()
        assert row.imputed_value == '5'

    def test_existing_row_on_an_older_version_can_still_be_updated(self, client, db_session):
        user, aes, old_item, _new_item = self._setup(db_session)
        db_session.add(FormData(
            assignment_entity_status_id=aes.id, form_item_id=old_item.id, value='1',
        ))
        db_session.commit()
        _login(client, user.id)

        resp = client.post(
            self.URL,
            json={'submission_id': aes.id, 'form_item_id': old_item.id, 'imputed_value': '7'},
        )

        assert resp.status_code == 200, resp.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Dynamic indicators
# ---------------------------------------------------------------------------

class TestDynamicIndicatorVersionGuard:
    def _setup(self, db_session):
        user = create_test_user(db_session, role='system_manager')
        template = create_test_template(db_session, owner_id=user.id)
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, template=template)
        old_section = FormSection(
            template_id=template.id, name='Dyn', order=1,
            version_id=template.published_version_id, section_type='dynamic_indicators',
        )
        db_session.add(old_section)
        _old, new_version = _deploy_new_version(db_session, template)
        new_section = FormSection(
            template_id=template.id, name='Dyn', order=1,
            version_id=new_version.id, section_type='dynamic_indicators',
        )
        indicator = IndicatorBank(name='Ind', type='number', archived=False, emergency=False)
        db_session.add_all([new_section, indicator])
        db_session.commit()
        return user, aes, old_section, new_section, indicator

    def _add(self, client, aes, section, indicator):
        return client.post(
            '/api/forms/dynamic-indicators/add',
            data=json.dumps({
                'assignment_entity_status_id': aes.id,
                'section_id': section.id,
                'indicator_bank_id': indicator.id,
            }),
            content_type='application/json',
        )

    def test_rejects_a_section_from_an_older_version(self, client, db_session):
        user, aes, old_section, _new, indicator = self._setup(db_session)
        _login(client, user.id)

        resp = self._add(client, aes, old_section, indicator)

        assert resp.status_code == 400
        assert 'older version' in resp.get_data(as_text=True)
        assert DynamicIndicatorData.query.filter_by(assignment_entity_status_id=aes.id).count() == 0

    def test_accepts_a_section_from_the_live_version(self, client, db_session):
        user, aes, _old, new_section, indicator = self._setup(db_session)
        _login(client, user.id)

        resp = self._add(client, aes, new_section, indicator)

        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert DynamicIndicatorData.query.filter_by(
            assignment_entity_status_id=aes.id, section_id=new_section.id
        ).count() == 1


# ---------------------------------------------------------------------------
# KoBo data import into an existing template
# ---------------------------------------------------------------------------

def _kobo_workbook():
    wb = Workbook()
    ws = wb.active
    ws.append(['Country', 'Cases'])
    ws.append(['Alpha', 12])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestKoboImportVersionGuard:
    def _config(self, user, template, country, item):
        return {
            'create_template': False,
            'existing_template_id': template.id,
            'column_to_item_mapping': {'1': item.id},
            'entity_column_index': 0,
            'columns_to_import': [0, 1],
            'entity_mapping': {'Alpha': {'country_id': country.id}},
            'period_name': 'Imported 2024',
            'owned_by': user.id,
        }

    def _setup(self, db_session):
        user = create_test_user(db_session, role='system_manager')
        template = create_test_template(db_session, owner_id=user.id)
        country = create_test_country(db_session)
        old_section = create_test_section(db_session, template, name='Old', order=1)
        old_item = create_test_item(db_session, old_section, template, type='number', label='Cases')
        _old, new_version = _deploy_new_version(db_session, template)
        new_section = create_test_section(db_session, template, version=new_version, name='New', order=1)
        new_item = create_test_item(
            db_session, new_section, template, version=new_version, type='number', label='Cases'
        )
        return user, template, country, old_item, new_item

    def test_mapping_to_an_item_of_an_older_version_is_refused(self, app, db_session):
        user, template, country, old_item, _new = self._setup(db_session)

        result = KoboDataImportService.execute_import(
            _kobo_workbook(), self._config(user, template, country, old_item)
        )

        assert result['success'] is False
        assert 'live version' in result['message']
        assert FormData.query.filter_by(form_item_id=old_item.id).count() == 0

    def test_mapping_to_an_item_of_another_template_is_refused(self, app, db_session):
        user, template, country, _old, _new = self._setup(db_session)
        other = create_test_template(db_session, owner_id=user.id)
        other_section = create_test_section(db_session, other, name='O', order=1)
        other_item = create_test_item(db_session, other_section, other, type='number', label='X')

        result = KoboDataImportService.execute_import(
            _kobo_workbook(), self._config(user, template, country, other_item)
        )

        assert result['success'] is False
        assert 'live version' in result['message']

    def test_mapping_to_a_live_item_imports_the_value(self, app, db_session):
        user, template, country, _old, new_item = self._setup(db_session)

        result = KoboDataImportService.execute_import(
            _kobo_workbook(), self._config(user, template, country, new_item)
        )

        assert result['success'] is True, result
        db.session.expire_all()
        rows = FormData.query.filter_by(form_item_id=new_item.id).all()
        assert len(rows) == 1
        assert str(rows[0].value) in ('12', '12.0')
