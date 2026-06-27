"""Tests for field mapping helpers and routes."""

import json
from unittest.mock import patch

import pytest

from app import db
from app.models import FormItem
from app.routes.admin.form_builder.helpers.field_mapping import (
    FieldMappingConflictError,
    link_draft_item,
    unlink_draft_item,
)
from app.utils.stable_key import generate_stable_key
from tests.factories import (
    create_test_draft_version,
    create_test_item,
    create_test_section,
    create_test_template,
    _grant_role_permission,
)

pytestmark = pytest.mark.unit


def _grant_publish(db_session):
    _grant_role_permission(db_session, 'admin_core', 'admin.templates.publish')
    db_session.commit()


def _draft_pair(db_session, admin_user):
    template = create_test_template(db_session, owner_id=admin_user.id)
    published = template.published_version
    draft = create_test_draft_version(db_session, template)
    return template, published, draft


class TestLinkDraftItem:
    def test_link_sets_stable_key(self, db_session, admin_user):
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published)
        draft_section = create_test_section(db_session, template, version=draft)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Pub Q'
        )
        pub_item.stable_key = pub_key
        draft_item = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Draft Q'
        )
        db_session.commit()

        with patch(
            'app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'
        ):
            key, warnings, displaced = link_draft_item(
                template=template,
                draft_version=draft,
                draft_item=draft_item,
                published_stable_key=pub_key,
            )
        assert key == pub_key
        assert displaced is None
        assert draft_item.stable_key == pub_key

    def test_conflict_without_confirm_raises(self, db_session, admin_user):
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published)
        draft_section = create_test_section(db_session, template, version=draft)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Pub Q'
        )
        pub_item.stable_key = pub_key
        holder = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Holder'
        )
        holder.stable_key = pub_key
        target = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Target'
        )
        db_session.commit()

        with pytest.raises(FieldMappingConflictError):
            link_draft_item(
                template=template,
                draft_version=draft,
                draft_item=target,
                published_stable_key=pub_key,
                confirm_reassign=False,
            )

    def test_confirm_reassign_displaces_other_draft_item(self, db_session, admin_user):
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published)
        draft_section = create_test_section(db_session, template, version=draft)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Pub Q'
        )
        pub_item.stable_key = pub_key
        holder = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Holder'
        )
        holder.stable_key = pub_key
        target = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Target'
        )
        db_session.commit()
        old_holder_key = holder.stable_key

        with patch(
            'app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'
        ):
            key, _warnings, displaced = link_draft_item(
                template=template,
                draft_version=draft,
                draft_item=target,
                published_stable_key=pub_key,
                confirm_reassign=True,
            )
        assert key == pub_key
        assert target.stable_key == pub_key
        assert holder.stable_key != old_holder_key
        assert displaced is not None
        assert displaced['id'] == holder.id

    def test_type_mismatch_returns_warning(self, db_session, admin_user):
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published)
        draft_section = create_test_section(db_session, template, version=draft)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Pub Q'
        )
        pub_item.stable_key = pub_key
        draft_item = create_test_item(
            db_session, draft_section, template, version=draft, item_type='indicator', label='Ind'
        )
        db_session.commit()

        with patch(
            'app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'
        ):
            _key, warnings, _displaced = link_draft_item(
                template=template,
                draft_version=draft,
                draft_item=draft_item,
                published_stable_key=pub_key,
            )
        assert any('type mismatch' in w.lower() for w in warnings)

    def test_unlink_generates_new_key(self, db_session, admin_user):
        template, published, draft = _draft_pair(db_session, admin_user)
        draft_section = create_test_section(db_session, template, version=draft)
        shared = generate_stable_key()
        draft_item = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Q'
        )
        draft_item.stable_key = shared
        db_session.commit()

        with patch(
            'app.routes.admin.form_builder.helpers.field_mapping.log_admin_action'
        ):
            new_key = unlink_draft_item(
                template=template,
                draft_version=draft,
                draft_item=draft_item,
            )
        assert new_key != shared
        assert draft_item.stable_key == new_key


class TestFieldMappingRoutes:
    def test_link_route_conflict_returns_409(self, logged_in_client, db_session, admin_user, app):
        _grant_publish(db_session)
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published)
        draft_section = create_test_section(db_session, template, version=draft)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Pub'
        )
        pub_item.stable_key = pub_key
        holder = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Holder'
        )
        holder.stable_key = pub_key
        target = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Target'
        )
        db_session.commit()

        with app.test_request_context():
            from flask_wtf.csrf import generate_csrf
            token = generate_csrf()

        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/{draft.id}/items/{target.id}/link',
            data=json.dumps({'published_stable_key': pub_key, 'confirm_reassign': False}),
            content_type='application/json',
            headers={'X-CSRFToken': token, 'Accept': 'application/json'},
        )
        assert resp.status_code == 409
        body = resp.get_json()
        assert body.get('conflict') is True

    def test_link_on_published_version_rejected(self, logged_in_client, db_session, admin_user, app):
        _grant_publish(db_session)
        template = create_test_template(db_session, owner_id=admin_user.id)
        published = template.published_version
        section = create_test_section(db_session, template, version=published)
        item = create_test_item(
            db_session, section, template, version=published, item_type='question', label='Q'
        )
        item.stable_key = generate_stable_key()
        db_session.commit()

        with app.test_request_context():
            from flask_wtf.csrf import generate_csrf
            token = generate_csrf()

        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/{published.id}/items/{item.id}/link',
            data=json.dumps({'published_stable_key': item.stable_key}),
            content_type='application/json',
            headers={'X-CSRFToken': token, 'Accept': 'application/json'},
        )
        assert resp.status_code == 400

    def test_preflight_includes_mapping_summary(self, logged_in_client, db_session, admin_user):
        _grant_publish(db_session)
        template, published, draft = _draft_pair(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published, name='S1', order=1)
        draft_section = create_test_section(db_session, template, version=draft, name='S1', order=1)
        pub_key = generate_stable_key()
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Q1', order=1
        )
        pub_item.stable_key = pub_key
        create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Q1 renamed', order=1
        )
        db_session.commit()

        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/deploy/preflight?version_id={draft.id}',
            headers={'Accept': 'application/json'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True
        assert 'mapping_summary' in data
        assert 'field_mapping_url' in data

    def test_field_mapping_page_loads(self, logged_in_client, db_session, admin_user):
        _grant_publish(db_session)
        template, _published, draft = _draft_pair(db_session, admin_user)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/versions/{draft.id}/field-mapping'
        )
        assert resp.status_code == 200
        assert b'Field mapping review' in resp.data or b'field mapping' in resp.data.lower()
