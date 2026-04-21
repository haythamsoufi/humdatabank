"""Integration tests for /api/mobile/v1/admin/content/* endpoints."""
import pytest
from tests.api.mobile.helpers import assert_mobile_ok, assert_mobile_paginated

PREFIX = '/api/mobile/v1'


@pytest.mark.api
@pytest.mark.integration
class TestTemplateRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/templates', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_templates(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/templates', headers=admin_jwt_headers)
        assert_mobile_paginated(resp)

    def test_delete_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/templates/999999/delete',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestAssignmentRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/assignments', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_assignments(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/assignments', headers=admin_jwt_headers)
        assert_mobile_ok(resp, has_data=True)

    def test_get_assignment_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.get(
            f'{PREFIX}/admin/content/assignments/999999',
            headers=admin_jwt_headers,
        )
        assert resp.status_code == 404

    def test_get_assignment_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(
            f'{PREFIX}/admin/content/assignments/1',
            headers=jwt_headers,
        )
        assert resp.status_code == 403

    def test_delete_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/assignments/999999/delete',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestDocumentRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/documents', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_documents(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/documents', headers=admin_jwt_headers)
        assert_mobile_paginated(resp)

    def test_get_file_unauthenticated(self, client, db_session):
        resp = client.get(f'{PREFIX}/admin/content/documents/1/file')
        assert resp.status_code == 401

    def test_get_file_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.get(
            f'{PREFIX}/admin/content/documents/999999/file',
            headers=admin_jwt_headers,
        )
        assert resp.status_code == 404

    def test_delete_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/documents/999999/delete',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestResourceRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/resources', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_resources(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/resources', headers=admin_jwt_headers)
        assert_mobile_paginated(resp)

    def test_get_file_unauthenticated(self, client, db_session):
        resp = client.get(f'{PREFIX}/admin/content/resources/1/file')
        assert resp.status_code == 401

    def test_get_file_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.get(
            f'{PREFIX}/admin/content/resources/999999/file',
            headers=admin_jwt_headers,
        )
        assert resp.status_code == 404

    def test_delete_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/resources/999999/delete',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestIndicatorBankRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/indicator-bank', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_indicators(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/indicator-bank',
                          headers=admin_jwt_headers)
        assert_mobile_paginated(resp)

    def test_get_indicator_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/indicator-bank/999999',
                          headers=admin_jwt_headers)
        assert resp.status_code == 404

    def test_edit_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/indicator-bank/999999/edit',
                           headers=admin_jwt_headers, json={'name': 'x'})
        assert resp.status_code == 404

    def test_delete_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/indicator-bank/999999/delete',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404

    def test_archive_not_found(self, client, admin_jwt_headers, db_session):
        resp = client.post(f'{PREFIX}/admin/content/indicator-bank/999999/archive',
                           headers=admin_jwt_headers)
        assert resp.status_code == 404


@pytest.mark.api
@pytest.mark.integration
class TestTranslationRoutes:
    def test_list_requires_permission(self, client, jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/translations', headers=jwt_headers)
        assert resp.status_code == 403

    def test_list_translations(self, client, admin_jwt_headers, db_session):
        resp = client.get(f'{PREFIX}/admin/content/translations',
                          headers=admin_jwt_headers)
        # polib may not be installed; either paginated or ok with message
        assert resp.status_code == 200
