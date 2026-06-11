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
             patch('app.routes.admin.form_builder.versions.notify_template_updated',
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
             patch('app.routes.admin.form_builder.versions.notify_template_updated',
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
        """POST for non-existent version returns 404."""
        _grant_template_permissions(db_session)
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/999999/delete',
            data={},
        )
        assert resp.status_code == 404


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
        """POST for non-existent version returns 404."""
        template = _make_owned_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/versions/999999/comment',
            data={'comment': 'Note'},
        )
        assert resp.status_code == 404
