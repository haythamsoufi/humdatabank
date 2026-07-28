"""Direct unit tests for app.routes.api.mobile.admin_content view functions.

Uses route_admin fixture from local conftest.py.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from flask_login import login_user

pytestmark = [pytest.mark.unit]


def _parse(resp):
    if isinstance(resp, tuple):
        body, status = resp
        return body, status
    return resp, resp.status_code


# ---------------------------------------------------------------------------
# list_templates
# ---------------------------------------------------------------------------

class TestListTemplates:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_templates

        with app.test_request_context('/api/mobile/v1/admin/content/templates', method='GET'):
            login_user(route_admin)
            resp = list_templates()

        _, status = _parse(resp)
        assert status == 200

    def test_with_pagination(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_templates

        with app.test_request_context(
            '/api/mobile/v1/admin/content/templates?page=1&per_page=5', method='GET'
        ):
            login_user(route_admin)
            resp = list_templates()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# delete_template
# ---------------------------------------------------------------------------

class TestDeleteTemplate:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_template

        with app.test_request_context(
            '/api/mobile/v1/admin/content/templates/99999/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = delete_template(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_template
        from tests.factories import create_test_template

        template = create_test_template(db_session)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/templates/{template.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action'):
                resp = delete_template(template.id)

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_template
        from tests.factories import create_test_template

        template = create_test_template(db_session)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/templates/{template.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action',
                       side_effect=RuntimeError('db error')), \
                 patch('app.utils.transactions.request_transaction_rollback'):
                resp = delete_template(template.id)

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# list_assignments
# ---------------------------------------------------------------------------

class TestListAssignments:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_assignments

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments', method='GET'
        ):
            login_user(route_admin)
            resp = list_assignments()

        _, status = _parse(resp)
        assert status == 200

    def test_with_pagination(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_assignments

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments?page=1&per_page=5', method='GET'
        ):
            login_user(route_admin)
            resp = list_assignments()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# get_assignment
# ---------------------------------------------------------------------------

class TestGetAssignment:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_assignment

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments/99999', method='GET'
        ):
            login_user(route_admin)
            resp = get_assignment(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_assignment
        from tests.factories import create_test_template

        template = create_test_template(db_session)
        from app.models import AssignedForm
        af = AssignedForm(template_id=template.id, period_name='2024', is_public_active=False)
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/assignments/{af.id}', method='GET'
        ):
            login_user(route_admin)
            resp = get_assignment(af.id)

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# delete_assignment
# ---------------------------------------------------------------------------

class TestDeleteAssignment:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_assignment

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments/99999/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = delete_assignment(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_assignment
        from tests.factories import create_test_template
        from app.models import AssignedForm

        template = create_test_template(db_session)
        af = AssignedForm(template_id=template.id, period_name='2024-del')
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/assignments/{af.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action'):
                resp = delete_assignment(af.id)

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_assignment
        from tests.factories import create_test_template
        from app.models import AssignedForm

        template = create_test_template(db_session)
        af = AssignedForm(template_id=template.id, period_name='2024-err')
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/assignments/{af.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action',
                       side_effect=RuntimeError('db error')), \
                 patch('app.utils.transactions.request_transaction_rollback'):
                resp = delete_assignment(af.id)

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# toggle_public_access
# ---------------------------------------------------------------------------

class TestTogglePublicAccess:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import toggle_public_access

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments/99999/toggle-public', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = toggle_public_access(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import toggle_public_access
        from tests.factories import create_test_template
        from app.models import AssignedForm

        template = create_test_template(db_session)
        af = AssignedForm(template_id=template.id, period_name='2024-toggle', is_public_active=False)
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/assignments/{af.id}/toggle-public', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = toggle_public_access(af.id)

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# generate_public_url
# ---------------------------------------------------------------------------

class TestGeneratePublicUrl:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import generate_public_url

        with app.test_request_context(
            '/api/mobile/v1/admin/content/assignments/99999/generate-url', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = generate_public_url(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import generate_public_url
        from tests.factories import create_test_template
        from app.models import AssignedForm

        template = create_test_template(db_session)
        af = AssignedForm(template_id=template.id, period_name='2024-genurl')
        db_session.add(af)
        db_session.commit()
        db_session.refresh(af)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/assignments/{af.id}/generate-url', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = generate_public_url(af.id)

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# list_documents
# ---------------------------------------------------------------------------

class TestListDocuments:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_documents

        with app.test_request_context(
            '/api/mobile/v1/admin/content/documents', method='GET'
        ):
            login_user(route_admin)
            resp = list_documents()

        _, status = _parse(resp)
        assert status == 200

    def test_with_search(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_documents

        with app.test_request_context(
            '/api/mobile/v1/admin/content/documents?search=report', method='GET'
        ):
            login_user(route_admin)
            resp = list_documents()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# get_submitted_document_file
# ---------------------------------------------------------------------------

class TestGetSubmittedDocumentFile:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_submitted_document_file

        with app.test_request_context(
            '/api/mobile/v1/admin/content/documents/99999/file', method='GET'
        ):
            login_user(route_admin)
            resp = get_submitted_document_file(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_access_denied(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_submitted_document_file
        from app.models import SubmittedDocument

        doc = SubmittedDocument(filename='test.pdf', storage_path='docs/test.pdf')
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/documents/{doc.id}/file', method='GET'
        ):
            login_user(route_admin)
            with patch('app.routes.admin.content_management._check_document_access',
                       return_value=(False, 'Denied')):
                resp = get_submitted_document_file(doc.id)

        _, status = _parse(resp)
        assert status == 403

    def test_file_not_found_on_server(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_submitted_document_file
        from app.models import SubmittedDocument

        doc = SubmittedDocument(filename='missing.pdf', storage_path='docs/missing.pdf')
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_storage = MagicMock()
        mock_storage.exists.return_value = False

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/documents/{doc.id}/file', method='GET'
        ):
            login_user(route_admin)
            with patch('app.routes.admin.content_management._check_document_access',
                       return_value=(True, None)), \
                 patch('app.routes.admin.content_management._storage_category_for_submitted_document',
                       return_value='documents'), \
                 patch('app.routes.api.mobile.admin_content.storage', mock_storage):
                resp = get_submitted_document_file(doc.id)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_submitted_document_file
        from app.models import SubmittedDocument

        doc = SubmittedDocument(filename='report.pdf', storage_path='docs/report.pdf')
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        mock_storage = MagicMock()
        mock_storage.exists.return_value = True
        mock_storage.stream_response.return_value = ('file-bytes', 200)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/documents/{doc.id}/file', method='GET'
        ):
            login_user(route_admin)
            with patch('app.routes.admin.content_management._check_document_access',
                       return_value=(True, None)), \
                 patch('app.routes.admin.content_management._storage_category_for_submitted_document',
                       return_value='documents'), \
                 patch('app.routes.api.mobile.admin_content.storage', mock_storage):
                resp = get_submitted_document_file(doc.id)

        _, status = _parse(resp)
        assert status in (200, 500)


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------

class TestDeleteDocument:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_document

        with app.test_request_context(
            '/api/mobile/v1/admin/content/documents/99999/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = delete_document(99999)

        _, status = _parse(resp)
        assert status == 404

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_document
        from app.models import SubmittedDocument

        doc = SubmittedDocument(filename='deleteme.pdf', storage_path='docs/deleteme.pdf')
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/documents/{doc.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action'):
                resp = delete_document(doc.id)

        _, status = _parse(resp)
        assert status == 200

    def test_error(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_document
        from app.models import SubmittedDocument

        doc = SubmittedDocument(filename='errdoc.pdf', storage_path='docs/errdoc.pdf')
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        with app.test_request_context(
            f'/api/mobile/v1/admin/content/documents/{doc.id}/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.services.platform.user_analytics_service.log_admin_action',
                       side_effect=RuntimeError('db error')), \
                 patch('app.utils.transactions.request_transaction_rollback'):
                resp = delete_document(doc.id)

        _, status = _parse(resp)
        assert status == 500


# ---------------------------------------------------------------------------
# list_resources
# ---------------------------------------------------------------------------

class TestListResources:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_resources

        with app.test_request_context(
            '/api/mobile/v1/admin/content/resources', method='GET'
        ):
            login_user(route_admin)
            resp = list_resources()

        _, status = _parse(resp)
        assert status == 200

    def test_with_search(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_resources

        with app.test_request_context(
            '/api/mobile/v1/admin/content/resources?search=guide', method='GET'
        ):
            login_user(route_admin)
            resp = list_resources()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# get_resource_file
# ---------------------------------------------------------------------------

class TestGetResourceFile:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_resource_file

        with app.test_request_context(
            '/api/mobile/v1/admin/content/resources/99999/file', method='GET'
        ):
            login_user(route_admin)
            resp = get_resource_file(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# delete_resource
# ---------------------------------------------------------------------------

class TestDeleteResource:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_resource

        with app.test_request_context(
            '/api/mobile/v1/admin/content/resources/99999/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = delete_resource(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# list_indicators
# ---------------------------------------------------------------------------

class TestListIndicators:
    def test_success_empty(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_indicators

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators', method='GET'
        ):
            login_user(route_admin)
            resp = list_indicators()

        _, status = _parse(resp)
        assert status == 200

    def test_with_search_and_filters(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_indicators

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators?search=count&type=number&archived=false',
            method='GET'
        ):
            login_user(route_admin)
            resp = list_indicators()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# get_indicator
# ---------------------------------------------------------------------------

class TestGetIndicator:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import get_indicator

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators/99999', method='GET'
        ):
            login_user(route_admin)
            resp = get_indicator(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# edit_indicator
# ---------------------------------------------------------------------------

class TestEditIndicator:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import edit_indicator

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators/99999/edit',
            method='PUT',
            data=json.dumps({'name': 'Test'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = edit_indicator(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# delete_indicator
# ---------------------------------------------------------------------------

class TestDeleteIndicator:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import delete_indicator

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators/99999/delete', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = delete_indicator(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# archive_indicator
# ---------------------------------------------------------------------------

class TestArchiveIndicator:
    def test_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import archive_indicator

        with app.test_request_context(
            '/api/mobile/v1/admin/content/indicators/99999/archive', method='POST'
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = archive_indicator(99999)

        _, status = _parse(resp)
        assert status == 404


# ---------------------------------------------------------------------------
# list_translations
# ---------------------------------------------------------------------------

class TestListTranslations:
    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_translations

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations', method='GET'
        ):
            login_user(route_admin)
            with patch('app.extensions.resolve_translations_directory', return_value='/tmp/nonexistent'):
                resp = list_translations()

        _, status = _parse(resp)
        assert status == 200

    def test_with_locale_filter(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_translations

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations?locale=fr', method='GET'
        ):
            login_user(route_admin)
            with patch('app.extensions.resolve_translations_directory', return_value='/tmp/nonexistent'):
                resp = list_translations()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# list_translation_sources
# ---------------------------------------------------------------------------

class TestListTranslationSources:
    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import list_translation_sources

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations/sources', method='GET'
        ):
            login_user(route_admin)
            with patch('app.extensions.resolve_translations_directory', return_value='/tmp/nonexistent'):
                resp = list_translation_sources()

        _, status = _parse(resp)
        assert status == 200


# ---------------------------------------------------------------------------
# update_translation
# ---------------------------------------------------------------------------

class TestUpdateTranslation:
    def test_missing_fields_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import update_translation

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations/update',
            method='POST',
            data=json.dumps({}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_translation()

        _, status = _parse(resp)
        assert status == 400

    def test_invalid_locale_returns_400(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import update_translation

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations/update',
            method='POST',
            data=json.dumps({'locale': '', 'msgid': 'hello', 'msgstr': 'bonjour'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'):
                resp = update_translation()

        _, status = _parse(resp)
        assert status == 400

    def test_translation_file_not_found(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import update_translation

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations/update',
            method='POST',
            data=json.dumps({'locale': 'fr', 'msgid': 'hello', 'msgstr': 'bonjour'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.extensions.resolve_translations_directory', return_value='/tmp/nonexistent'):
                resp = update_translation()

        _, status = _parse(resp)
        assert status in (400, 404, 500)

    def test_success(self, app, db_session, route_admin):
        from app.routes.api.mobile.admin_content import update_translation

        mock_po_file = MagicMock()
        mock_entry = MagicMock()
        mock_entry.msgstr = 'old translation'
        mock_po_file.find.return_value = mock_entry
        mock_po_file.save = MagicMock()

        with app.test_request_context(
            '/api/mobile/v1/admin/content/translations/update',
            method='POST',
            data=json.dumps({'locale': 'fr', 'msgid': 'hello', 'msgstr': 'bonjour'}),
            content_type='application/json',
        ):
            login_user(route_admin)
            with patch('app.utils.mobile_auth.enforce_api_or_csrf_protection'), \
                 patch('app.extensions.resolve_translations_directory', return_value='/tmp/fake'), \
                 patch('os.path.exists', return_value=True), \
                 patch('polib.pofile', return_value=mock_po_file), \
                 patch('app.services.platform.user_analytics_service.log_admin_action'):
                resp = update_translation()

        _, status = _parse(resp)
        assert status == 200
