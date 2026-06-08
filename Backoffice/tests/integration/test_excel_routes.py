import io
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from tests.factories import create_test_assignment_entity_status

@dataclass
class _AES:
    id: int
    status: str = "pending"


@pytest.mark.integration
class TestExcelRoutes:
    @staticmethod
    def _assert_error_json(resp, status_code):
        assert resp.status_code == status_code
        data = resp.get_json()
        assert data is not None
        assert data.get("error") or data.get("success") is False

    def test_export_redirects_when_aes_missing(self, logged_in_client):
        with patch("app.routes.excel.get_aes_with_joins", return_value=None):
            resp = logged_in_client.get("/excel/assignment/123/export", follow_redirects=False)
            assert resp.status_code in (301, 302, 303, 307, 308)

    def test_export_success_sets_headers_and_content_type(self, logged_in_client):
        aes = _AES(id=123, status="pending")

        fake_output = io.BytesIO(b"excel-bytes")
        with patch("app.routes.excel.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel.ExcelService.build_assignment_workbook",
            return_value=(fake_output, "export.xlsx"),
        ):
            resp = logged_in_client.get(f"/excel/assignment/{aes.id}/export")
            resp.close()
            assert resp.status_code == 200
            assert resp.headers.get("Content-Type", "").startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert resp.headers.get("X-hum-databank-Export-Completed") == "1"
            assert resp.headers.get("X-hum-databank-Export-Filename") == "export.xlsx"

    @pytest.mark.critical
    def test_export_success_with_real_assignment(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status="in_progress")
            aes_id = aes.id

        fake_output = io.BytesIO(b"excel-bytes")
        with patch(
            "app.routes.excel.ExcelService.build_assignment_workbook",
            return_value=(fake_output, "export.xlsx"),
        ):
            resp = logged_in_client.get(f"/excel/assignment/{aes_id}/export")
            resp.close()
            assert resp.status_code == 200
            assert resp.headers.get("Content-Type", "").startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    def test_import_ajax_404_when_aes_missing(self, logged_in_client):
        with patch("app.routes.excel.get_aes_with_joins", return_value=None):
            resp = logged_in_client.post(
                "/excel/assignment/123/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={},
            )
            assert resp.status_code == 404
            self._assert_error_json(resp, 404)

    def test_import_ajax_400_invalid_extension(self, logged_in_client):
        aes = _AES(id=123, status="pending")

        with patch("app.routes.excel.get_aes_with_joins", return_value=aes):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "bad.txt")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 400
            self._assert_error_json(resp, 400)

    def test_import_ajax_400_oversize_file(self, logged_in_client):
        aes = _AES(id=123, status="pending")

        with patch("app.routes.excel.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel.MAX_EXCEL_FILE_SIZE", 10
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"0123456789ABCDEF"), "big.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 400
            self._assert_error_json(resp, 400)

    def test_import_ajax_403_when_not_editable_and_not_admin(self, logged_in_client):
        aes = _AES(id=123, status="submitted")

        with patch("app.routes.excel.get_aes_with_joins", return_value=aes), patch(
            "app.services.authorization_service.AuthorizationService.is_admin", return_value=False
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "ok.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 403
            self._assert_error_json(resp, 403)

    def test_import_ajax_success_contract(self, logged_in_client):
        aes = _AES(id=123, status="pending")

        with patch("app.routes.excel.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel.ExcelService.load_workbook", return_value=object()
        ), patch(
            "app.routes.excel.ExcelService.import_assignment_data",
            return_value={"success": True, "updated_count": 1, "errors": []},
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "ok.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["updated_count"] == 1

    def test_import_ajax_failure_contract(self, logged_in_client):
        aes = _AES(id=123, status="pending")

        with patch("app.routes.excel.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel.ExcelService.load_workbook", return_value=object()
        ), patch(
            "app.routes.excel.ExcelService.import_assignment_data",
            return_value={"success": False, "updated_count": 0, "errors": ["bad"]},
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "ok.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 400
            data = resp.get_json()
            self._assert_error_json(resp, 400)
            assert "errors" in data

