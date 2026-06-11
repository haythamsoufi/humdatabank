"""Unit tests for app.routes.admin.form_builder.helpers.template_mgmt."""
import json
import pytest
from unittest.mock import patch, MagicMock
from werkzeug.datastructures import ImmutableMultiDict

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.template_mgmt import (
    _get_or_create_draft_version,
    _handle_template_pages,
    _handle_template_sharing,
    _populate_template_sharing,
    _ensure_template_access_or_redirect,
)
from tests.factories import (
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
    create_test_admin,
)


class TestGetOrCreateDraftVersion:
    def test_returns_existing_draft(self, app, db_session):
        user = create_test_admin(db_session)
        template = create_test_template(db_session)
        existing_draft = create_test_draft_version(db_session, template)

        draft = _get_or_create_draft_version(template, user.id)
        assert draft.id == existing_draft.id

    def test_creates_initial_draft_for_brand_new_template(self, app, db_session):
        from app.models import FormTemplate, FormTemplateVersion
        user = create_test_admin(db_session)

        # Create a template with NO versions
        template = FormTemplate()
        db_session.add(template)
        db_session.flush()

        draft = _get_or_create_draft_version(template, user.id)
        assert draft is not None
        assert draft.status == 'draft'
        assert draft.version_number == 1

    def test_creates_draft_from_published_version(self, app, db_session):
        from app.models import FormSection
        user = create_test_admin(db_session)
        template = create_test_template(db_session)
        # Published version exists, no draft
        pub_version_id = template.published_version_id
        assert pub_version_id is not None

        # Add a section to published version
        section = create_test_section(db_session, template)

        draft = _get_or_create_draft_version(template, user.id)
        assert draft is not None
        assert draft.status == 'draft'
        assert draft.id != pub_version_id

        # Cloned section should exist in draft
        cloned = FormSection.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).all()
        assert len(cloned) == 1

    def test_creates_published_baseline_when_missing(self, app, db_session):
        from app.models import FormTemplate, FormTemplateVersion
        user = create_test_admin(db_session)

        # Create template manually with a version but no published_version_id
        template = FormTemplate()
        db_session.add(template)
        db_session.flush()

        # Add a version but do not set as published
        version = FormTemplateVersion(
            template_id=template.id,
            version_number=1,
            status='published',
            name="Test"
        )
        db_session.add(version)
        db_session.flush()
        # Intentionally NOT setting template.published_version_id

        draft = _get_or_create_draft_version(template, user.id)
        assert draft is not None
        assert draft.status == 'draft'


class TestHandleTemplatePages:
    def test_creates_new_pages(self, app, db_session):
        from app.models import FormPage
        user = create_test_admin(db_session)
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        form_data = ImmutableMultiDict([
            ('page_names', 'Page One'),
            ('page_orders', '1'),
            ('page_ids', ''),
            ('page_name_translations', ''),
        ])

        _handle_template_pages(template, form_data, version.id)
        db_session.flush()

        pages = FormPage.query.filter_by(template_id=template.id, version_id=version.id).all()
        assert len(pages) == 1
        assert pages[0].name == 'Page One'

    def test_updates_existing_page(self, app, db_session):
        from app.models import FormPage
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        page = FormPage(
            template_id=template.id,
            version_id=version.id,
            name="Old Name",
            order=1
        )
        db_session.add(page)
        db_session.flush()

        form_data = ImmutableMultiDict([
            ('page_names', 'New Name'),
            ('page_orders', '2'),
            ('page_ids', str(page.id)),
            ('page_name_translations', ''),
        ])

        _handle_template_pages(template, form_data, version.id)
        db_session.flush()

        updated = FormPage.query.get(page.id)
        assert updated.name == 'New Name'
        assert updated.order == 2

    def test_deletes_removed_pages(self, app, db_session):
        from app.models import FormPage
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        page = FormPage(
            template_id=template.id,
            version_id=version.id,
            name="To Delete",
            order=1
        )
        db_session.add(page)
        db_session.flush()
        page_id = page.id

        # Submit with no pages (page will be deleted)
        form_data = ImmutableMultiDict([])

        _handle_template_pages(template, form_data, version.id)
        db_session.flush()

        assert FormPage.query.get(page_id) is None

    def test_creates_page_with_translations(self, app, db_session):
        from app.models import FormPage
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        translations = json.dumps({"en": "Page One"})
        form_data = ImmutableMultiDict([
            ('page_names', 'Page One'),
            ('page_orders', '1'),
            ('page_ids', ''),
            ('page_name_translations', translations),
        ])

        with app.test_request_context():
            app.config['SUPPORTED_LANGUAGES'] = ['en']
            _handle_template_pages(template, form_data, version.id)
            db_session.flush()

        pages = FormPage.query.filter_by(template_id=template.id, version_id=version.id).all()
        assert pages[0].name_translations == {"en": "Page One"}

    def test_invalid_order_uses_index(self, app, db_session):
        from app.models import FormPage
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        form_data = ImmutableMultiDict([
            ('page_names', 'Page A'),
            ('page_orders', 'not-a-number'),
            ('page_ids', ''),
            ('page_name_translations', ''),
        ])

        _handle_template_pages(template, form_data, version.id)
        db_session.flush()

        pages = FormPage.query.filter_by(template_id=template.id, version_id=version.id).all()
        assert len(pages) == 1
        assert pages[0].order == 1  # index 0 + 1


class TestHandleTemplateSharing:
    def test_adds_new_shares(self, app, db_session):
        from app.models import TemplateShare
        owner = create_test_admin(db_session)
        sharee = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action'):
            _handle_template_sharing(
                template,
                shared_admin_ids=[sharee.id],
                shared_by_user_id=owner.id
            )
        db_session.flush()

        shares = TemplateShare.query.filter_by(template_id=template.id).all()
        assert any(s.shared_with_user_id == sharee.id for s in shares)

    def test_removes_shares_not_in_list(self, app, db_session):
        from app.models import TemplateShare
        owner = create_test_admin(db_session)
        sharee1 = create_test_admin(db_session)
        sharee2 = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        # Share with sharee1 first
        share = TemplateShare(
            template_id=template.id,
            shared_with_user_id=sharee1.id,
            shared_by_user_id=owner.id
        )
        db_session.add(share)
        db_session.flush()

        # Now share only with sharee2 (sharee1 should be removed)
        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action'):
            _handle_template_sharing(
                template,
                shared_admin_ids=[sharee2.id],
                shared_by_user_id=owner.id
            )
        db_session.flush()

        shares = TemplateShare.query.filter_by(template_id=template.id).all()
        shared_ids = {s.shared_with_user_id for s in shares}
        assert sharee1.id not in shared_ids
        assert sharee2.id in shared_ids

    def test_does_not_share_with_owner(self, app, db_session):
        from app.models import TemplateShare
        owner = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action'):
            _handle_template_sharing(
                template,
                shared_admin_ids=[owner.id],
                shared_by_user_id=owner.id
            )
        db_session.flush()

        shares = TemplateShare.query.filter_by(
            template_id=template.id,
            shared_with_user_id=owner.id
        ).all()
        assert len(shares) == 0

    def test_empty_share_list_removes_all(self, app, db_session):
        from app.models import TemplateShare
        owner = create_test_admin(db_session)
        sharee = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        share = TemplateShare(
            template_id=template.id,
            shared_with_user_id=sharee.id,
            shared_by_user_id=owner.id
        )
        db_session.add(share)
        db_session.flush()

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action'):
            _handle_template_sharing(
                template,
                shared_admin_ids=[],
                shared_by_user_id=owner.id
            )
        db_session.flush()

        shares = TemplateShare.query.filter_by(template_id=template.id).all()
        assert len(shares) == 0

    def test_template_name_used_in_audit_log(self, app, db_session):
        owner = create_test_admin(db_session)
        sharee = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action') as mock_log:
            _handle_template_sharing(
                template,
                shared_admin_ids=[sharee.id],
                shared_by_user_id=owner.id,
                template_name="Custom Template Name"
            )
            if mock_log.called:
                call_kwargs = mock_log.call_args[1] if mock_log.call_args else {}
                description = call_kwargs.get('description', '')
                assert 'Custom Template Name' in description

    def test_none_share_ids_treated_as_empty(self, app, db_session):
        owner = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        # Should not raise
        with patch('app.routes.admin.form_builder.helpers.template_mgmt.log_admin_action'):
            _handle_template_sharing(
                template,
                shared_admin_ids=None,
                shared_by_user_id=owner.id
            )


class TestPopulateTemplateSharing:
    def test_populates_owner_field(self, app, db_session):
        owner = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        form = MagicMock()
        form.owned_by = MagicMock()
        form.shared_with_admins = MagicMock()

        _populate_template_sharing(form, template)

        assert form.owned_by.data == owner.id

    def test_populates_shared_users(self, app, db_session):
        from app.models import TemplateShare
        owner = create_test_admin(db_session)
        sharee = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        share = TemplateShare(
            template_id=template.id,
            shared_with_user_id=sharee.id,
            shared_by_user_id=owner.id
        )
        db_session.add(share)
        db_session.flush()

        form = MagicMock()
        form.owned_by = MagicMock()
        form.shared_with_admins = MagicMock()

        _populate_template_sharing(form, template)

        assert sharee.id in form.shared_with_admins.data

    def test_no_shares_returns_empty_list(self, app, db_session):
        owner = create_test_admin(db_session)
        template = create_test_template(db_session, owner_id=owner.id)

        form = MagicMock()
        form.owned_by = MagicMock()
        form.shared_with_admins = MagicMock()

        _populate_template_sharing(form, template)
        assert form.shared_with_admins.data == []


class TestEnsureTemplateAccessOrRedirect:
    def test_returns_none_when_access_allowed(self, app, db_session):
        user = create_test_admin(db_session)
        template = create_test_template(db_session)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.check_template_access', return_value=True):
            with patch('app.routes.admin.form_builder.helpers.template_mgmt.current_user') as mock_user:
                mock_user.id = user.id
                result = _ensure_template_access_or_redirect(template.id)

        assert result is None

    def test_returns_redirect_when_access_denied(self, app, db_session):
        user = create_test_admin(db_session)
        template = create_test_template(db_session)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.check_template_access', return_value=False):
            with patch('app.routes.admin.form_builder.helpers.template_mgmt.current_user') as mock_user:
                mock_user.id = user.id
                with app.test_request_context('/'):
                    result = _ensure_template_access_or_redirect(template.id)

        assert result is not None

    def test_returns_redirect_with_version_id(self, app, db_session):
        user = create_test_admin(db_session)
        template = create_test_template(db_session)
        version = create_test_draft_version(db_session, template)

        with patch('app.routes.admin.form_builder.helpers.template_mgmt.check_template_access', return_value=False):
            with patch('app.routes.admin.form_builder.helpers.template_mgmt.current_user') as mock_user:
                mock_user.id = user.id
                with app.test_request_context('/'):
                    result = _ensure_template_access_or_redirect(template.id, version_id=version.id)

        assert result is not None
