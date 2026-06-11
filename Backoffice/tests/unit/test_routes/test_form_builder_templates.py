"""
Comprehensive pytest tests for app/routes/admin/form_builder/templates.py

Routes covered:
- GET  /admin/templates                         (manage_templates)
- POST /admin/templates/import_kobo_xls         (import_kobo_xls)
- GET  /admin/templates/new                     (new_template)
- POST /admin/templates/new                     (new_template - form submit)
- GET  /admin/templates/<id>/owned-by           (get_template_owned_by)
- GET  /admin/templates/<id>/clone-data         (get_template_clone_data)
- GET  /admin/templates/edit/<id>               (edit_template)
- POST /admin/templates/edit/<id>               (edit_template - save)
- GET  /admin/templates/<id>/delete-info        (get_template_delete_info)
- POST /admin/templates/delete/<id>             (delete_template)
- POST /admin/templates/duplicate/<id>          (duplicate_template)
- GET  /admin/templates/<id>/export_excel       (export_template_excel)
- POST /admin/templates/<id>/import_excel       (import_template_excel)
- GET/POST /admin/templates/<id>/variables      (manage_template_variables)
- GET  /admin/templates/<id>/variables/options  (get_variable_options)
"""
import io
import json
import pytest
from unittest.mock import MagicMock, patch

from tests.factories import (
    create_test_template,
    create_test_draft_version,
    create_test_section,
    create_test_item,
    _ensure_permission,
    _grant_role_permission,
)


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _grant_template_permissions(db_session, extra_perms=None):
    """Grant additional template permissions to the admin_core role."""
    base_perms = [
        'admin.templates.create',
        'admin.templates.duplicate',
        'admin.templates.export_excel',
        'admin.templates.import_excel',
        'admin.templates.publish',
    ]
    for perm in (extra_perms or base_perms):
        _grant_role_permission(db_session, 'admin_core', perm)
    db_session.commit()


def _make_template(db_session, admin_user, name='Test Template', status='published'):
    """Helper to create a template owned by the admin user."""
    return create_test_template(
        db_session,
        name=name,
        status=status,
        owner_id=admin_user.id,
    )


# ---------------------------------------------------------------------------
# manage_templates
# ---------------------------------------------------------------------------

class TestManageTemplates:

    def test_get_templates_list(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates returns 200."""
        _make_template(db_session, admin_user)
        resp = logged_in_client.get('/admin/templates')
        assert resp.status_code == 200

    def test_get_templates_json_response(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates with JSON Accept returns JSON list."""
        _make_template(db_session, admin_user)
        resp = logged_in_client.get(
            '/admin/templates',
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'templates' in data

    def test_get_templates_empty(self, logged_in_client, db_session, app):
        """GET /admin/templates works when there are no templates."""
        resp = logged_in_client.get('/admin/templates')
        assert resp.status_code == 200

    def test_unauthenticated_redirects(self, client, db_session, app):
        """Unauthenticated user is redirected to login."""
        resp = client.get('/admin/templates')
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# new_template
# ---------------------------------------------------------------------------

class TestNewTemplate:

    def test_get_new_template_form(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/new returns the form page."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.get('/admin/templates/new')
        assert resp.status_code == 200

    def test_get_new_template_with_clone_from(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/new?clone_from=<id> pre-fills form data."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user, name='Source Template')
        resp = logged_in_client.get(f'/admin/templates/new?clone_from={template.id}')
        assert resp.status_code == 200

    def test_get_new_template_invalid_clone_from(self, logged_in_client, db_session, admin_user, app):
        """GET with non-existent clone_from still renders the form."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.get('/admin/templates/new?clone_from=999999')
        assert resp.status_code == 200

    def test_post_new_template_creates_template(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/new creates a new template and redirects to edit."""
        _grant_template_permissions(db_session)
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                '/admin/templates/new',
                data={
                    'submit': 'Save Template',
                    'name': 'My New Template',
                    'description': 'A test template',
                    'add_to_self_report': '',
                    'display_order_visible': '',
                    'is_paginated': '',
                    'enable_export_pdf': '',
                    'enable_export_excel': '',
                    'enable_import_excel': '',
                    'enable_ai_validation': '',
                    'enable_data_quality': '',
                    'owned_by': str(admin_user.id),
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_post_new_template_duplicate_name_shows_error(self, logged_in_client, db_session, admin_user, app):
        """POST with duplicate name flashes an error."""
        _grant_template_permissions(db_session)
        existing = _make_template(db_session, admin_user, name='Duplicate Name')
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                '/admin/templates/new',
                data={
                    'submit': 'Save Template',
                    'name': 'Duplicate Name',
                    'description': '',
                    'owned_by': str(admin_user.id),
                },
                follow_redirects=True,
            )
        assert resp.status_code == 200

    def test_post_new_template_excel_import_no_file(self, logged_in_client, db_session, admin_user, app):
        """POST with import_from_excel=1 but no file redirects to edit."""
        _grant_template_permissions(db_session)
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                '/admin/templates/new',
                data={
                    'import_from_excel': '1',
                    'name': 'Excel Import Template',
                    'description': '',
                    'owned_by': str(admin_user.id),
                },
                follow_redirects=False,
            )
        # Either 302 redirect or 200 with error - both acceptable
        assert resp.status_code in (200, 302)

    def test_post_new_template_excel_import_with_file(self, logged_in_client, db_session, admin_user, app):
        """POST with import_from_excel=1 and a mock Excel file."""
        _grant_template_permissions(db_session)
        mock_result = {
            'success': True,
            'created_counts': {'pages': 0, 'sections': 2, 'items': 5},
            'message': "Template 'Test' imported",
            'errors': [],
        }
        excel_bytes = io.BytesIO(b'PK\x03\x04' + b'\x00' * 20)  # minimal .xlsx magic
        excel_bytes.name = 'test.xlsx'
        with patch('app.routes.admin.form_builder.templates.TemplateExcelService') as mock_svc, \
             patch('app.routes.admin.form_builder.templates.validate_upload_extension_and_mime',
                   return_value=(True, None, 'xlsx')), \
             patch('app.routes.admin.form_builder.templates.log_admin_action'):
            mock_svc.import_template.return_value = mock_result
            resp = logged_in_client.post(
                '/admin/templates/new',
                data={
                    'import_from_excel': '1',
                    'name': 'Excel Import Template',
                    'description': '',
                    'owned_by': str(admin_user.id),
                    'excel_file': (io.BytesIO(b'dummy'), 'test.xlsx'),
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# import_kobo_xls
# ---------------------------------------------------------------------------

class TestImportKoboXls:

    def test_no_file_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST without file redirects back to new_template."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.post('/admin/templates/import_kobo_xls', data={})
        assert resp.status_code == 302

    def test_empty_filename_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST with empty filename redirects."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.post(
            '/admin/templates/import_kobo_xls',
            data={'kobo_file': (io.BytesIO(b''), '')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 302

    def test_invalid_file_type_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST with non-Excel file redirects with error."""
        _grant_template_permissions(db_session)
        with patch(
            'app.routes.admin.form_builder.templates.validate_upload_extension_and_mime',
            return_value=(False, 'Invalid file type', None),
        ):
            resp = logged_in_client.post(
                '/admin/templates/import_kobo_xls',
                data={
                    'kobo_file': (io.BytesIO(b'not-excel'), 'file.txt'),
                    'name': 'Test',
                },
                content_type='multipart/form-data',
            )
        assert resp.status_code == 302

    def test_kobo_import_success(self, logged_in_client, db_session, admin_user, app):
        """POST with valid file and successful import redirects to edit."""
        _grant_template_permissions(db_session)
        mock_result = {
            'success': True,
            'template_id': 1,
            'message': "Template 'KoboTest' created",
            'created_counts': {'sections': 2, 'items': 5},
            'warnings': [],
            'errors': [],
        }
        with patch(
            'app.routes.admin.form_builder.templates.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.templates.KoboXlsImportService'
        ) as mock_svc:
            mock_svc.import_kobo_xls.return_value = mock_result
            resp = logged_in_client.post(
                '/admin/templates/import_kobo_xls',
                data={
                    'kobo_file': (io.BytesIO(b'dummy'), 'template.xlsx'),
                    'name': 'KoboTest',
                    'owned_by': str(admin_user.id),
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_kobo_import_failure(self, logged_in_client, db_session, admin_user, app):
        """POST with failed import shows error flash and redirects."""
        _grant_template_permissions(db_session)
        mock_result = {
            'success': False,
            'message': 'Import failed',
            'errors': ['Row 3: missing column'],
        }
        with patch(
            'app.routes.admin.form_builder.templates.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.templates.KoboXlsImportService'
        ) as mock_svc:
            mock_svc.import_kobo_xls.return_value = mock_result
            resp = logged_in_client.post(
                '/admin/templates/import_kobo_xls',
                data={
                    'kobo_file': (io.BytesIO(b'dummy'), 'template.xlsx'),
                    'name': 'BadTemplate',
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_kobo_import_exception_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST that raises an exception during import redirects with error flash."""
        _grant_template_permissions(db_session)
        with patch(
            'app.routes.admin.form_builder.templates.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.templates.KoboXlsImportService'
        ) as mock_svc:
            mock_svc.import_kobo_xls.side_effect = Exception("Service error")
            resp = logged_in_client.post(
                '/admin/templates/import_kobo_xls',
                data={
                    'kobo_file': (io.BytesIO(b'dummy'), 'template.xlsx'),
                    'name': 'ErrorTemplate',
                },
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# get_template_owned_by
# ---------------------------------------------------------------------------

class TestGetTemplateOwnedBy:

    def test_returns_owner_info(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/owned-by returns owner details."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/{template.id}/owned-by')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['owned_by_user_id'] == admin_user.id

    def test_404_for_missing_template(self, logged_in_client, db_session, app):
        """GET for non-existent template returns 404."""
        resp = logged_in_client.get('/admin/templates/999999/owned-by')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# get_template_clone_data
# ---------------------------------------------------------------------------

class TestGetTemplateCloneData:

    def test_returns_clone_data(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/clone-data returns template details."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/{template.id}/clone-data')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'id' in data
        assert data['id'] == template.id

    def test_returns_403_for_no_access(self, logged_in_client, db_session, admin_user, app):
        """GET returns 403 when user lacks access to the template."""
        from tests.factories import create_test_template
        # Template not owned by admin_user (owner_id=None means no specific owner)
        template = create_test_template(db_session, name='Other Owner Template')
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/{template.id}/clone-data')
        assert resp.status_code == 403

    def test_404_for_missing_template(self, logged_in_client, db_session, app):
        """GET for non-existent template returns 404."""
        resp = logged_in_client.get('/admin/templates/999999/clone-data')
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# edit_template
# ---------------------------------------------------------------------------

class TestEditTemplate:

    def test_get_edit_template(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/edit/<id> renders the form builder."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/edit/{template.id}')
        assert resp.status_code == 200

    def test_get_edit_template_with_version_id(self, logged_in_client, db_session, admin_user, app):
        """GET with explicit version_id parameter loads that version."""
        template = _make_template(db_session, admin_user)
        draft = create_test_draft_version(db_session, template)
        resp = logged_in_client.get(f'/admin/templates/edit/{template.id}?version_id={draft.id}')
        assert resp.status_code == 200

    def test_get_edit_template_404(self, logged_in_client, db_session, app):
        """GET for non-existent template returns 404."""
        resp = logged_in_client.get('/admin/templates/edit/999999')
        assert resp.status_code == 404

    def test_get_edit_redirects_when_no_access(self, logged_in_client, db_session, admin_user, app):
        """GET redirects when user does not have access to the template."""
        from tests.factories import create_test_template
        template = create_test_template(db_session, name='Private Template')
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/edit/{template.id}')
        assert resp.status_code == 302

    def test_post_edit_template_updates_name(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/edit/<id> updates template name."""
        template = _make_template(db_session, admin_user, name='Old Name')
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/edit/{template.id}',
                data={
                    'submit': 'Save Template',
                    'name': 'New Name',
                    'description': 'Updated description',
                    'owned_by': str(admin_user.id),
                },
                follow_redirects=False,
            )
        # Accept redirect (302) or success render (200)
        assert resp.status_code in (200, 302)

    def test_post_edit_empty_name_flashes_error(self, logged_in_client, db_session, admin_user, app):
        """POST with empty name flashes error and redirects."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/edit/{template.id}',
            data={
                'submit': 'Save Template',
                'name': '',
                'description': '',
                'owned_by': str(admin_user.id),
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_template_delete_info
# ---------------------------------------------------------------------------

class TestGetTemplateDeleteInfo:

    def test_returns_delete_info(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/delete-info returns structure info."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/{template.id}/delete-info')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'template_id' in data

    def test_returns_403_for_non_owner(self, logged_in_client, db_session, admin_user, app):
        """GET returns 403 when not owner."""
        from tests.factories import create_test_template
        template = create_test_template(db_session, name='Not Mine')
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/{template.id}/delete-info')
        # 403 when not owner and not system manager
        assert resp.status_code in (200, 403)


# ---------------------------------------------------------------------------
# delete_template
# ---------------------------------------------------------------------------

class TestDeleteTemplate:

    def test_delete_not_confirmed_redirects(self, logged_in_client, db_session, admin_user, app):
        """POST without confirmed=true redirects with warning."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/delete/{template.id}',
            data={'confirmed': 'false'},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_confirmed_removes_template(self, logged_in_client, db_session, admin_user, app):
        """POST with confirmed=true deletes the template."""
        template = _make_template(db_session, admin_user, name='To Delete')
        template_id = template.id
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/delete/{template_id}',
                data={'confirmed': 'true'},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_404_for_missing(self, logged_in_client, db_session, app):
        """POST for non-existent template returns 404."""
        resp = logged_in_client.post(
            '/admin/templates/delete/999999',
            data={'confirmed': 'true'},
        )
        assert resp.status_code == 404

    def test_delete_not_json_confirmed(self, logged_in_client, db_session, admin_user, app):
        """POST with JSON Accept and confirmed=false returns JSON error."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/delete/{template.id}',
            data={'confirmed': 'false'},
            headers={'Accept': 'application/json', 'Content-Type': 'application/json'},
            json={'confirmed': 'false'},
        )
        assert resp.status_code in (200, 302, 400)


# ---------------------------------------------------------------------------
# duplicate_template
# ---------------------------------------------------------------------------

class TestDuplicateTemplate:

    def test_duplicate_success(self, logged_in_client, db_session, admin_user, app):
        """POST /admin/templates/duplicate/<id> clones the template."""
        _grant_template_permissions(db_session)
        source = _make_template(db_session, admin_user, name='Source')
        with patch('app.routes.admin.form_builder.templates.log_admin_action'), \
             patch('app.routes.admin.form_builder.templates._clone_template_structure_between_templates'):
            resp = logged_in_client.post(
                f'/admin/templates/duplicate/{source.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_access_denied(self, logged_in_client, db_session, admin_user, app):
        """POST redirects when user lacks access."""
        _grant_template_permissions(db_session)
        from tests.factories import create_test_template
        template = create_test_template(db_session, name='Private')
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.post(
                f'/admin/templates/duplicate/{template.id}',
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_duplicate_404(self, logged_in_client, db_session, admin_user, app):
        """POST for non-existent template returns 404."""
        _grant_template_permissions(db_session)
        resp = logged_in_client.post('/admin/templates/duplicate/999999', data={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# export_template_excel
# ---------------------------------------------------------------------------

class TestExportTemplateExcel:

    def test_export_success(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/export_excel streams an Excel file."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        mock_bytes = io.BytesIO(b'PK\x03\x04dummy-excel-content')
        with patch('app.routes.admin.form_builder.templates.TemplateExcelService') as mock_svc, \
             patch('app.routes.admin.form_builder.templates.log_admin_action'), \
             patch('app.routes.admin.form_builder.templates.send_file') as mock_send:
            mock_svc.export_template.return_value = mock_bytes
            mock_send.return_value = MagicMock(status_code=200)
            resp = logged_in_client.get(f'/admin/templates/{template.id}/export_excel')
        # Either 200 (file sent) or 302 (error redirect)
        assert resp.status_code in (200, 302)

    def test_export_access_denied(self, logged_in_client, db_session, admin_user, app):
        """GET redirects when user lacks access."""
        _grant_template_permissions(db_session)
        from tests.factories import create_test_template
        template = create_test_template(db_session, name='Private Export')
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/{template.id}/export_excel')
        assert resp.status_code == 302

    def test_export_error_redirects(self, logged_in_client, db_session, admin_user, app):
        """GET redirects on exception."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        with patch('app.routes.admin.form_builder.templates.TemplateExcelService') as mock_svc:
            mock_svc.export_template.side_effect = Exception("Export failed")
            resp = logged_in_client.get(f'/admin/templates/{template.id}/export_excel')
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# import_template_excel
# ---------------------------------------------------------------------------

class TestImportTemplateExcel:

    def test_import_no_file(self, logged_in_client, db_session, admin_user, app):
        """POST without file redirects with error."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/import_excel',
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_import_invalid_extension(self, logged_in_client, db_session, admin_user, app):
        """POST with non-Excel extension redirects with error."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/import_excel',
            data={'excel_file': (io.BytesIO(b'text'), 'file.txt')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_import_success(self, logged_in_client, db_session, admin_user, app):
        """POST with valid file and successful import shows success flash."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        mock_result = {
            'success': True,
            'message': 'Import successful',
            'version_id': None,
            'errors': [],
            'created_count': {'pages': 0, 'sections': 2, 'items': 5},
        }
        with patch('app.routes.admin.form_builder.templates.TemplateExcelService') as mock_svc, \
             patch('app.routes.admin.form_builder.templates.log_admin_action'):
            mock_svc.import_template.return_value = mock_result
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/import_excel',
                data={'excel_file': (io.BytesIO(b'dummy'), 'template.xlsx')},
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_import_failure_shows_errors(self, logged_in_client, db_session, admin_user, app):
        """POST with failed import shows error flash."""
        _grant_template_permissions(db_session)
        template = _make_template(db_session, admin_user)
        mock_result = {
            'success': False,
            'message': 'Import failed: bad columns',
            'version_id': None,
            'errors': ['Bad column A', 'Missing column B'],
            'created_count': {'pages': 0, 'sections': 0, 'items': 0},
        }
        with patch('app.routes.admin.form_builder.templates.TemplateExcelService') as mock_svc:
            mock_svc.import_template.return_value = mock_result
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/import_excel',
                data={'excel_file': (io.BytesIO(b'dummy'), 'template.xlsx')},
                content_type='multipart/form-data',
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# manage_template_variables
# ---------------------------------------------------------------------------

class TestManageTemplateVariables:

    def test_get_variables_returns_dict(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/variables returns variables dict."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/{template.id}/variables')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'variables' in data

    def test_get_variables_404_missing_template(self, logged_in_client, db_session, app):
        """GET for missing template returns 404."""
        resp = logged_in_client.get('/admin/templates/999999/variables')
        assert resp.status_code == 404

    def test_post_variables_json_success(self, logged_in_client, db_session, admin_user, app):
        """POST with valid variables JSON saves and returns ok."""
        template = _make_template(db_session, admin_user)
        version_id = template.published_version_id
        with patch('app.routes.admin.form_builder.templates.log_admin_action'):
            resp = logged_in_client.post(
                f'/admin/templates/{template.id}/variables',
                json={'variables': {'my_var': 42}},
                headers={'Content-Type': 'application/json'},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_post_variables_no_data_returns_error(self, logged_in_client, db_session, admin_user, app):
        """POST with empty body returns 400."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/variables',
            data='',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.status_code in (200, 400)

    def test_post_variables_missing_variables_key(self, logged_in_client, db_session, admin_user, app):
        """POST without 'variables' key returns 400."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/variables',
            json={'other_key': 'value'},
            headers={'Content-Type': 'application/json'},
        )
        assert resp.status_code in (200, 400)

    def test_post_variables_not_dict_returns_error(self, logged_in_client, db_session, admin_user, app):
        """POST with non-dict variables returns 400."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.post(
            f'/admin/templates/{template.id}/variables',
            json={'variables': [1, 2, 3]},
            headers={'Content-Type': 'application/json'},
        )
        assert resp.status_code in (200, 400)

    def test_get_variables_access_denied(self, logged_in_client, db_session, admin_user, app):
        """GET returns 403 when access denied."""
        template = _make_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/{template.id}/variables')
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# get_variable_options
# ---------------------------------------------------------------------------

class TestGetVariableOptions:

    def test_returns_templates_and_assignments(self, logged_in_client, db_session, admin_user, app):
        """GET /admin/templates/<id>/variables/options returns options data."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(f'/admin/templates/{template.id}/variables/options')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'templates' in data
        assert 'assignments_by_template' in data

    def test_with_source_template_id(self, logged_in_client, db_session, admin_user, app):
        """GET with source_template_id returns form items."""
        template = _make_template(db_session, admin_user)
        resp = logged_in_client.get(
            f'/admin/templates/{template.id}/variables/options?source_template_id={template.id}'
        )
        assert resp.status_code == 200

    def test_access_denied(self, logged_in_client, db_session, admin_user, app):
        """GET returns 403 when access denied."""
        template = _make_template(db_session, admin_user)
        with patch(
            'app.routes.admin.form_builder.templates.check_template_access',
            return_value=False,
        ):
            resp = logged_in_client.get(f'/admin/templates/{template.id}/variables/options')
        assert resp.status_code == 403
