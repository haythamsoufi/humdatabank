"""Excel import skips locked section/page values and warns only when they differ."""
import pytest

from app.models.assignments import AssignmentPageStatus
from app.models.enums import AssignmentSectionStatusValue
from app.models.forms import FormData, FormPage
from app.services.imports.scoped_import_guard import (
    filter_locked_field_updates,
    filter_staged_import_payload,
    values_differ,
)
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_item,
    create_test_section,
)


@pytest.mark.unit
class TestValuesDiffer:
    def test_same_simple_value_is_not_different(self):
        existing = FormData(value='10')
        assert values_differ({'value': '10'}, existing) is False
        assert values_differ({'value': 10}, existing) is False

    def test_changed_value_is_different(self):
        existing = FormData(value='10')
        assert values_differ({'value': '11'}, existing) is True

    def test_empty_incoming_matches_missing_entry(self):
        assert values_differ({'value': None}, None) is False
        assert values_differ({'value': '7'}, None) is True


@pytest.mark.unit
class TestFilterLockedFieldUpdates:
    def test_identical_locked_page_is_skipped_without_warning(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            locked_page = FormPage(
                template_id=template.id,
                version_id=template.published_version_id,
                name='People reached',
                order=1,
            )
            open_page = FormPage(
                template_id=template.id,
                version_id=template.published_version_id,
                name='Finance',
                order=2,
            )
            db_session.add_all([locked_page, open_page])
            db_session.commit()
            locked = create_test_section(db_session, template, name='People reached')
            locked.page_id = locked_page.id
            open_section = create_test_section(db_session, template, name='Finance', order=2)
            open_section.page_id = open_page.id
            locked_item = create_test_item(db_session, locked, template)
            open_item = create_test_item(db_session, open_section, template)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=locked_page.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=locked_item.id,
                value='10',
            ))
            db_session.commit()

            writable, warnings = filter_locked_field_updates(aes, {
                locked_item.id: {'value': '10'},
                open_item.id: {'value': '4'},
            })
            assert locked_item.id not in writable
            assert writable[open_item.id]['value'] == '4'
            assert warnings == []

    def test_different_locked_page_warns_once(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            page = FormPage(
                template_id=template.id,
                version_id=template.published_version_id,
                name='Overview',
                order=1,
            )
            db_session.add(page)
            db_session.commit()
            section = create_test_section(db_session, template, name='Overview section')
            section.page_id = page.id
            item = create_test_item(db_session, section, template)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=page.id,
                status=AssignmentSectionStatusValue.approved.value,
            ))
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value='old',
            ))
            db_session.commit()

            writable, warnings = filter_locked_field_updates(aes, {
                item.id: {'value': 'new'},
            })
            assert writable == {}
            assert len(warnings) == 1
            assert warnings[0]['scope'] == 'page'
            assert 'Overview' in warnings[0]['message']


@pytest.mark.unit
class TestFilterStagedImportPayload:
    def test_drops_locked_fields_and_counts_remaining(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            locked_page = FormPage(
                template_id=template.id,
                version_id=template.published_version_id,
                name='Locked',
                order=1,
            )
            open_page = FormPage(
                template_id=template.id,
                version_id=template.published_version_id,
                name='Open',
                order=2,
            )
            db_session.add_all([locked_page, open_page])
            db_session.commit()
            locked = create_test_section(db_session, template, name='Locked')
            locked.page_id = locked_page.id
            open_section = create_test_section(db_session, template, name='Open', order=2)
            open_section.page_id = open_page.id
            locked_item = create_test_item(db_session, locked, template)
            open_item = create_test_item(db_session, open_section, template)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=locked_page.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=locked_item.id,
                value='same',
            ))
            db_session.commit()

            payload = {
                'fields': {
                    str(locked_item.id): {'value': 'same'},
                    str(open_item.id): {'value': 'fresh'},
                },
                'matrices': {},
                'dynamic_indicators': [],
                'repeat_slots': [],
            }
            extra = filter_staged_import_payload(aes, payload)
            assert extra['warnings'] == []
            assert extra['updated_count'] == 1
            assert str(locked_item.id) not in payload['fields']
            assert str(open_item.id) in payload['fields']
