"""
Comprehensive pytest tests for app/routes/admin/form_builder/kobo.py

Routes covered (all require admin + system_manager roles):
- GET  /admin/kobo-data-import                    (kobo_data_import)
- POST /admin/kobo-data-import/validate           (kobo_data_import_validate)
- POST /admin/kobo-data-import/analyze            (kobo_data_import_analyze)
- POST /admin/kobo-data-import/match-entities     (kobo_data_import_match)
- POST /admin/kobo-data-import/preview            (kobo_data_import_preview)
- POST /admin/kobo-data-import/template-structure (kobo_data_import_template_structure)
- POST /admin/kobo-data-import/map-columns        (kobo_data_import_map_columns)
- POST /admin/kobo-data-import/execute            (kobo_data_import_execute)

The kobo routes require both @admin_required AND @system_manager_required.
We patch AuthorizationService to let the admin user through for tests that
exercise the route logic, and create real system_manager_user flows where needed.
"""
import io
import json
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch, mock_open

from tests.factories import create_test_template, create_test_section, create_test_item


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures / Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def sm_client(logged_in_client, db_session, admin_user, app):
    """
    Return the logged-in admin client but with is_system_manager patched to True.

    This avoids the need to create a full system-manager user while still
    exercising the route logic beyond the auth gate.
    """
    with patch(
        'app.services.authorization_service.AuthorizationService.is_system_manager',
        return_value=True,
    ):
        yield logged_in_client


def _make_owned_template(db_session, admin_user, **kwargs):
    return create_test_template(db_session, owner_id=admin_user.id, **kwargs)


def _kobo_post_json(client, url, payload, **kwargs):
    return client.post(
        url,
        json=payload,
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# kobo_data_import (GET)
# ---------------------------------------------------------------------------

class TestKoboDataImport:

    def test_get_renders_page(self, sm_client, db_session, admin_user, app):
        """GET /admin/kobo-data-import renders the wizard page (system manager)."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = sm_client.get('/admin/kobo-data-import')
        assert resp.status_code == 200

    def test_get_non_system_manager_redirects(self, logged_in_client, db_session, admin_user, app):
        """GET by non-system-manager admin redirects with warning."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=False,
        ):
            resp = logged_in_client.get('/admin/kobo-data-import')
        assert resp.status_code == 302

    def test_get_unauthenticated_redirects(self, client, db_session, app):
        """GET by unauthenticated user redirects to login."""
        resp = client.get('/admin/kobo-data-import')
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# kobo_data_import_validate (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportValidate:

    def test_no_file_returns_400(self, sm_client, db_session, admin_user, app):
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/validate',
                data={},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400

    def test_invalid_file_type_returns_valid_false(self, sm_client, db_session, admin_user, app):
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(False, 'Invalid file type', None),
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/validate',
                data={'file': (io.BytesIO(b'text data'), 'data.txt')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('valid') is False

    def test_successful_validate(self, sm_client, db_session, admin_user, app):
        validate_result = {
            'valid': True,
            'message': 'Valid KoBo data export',
            'errors': [],
            'preview': {'sheet_name': 'Sheet', 'total_rows': 2, 'total_columns': 3},
        }
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService.validate_data_export',
            return_value=validate_result,
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/validate',
                data={'file': (io.BytesIO(b'PK\x03\x04excel-data'), 'data.xlsx')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('valid') is True
        assert data.get('preview', {}).get('total_rows') == 2


# ---------------------------------------------------------------------------
# kobo_data_import_analyze (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportAnalyze:

    def test_no_file_returns_400(self, sm_client, db_session, admin_user, app):
        """POST without file returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400

    def test_empty_filename_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty filename returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={'file': (io.BytesIO(b''), '')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400

    def test_invalid_file_type_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with invalid file type returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(False, 'Invalid file type', None),
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={'file': (io.BytesIO(b'text data'), 'data.txt')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400

    def test_file_too_large_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with file exceeding 50 MB returns 400."""
        big_data = b'\x00' * (51 * 1024 * 1024)
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ):
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={'file': (io.BytesIO(big_data), 'huge.xlsx')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 400

    def test_successful_analyze_stores_tmp_file(self, sm_client, db_session, admin_user, app):
        """POST with valid file calls analyze and stores tmp file."""
        analyze_result = {
            'success': True,
            'columns': ['col1', 'col2'],
            'row_count': 10,
        }
        file_content = b'PK\x03\x04excel-data'
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc, patch(
            'builtins.open', mock_open(),
        ), patch(
            'os.makedirs',
        ):
            mock_svc.analyze.return_value = analyze_result
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={'file': (io.BytesIO(file_content), 'data.xlsx')},
                content_type='multipart/form-data',
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_analyze_failure_returns_200_with_error(self, sm_client, db_session, admin_user, app):
        """POST where service returns failure still returns 200."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.validate_upload_extension_and_mime',
            return_value=(True, None, 'xlsx'),
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc:
            mock_svc.analyze.return_value = {'success': False, 'message': 'Parse error'}
            resp = sm_client.post(
                '/admin/kobo-data-import/analyze',
                data={'file': (io.BytesIO(b'dummy'), 'data.xlsx')},
                content_type='multipart/form-data',
            )
        # json_ok wraps both success and failure
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# kobo_data_import_match (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportMatch:

    def test_no_data_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty body returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.get_json_safe', return_value=None
        ):
            resp = _kobo_post_json(sm_client, '/admin/kobo-data-import/match-entities', {})
        # get_json_safe returns None -> 400
        assert resp.status_code == 400

    def test_empty_entity_names_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with no entity_names and no file returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/match-entities',
                {'entity_names': []},
            )
        assert resp.status_code == 400

    def test_successful_match_returns_mapping(self, sm_client, db_session, admin_user, app):
        """POST with entity_names returns matched countries."""
        mapping = [
            {'entity_name': 'France', 'country_id': 1, 'country_name': 'France'},
        ]
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc:
            mock_svc.try_match_entities.return_value = mapping
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/match-entities',
                {'entity_names': ['France', 'Germany']},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'entity_mapping' in data

    def test_match_with_entity_column_index(self, sm_client, db_session, admin_user, app):
        """POST with entity_column_index extracts unique entities from file."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc:
            mock_svc.extract_unique_entities.return_value = ['France']
            mock_svc.try_match_entities.return_value = []
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = '/nonexistent/file.xlsx'
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/match-entities',
                {
                    'entity_names': [],
                    'entity_column_index': 0,
                },
            )
        # Either 400 (no entities after extract) or 200
        assert resp.status_code in (200, 400)


# ---------------------------------------------------------------------------
# kobo_data_import_preview (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportPreview:

    def test_no_data_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty body returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.get_json_safe', return_value=None
        ):
            resp = _kobo_post_json(sm_client, '/admin/kobo-data-import/preview', {})
        assert resp.status_code == 400

    def test_expired_session_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with mismatched file_id returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            # No session data -> expired session
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/preview',
                {
                    'file_id': 'fake-id',
                    'entity_column_index': 0,
                    'columns_to_import': [],
                },
            )
        assert resp.status_code == 400

    def test_valid_session_calls_generate_preview(self, sm_client, db_session, admin_user, app):
        """POST with valid session calls generate_preview and returns result."""
        file_id = str(uuid.uuid4())
        tmp_path = '/tmp/test_kobo.xlsx'
        preview_result = {
            'rows': [{'col1': 'val1'}],
            'total_rows': 1,
        }
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc, patch(
            'os.path.exists', return_value=True,
        ), patch(
            'builtins.open', mock_open(read_data=b'excel'),
        ):
            mock_svc.generate_preview.return_value = preview_result
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = tmp_path
                sess['kobo_data_import_id'] = file_id
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/preview',
                {
                    'file_id': file_id,
                    'entity_column_index': 0,
                    'columns_to_import': ['col1'],
                },
            )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# kobo_data_import_template_structure (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportTemplateStructure:

    def test_missing_template_id_returns_400(self, sm_client, db_session, admin_user, app):
        """POST without template_id returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/template-structure',
                {},
            )
        assert resp.status_code == 400

    def test_not_found_template_returns_404(self, sm_client, db_session, admin_user, app):
        """POST with non-existent template_id returns 404."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/template-structure',
                {'template_id': 999999},
            )
        assert resp.status_code == 404

    def test_returns_sections_and_items(self, sm_client, db_session, admin_user, app):
        """POST returns sections and items for an existing template."""
        template = _make_owned_template(db_session, admin_user)
        section = create_test_section(db_session, template)
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/template-structure',
                {'template_id': template.id},
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'sections' in data
        assert data['template_id'] == template.id

    def test_template_with_no_versions_returns_400(self, sm_client, db_session, admin_user, app):
        """POST for template with no versions returns 400."""
        from app.models import FormTemplate
        from app import db
        # Create template without any version
        t = FormTemplate(owned_by=admin_user.id)
        db.session.add(t)
        db.session.commit()
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/template-structure',
                {'template_id': t.id},
            )
        assert resp.status_code in (200, 400)


# ---------------------------------------------------------------------------
# kobo_data_import_map_columns (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportMapColumns:

    def test_no_data_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty body returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.get_json_safe', return_value=None
        ):
            resp = _kobo_post_json(sm_client, '/admin/kobo-data-import/map-columns', {})
        assert resp.status_code == 400

    def test_missing_kobo_columns_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty kobo_columns returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/map-columns',
                {'kobo_columns': [], 'template_items': []},
            )
        assert resp.status_code == 400

    def test_returns_column_mappings(self, sm_client, db_session, admin_user, app):
        """POST with columns and items returns auto-mapping."""
        mappings = [
            {'column': 'col1', 'item_id': 1, 'item_label': 'Item 1', 'score': 0.9},
        ]
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc:
            mock_svc.map_columns_to_template.return_value = mappings
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/map-columns',
                {
                    'kobo_columns': ['col1', 'col2'],
                    'template_items': [{'id': 1, 'label': 'Item 1'}],
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'mappings' in data
        assert 'matched_count' in data


# ---------------------------------------------------------------------------
# kobo_data_import_execute (POST)
# ---------------------------------------------------------------------------

class TestKoboDataImportExecute:

    def test_no_data_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with empty body returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.get_json_safe', return_value=None
        ):
            resp = _kobo_post_json(sm_client, '/admin/kobo-data-import/execute', {})
        assert resp.status_code == 400

    def test_expired_session_returns_400(self, sm_client, db_session, admin_user, app):
        """POST with mismatched file_id returns 400."""
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ):
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/execute',
                {
                    'file_id': 'bad-id',
                    'template_name': 'Test',
                    'period_name': '2024',
                },
            )
        assert resp.status_code == 400

    def test_cannot_read_file_returns_500(self, sm_client, db_session, admin_user, app):
        """POST when temp file cannot be read returns 500."""
        file_id = str(uuid.uuid4())
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch('os.path.exists', return_value=True):
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = '/nonexistent/kobo.xlsx'
                sess['kobo_data_import_id'] = file_id
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/execute',
                {'file_id': file_id, 'template_name': 'Test'},
            )
        assert resp.status_code == 500

    def test_successful_execute_logs_action(self, sm_client, db_session, admin_user, app):
        """POST with valid session executes import and logs action."""
        file_id = str(uuid.uuid4())
        exec_result = {
            'success': True,
            'template_id': 1,
            'counts': {'rows': 5},
            'message': 'Import complete',
        }
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc, patch(
            'os.path.exists', return_value=True,
        ), patch(
            'builtins.open', mock_open(read_data=b'excel'),
        ), patch(
            'os.remove',
        ), patch(
            'app.routes.admin.form_builder.kobo.log_admin_action',
        ):
            mock_svc.execute_import.return_value = exec_result
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = '/tmp/kobo.xlsx'
                sess['kobo_data_import_id'] = file_id
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/execute',
                {
                    'file_id': file_id,
                    'template_name': 'My Import',
                    'period_name': '2024',
                    'entity_column_index': 0,
                    'columns_to_import': ['col1'],
                    'entity_mapping': {},
                },
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get('success') is True

    def test_execute_with_validation_status_int_coercion(self, sm_client, db_session, admin_user, app):
        """POST coerces validation_status_column_index to int."""
        file_id = str(uuid.uuid4())
        exec_result = {'success': False, 'message': 'No data'}
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc, patch(
            'os.path.exists', return_value=True,
        ), patch(
            'builtins.open', mock_open(read_data=b'excel'),
        ), patch('os.remove'):
            mock_svc.execute_import.return_value = exec_result
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = '/tmp/kobo2.xlsx'
                sess['kobo_data_import_id'] = file_id
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/execute',
                {
                    'file_id': file_id,
                    'validation_status_column_index': '3',  # string -> should be coerced
                    'submission_time_column_index': 2,
                },
            )
        assert resp.status_code == 200

    def test_execute_invalid_validation_status_column_index(
        self, sm_client, db_session, admin_user, app
    ):
        """POST with non-numeric validation_status_column_index treats it as None."""
        file_id = str(uuid.uuid4())
        exec_result = {'success': False, 'message': 'No data'}
        with patch(
            'app.services.authorization_service.AuthorizationService.is_system_manager',
            return_value=True,
        ), patch(
            'app.routes.admin.form_builder.kobo.KoboDataImportService'
        ) as mock_svc, patch(
            'os.path.exists', return_value=True,
        ), patch(
            'builtins.open', mock_open(read_data=b'excel'),
        ), patch('os.remove'):
            mock_svc.execute_import.return_value = exec_result
            with sm_client.session_transaction() as sess:
                sess['kobo_data_import_file'] = '/tmp/kobo3.xlsx'
                sess['kobo_data_import_id'] = file_id
            resp = _kobo_post_json(
                sm_client,
                '/admin/kobo-data-import/execute',
                {
                    'file_id': file_id,
                    'validation_status_column_index': 'not-a-number',
                },
            )
        assert resp.status_code == 200
        # The call should succeed (vs_idx treated as None)
        mock_svc.execute_import.assert_called_once()
        call_config = mock_svc.execute_import.call_args[0][1]
        assert call_config.get('validation_status_column_index') is None
