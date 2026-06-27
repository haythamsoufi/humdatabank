"""
Comprehensive pytest tests for app/routes/admin/form_builder/versions.py

Routes covered:
- POST /admin/templates/<id>/deploy                         (deploy_template_version)
- POST /admin/templates/<id>/discard_draft                  (discard_template_draft)
- POST /admin/templates/<id>/versions/<vid>/delete          (delete_template_version)
- POST /admin/templates/<id>/draft_comment                  (update_draft_comment)
- POST /admin/templates/<id>/versions/new                   (create_draft_version)
- POST /admin/templates/<id>/versions/<vid>/comment         (update_version_comment)
"""
import pytest
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_template,
    create_test_draft_version,
    create_test_section,
    create_test_item,
    _grant_role_permission,
)


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant_template_permissions(db_session):
    """Grant extra template permissions (publish, delete) to admin_core role."""
    for perm in ('admin.templates.publish', 'admin.templates.delete'):
        _grant_role_permission(db_session, 'admin_core', perm)
    db_session.commit()


def _make_owned_template(db_session, admin_user, **kwargs):
    return create_test_template(db_session, owner_id=admin_user.id, **kwargs)


def _make_draft(db_session, template, **kwargs):
    return create_test_draft_version(db_session, template, **kwargs)


# ---------------------------------------------------------------------------
# deploy_template_version
# ---------------------------------------------------------------------------

class TestDeployTemplateVersion:

    def test_deploy_draft_version_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/deploy deploys the draft version."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions.register_post_commit',
                   side_effect=None, create=True):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deploy_no_draft_found_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST without a draft version to deploy flashes warning."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        # No draft version exists — only the published one created by factory
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/deploy',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_deploy_access_denied_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST when access is denied redirects to manage_templates."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        _make_draft(db_session, template)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deploy_with_invalid_indicator_items_blocks_deploy(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST when indicator items have missing bank refs is blocked."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        section = create_test_section(db_session, template, version=draft)
        # Item with NULL indicator_bank_id
        item = create_test_item(
            db_session, section, template, version=draft,
            item_type='indicator',
            indicator_bank_id=None,
        )
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deploy_archives_previous_published_version(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST archives the previously published version when deploying a new one."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions.register_post_commit',
                   side_effect=None, create=True):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deploy_404_for_missing_template(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.post(
            '/admin/templates/999999/deploy',
            data={'version_id': '1'},
        )
        assert resp.status_code == 404

    def test_deploy_exception_redirects_with_error(self, logged_in_client, db_session, admin_user, app):
        """POST that raises an exception redirects with error flash."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch(
            'app.routes.admin.form_builder.versions.FormTemplateVersion'
        ) as mock_ver_cls:
            mock_ver_cls.query.filter_by.side_effect = Exception("DB error")
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_deploy_invalid_indicators_ajax_returns_json(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with AJAX headers returns JSON error when indicator refs are invalid."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        section = create_test_section(db_session, template, version=draft)
        create_test_item(
            db_session, section, template, version=draft,
            item_type='indicator',
            indicator_bank_id=None,
        )
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/deploy',
            json={'version_id': str(draft.id)},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'indicator' in data.get('error', '').lower()

    def test_deploy_success_redirect_includes_version_id(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST deploy redirects to edit page with the deployed version_id."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions.register_post_commit',
                   side_effect=None, create=True):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert f'version_id={draft.id}' in resp.headers.get('Location', '')

    def test_deploy_preflight_returns_estimate(self, logged_in_client, db_session, admin_user, app):
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/deploy/preflight?version_id={draft.id}'
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'estimate' in data

    def test_deploy_remaps_form_data_on_publish(
        self, logged_in_client, db_session, admin_user, app
    ):
        from app.models import FormData
        from app.utils.stable_key import generate_stable_key
        from tests.factories import create_test_assignment_entity_status, create_test_item, create_test_section

        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        published = template.published_version
        pub_section = create_test_section(db_session, template, version=published)
        draft = _make_draft(db_session, template)
        draft_section = create_test_section(db_session, template, version=draft)
        shared_key = generate_stable_key()

        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Q1'
        )
        pub_item.stable_key = shared_key
        draft_item = create_test_item(
            db_session, draft_section, template, version=draft, item_type='question', label='Q1'
        )
        draft_item.stable_key = shared_key
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = FormData(assignment_entity_status_id=aes.id, form_item_id=pub_item.id, value='7')
        db_session.add(row)
        db_session.commit()

        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions.register_post_commit'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        db_session.refresh(row)
        assert row.form_item_id == draft_item.id

    def test_deploy_schedules_notification_after_commit(
        self, logged_in_client, db_session, admin_user, app
    ):
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions.register_post_commit') as mock_post_commit:
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/deploy',
                data={'version_id': str(draft.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_post_commit.assert_called_once()
        assert mock_post_commit.call_args[0][1] == template.id


# ---------------------------------------------------------------------------
# discard_template_draft
# ---------------------------------------------------------------------------

class TestDiscardTemplateDraft:

    def test_discard_draft_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/discard_draft removes draft version."""
        template = _make_owned_template(db_session, admin_user)
        _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/discard_draft',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_discard_draft_no_draft_flashes_warning(self, logged_in_client, db_session, admin_user, app):
        """POST when no draft exists flashes warning and redirects."""
        template = _make_owned_template(db_session, admin_user)
        # No draft — only published version
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/discard_draft',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_discard_draft_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST when access denied redirects to manage_templates."""
        template = _make_owned_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/discard_draft',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_discard_draft_404_missing_template(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/discard_draft',
            data={},
        )
        assert resp.status_code == 404

    def test_discard_draft_no_draft_ajax_returns_json(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with AJAX headers returns JSON error when no draft exists."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/discard_draft',
            json={},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False


# ---------------------------------------------------------------------------
# delete_template_version
# ---------------------------------------------------------------------------

class TestDeleteTemplateVersion:

    def test_delete_non_published_version_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/versions/<vid>/delete removes a non-published version."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/{draft.id}/delete',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_cannot_delete_published_version(self, logged_in_client, db_session, admin_user, app):
        """POST cannot delete the currently published version."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        published_version_id = template.published_version_id
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/{published_version_id}/delete',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302  # Redirects with warning

    def test_delete_version_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST when access denied redirects to manage_templates."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/{draft.id}/delete',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_version_404_template(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.post(
            '/admin/templates/999999/versions/1/delete',
            data={},
        )
        assert resp.status_code == 404

    def test_delete_version_404_version(self, logged_in_client, db_session, admin_user, app):
        """POST for non-existent version redirects (NotFound is caught by exception handler)."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/999999/delete',
            data={},
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# update_draft_comment
# ---------------------------------------------------------------------------

class TestUpdateDraftComment:

    def test_update_draft_comment_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/draft_comment saves the comment."""
        template = _make_owned_template(db_session, admin_user)
        _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/draft_comment',
                data={'comment': 'My draft note'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_draft_comment_clears_when_empty(self, logged_in_client, db_session, admin_user, app):
        """POST with empty comment clears the existing note."""
        template = _make_owned_template(db_session, admin_user)
        _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/draft_comment',
                data={'comment': ''},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_draft_comment_no_draft_flashes_warning(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST when no draft exists flashes warning."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/draft_comment',
            data={'comment': 'Note'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_update_draft_comment_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST when access denied redirects."""
        template = _make_owned_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/draft_comment',
                data={'comment': 'Note'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_draft_comment_404(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/draft_comment',
            data={'comment': 'Note'},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# create_draft_version
# ---------------------------------------------------------------------------

class TestCreateDraftVersion:

    def test_create_draft_from_published_version(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/versions/new creates a new draft from published."""
        template = _make_owned_template(db_session, admin_user)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions._clone_template_structure'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/new',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_draft_from_explicit_source_version(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with source_version_id clones from that specific version."""
        template = _make_owned_template(db_session, admin_user)
        source_version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.versions.log_admin_action'), \
             patch('app.routes.admin.form_builder.versions._clone_template_structure'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/new',
                data={'source_version_id': str(source_version_id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_draft_invalid_source_version_flashes_warning(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with non-existent source_version_id flashes warning."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/new',
            data={'source_version_id': '999999'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_create_draft_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST when access denied redirects to manage_templates."""
        template = _make_owned_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/new',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_draft_404(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/versions/new',
            data={},
        )
        assert resp.status_code == 404

    def test_create_draft_exception_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST that raises exception redirects with error flash."""
        template = _make_owned_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.versions._clone_template_structure',
            side_effect=Exception("Clone failed"),
        ), patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/new',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_create_draft_blocked_when_draft_already_exists(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST when a draft already exists redirects to the existing draft."""
        template = _make_owned_template(db_session, admin_user)
        existing_draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions._clone_template_structure'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/new',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        assert f'version_id={existing_draft.id}' in resp.headers.get('Location', '')

    def test_create_draft_blocked_when_draft_exists_ajax_returns_json(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with AJAX headers returns JSON error when draft already exists."""
        template = _make_owned_template(db_session, admin_user)
        _make_draft(db_session, template)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/new',
            json={'source_version_id': template.published_version_id},
            headers={'X-Requested-With': 'XMLHttpRequest'},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False
        assert 'draft' in data.get('error', '').lower()


# ---------------------------------------------------------------------------
# update_version_comment
# ---------------------------------------------------------------------------

class TestUpdateVersionComment:

    def test_update_version_comment_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/<id>/versions/<vid>/comment saves comment."""
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/{draft.id}/comment',
                data={'comment': 'Version note'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_version_comment_clears_when_empty(
        self, logged_in_client, db_session, admin_user, app
    ):
        """POST with empty comment clears the existing note."""
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch('app.routes.admin.form_builder.versions.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/{draft.id}/comment',
                data={'comment': ''},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_version_comment_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST when access denied redirects."""
        template = _make_owned_template(db_session, admin_user)
        draft = _make_draft(db_session, template)
        with patch(
            'app.routes.admin.form_builder.versions.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/versions/{draft.id}/comment',
                data={'comment': 'Note'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_update_version_comment_404_template(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/999999/versions/1/comment',
            data={'comment': 'Note'},
        )
        assert resp.status_code == 404

    def test_update_version_comment_404_version(self, logged_in_client, db_session, admin_user, app):
        """POST for non-existent version redirects (NotFound is caught by exception handler)."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/999999/comment',
            data={'comment': 'Note'},
        )
        assert resp.status_code == 302
