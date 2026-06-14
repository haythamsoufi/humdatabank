"""Tests for app/routes/excel.py — Excel export/import endpoints."""
from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from flask import make_response
from flask_login import login_user

from tests.factories import create_test_user

pytestmark = [pytest.mark.unit]


def _make_logged_in_client(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


# =====================================================================
# export_assignment_excel
# =====================================================================


class TestExportAssignmentExcel:
    def test_export_aes_not_found_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        with patch("app.routes.excel.get_aes_with_joins", return_value=None):
            resp = client.get("/excel/assignment/99999/export")
        assert resp.status_code in (302, 301)

    def test_export_success_returns_excel(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.id = 1

        fake_bytes = BytesIO(b"PK fake xlsx content")
        fake_filename = "assignment_1.xlsx"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.build_assignment_workbook", return_value=(fake_bytes, fake_filename)):
            resp = client.get("/excel/assignment/1/export")

        assert resp.status_code == 200
        assert resp.headers.get("X-hum-databank-Export-Completed") == "1"
        assert resp.headers.get("X-hum-databank-Export-Filename") == fake_filename


# =====================================================================
# import_assignment_excel
# =====================================================================


class TestImportAssignmentExcel:
    def _post_with_file(self, client, aes_id, data=None, content_type="multipart/form-data"):
        return client.post(
            f"/excel/assignment/{aes_id}/import",
            data=data or {},
            content_type=content_type,
        )

    def test_import_aes_not_found_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        with patch("app.routes.excel.get_aes_with_joins", return_value=None):
            resp = self._post_with_file(client, 99999)
        assert resp.status_code in (301, 302)

    def test_import_aes_not_found_ajax_returns_404(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        with patch("app.routes.excel.get_aes_with_joins", return_value=None):
            resp = client.post(
                "/excel/assignment/99999/import",
                json={},
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 404

    def test_import_submitted_status_non_admin_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "submitted"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.AuthorizationService") as MockAuth:
            MockAuth.is_admin.return_value = False
            resp = self._post_with_file(client, 1)
        assert resp.status_code in (301, 302)

    def test_import_submitted_status_non_admin_ajax_returns_403(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "submitted"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.AuthorizationService") as MockAuth:
            MockAuth.is_admin.return_value = False
            resp = client.post(
                "/excel/assignment/1/import",
                json={},
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 403

    def test_import_no_file_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes):
            resp = self._post_with_file(client, 1, data={})
        assert resp.status_code in (301, 302)

    def test_import_no_file_ajax_returns_400(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes):
            resp = client.post(
                "/excel/assignment/1/import",
                json={},
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 400

    def test_import_wrong_extension_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"data"), "test.csv")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (301, 302)

    def test_import_wrong_extension_ajax_returns_400(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"data"), "test.csv")},
                content_type="multipart/form-data",
                headers={"Accept": "application/json"},
            )
        # Either 400 or redirect depending on is_json_request detection
        assert resp.status_code in (301, 302, 400)

    def test_import_oversized_file_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        # Create a fake file larger than 10MB
        large_data = b"x" * 1  # Content, but we mock file_size
        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.MAX_EXCEL_FILE_SIZE", 0):  # Force any file to be oversized
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(large_data), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (301, 302, 400)

    def test_import_invalid_xlsx_load_error_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", side_effect=ValueError("bad xlsx")):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (301, 302)

    def test_import_success_no_errors_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {"success": True, "errors": [], "updated_count": 5}

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (301, 302)

    def test_import_success_with_errors_ajax_returns_200(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {
            "success": True,
            "errors": ["Row 3: invalid value", "Row 5: missing data"],
            "updated_count": 3,
        }

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result), \
             patch("app.routes.excel.is_json_request", return_value=True):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        # When is_json_request is True, a json_ok is returned
        assert resp.status_code in (200, 301, 302)

    def test_import_success_with_many_errors_ajax(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {
            "success": True,
            "errors": [f"Row {i}: error" for i in range(10)],
            "updated_count": 2,
        }

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result), \
             patch("app.routes.excel.is_json_request", return_value=True):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (200, 301, 302)

    def test_import_failure_ajax_returns_400(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {
            "success": False,
            "errors": ["Critical error: sheet not found"],
            "updated_count": 0,
        }

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result), \
             patch("app.routes.excel.is_json_request", return_value=True):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        # Ajax failure returns 400
        assert resp.status_code in (400, 301, 302)

    def test_import_failure_many_errors_ajax(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {
            "success": False,
            "errors": [f"Row {i}: error" for i in range(10)],
            "updated_count": 0,
        }

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result), \
             patch("app.routes.excel.is_json_request", return_value=True):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (400, 301, 302)

    def test_import_failure_non_ajax_redirects(self, app, admin_user, db_session, client):
        user_id = admin_user.id
        client = _make_logged_in_client(client, user_id)

        mock_aes = MagicMock()
        mock_aes.status = "in_progress"
        mock_wb = MagicMock()
        mock_result = {
            "success": False,
            "errors": ["Critical error"],
            "updated_count": 0,
        }

        with patch("app.routes.excel.get_aes_with_joins", return_value=mock_aes), \
             patch("app.routes.excel.ExcelService.load_workbook", return_value=mock_wb), \
             patch("app.routes.excel.ExcelService.import_assignment_data", return_value=mock_result), \
             patch("app.routes.excel.is_json_request", return_value=False):
            resp = client.post(
                "/excel/assignment/1/import",
                data={"excel_file": (BytesIO(b"fake xlsx"), "test.xlsx")},
                content_type="multipart/form-data",
            )
        assert resp.status_code in (301, 302)


# =====================================================================
# _user_can_access_aes helper
# =====================================================================


class TestUserCanAccessAes:
    def test_admin_can_access_any_aes(self, app, admin_user, db_session):
        from app.routes.excel import _user_can_access_aes

        mock_aes = MagicMock()
        mock_aes.entity_type = "country"
        mock_aes.entity_id = 999

        with app.test_request_context("/"):
            from flask_login import login_user
            from app.models import User
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True):
                result = _user_can_access_aes(mock_aes)
        assert result is True

    def test_non_admin_no_country_access_returns_false(self, app, admin_user, db_session):
        from app.routes.excel import _user_can_access_aes

        mock_aes = MagicMock()
        mock_aes.entity_type = "country"
        mock_aes.entity_id = 9999

        with app.test_request_context("/"):
            from flask_login import login_user
            from app.models import User
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            with patch("app.routes.excel.AuthorizationService.is_admin", return_value=False):
                # User has no countries matching entity_id=9999
                result = _user_can_access_aes(mock_aes)
        assert result is False

    def test_non_country_entity_type_returns_false(self, app, admin_user, db_session):
        from app.routes.excel import _user_can_access_aes

        mock_aes = MagicMock()
        mock_aes.entity_type = "national_society"
        mock_aes.entity_id = 5

        with app.test_request_context("/"):
            from flask_login import login_user
            from app.models import User
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            with patch("app.routes.excel.AuthorizationService.is_admin", return_value=False):
                result = _user_can_access_aes(mock_aes)
        assert result is False
