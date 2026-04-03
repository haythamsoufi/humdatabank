import io
from dataclasses import dataclass
from unittest.mock import patch

import pytest

@dataclass
class _AES:
    id: int
    status: str = "Pending"


@pytest.mark.integration
class TestExcelRoutes:
    def test_export_redirects_when_aes_missing(self, logged_in_client):
        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=None):
            resp = logged_in_client.get("/excel/assignment/123/export", follow_redirects=False)
            assert resp.status_code in (301, 302, 303, 307, 308)

    def test_export_success_sets_headers_and_content_type(self, logged_in_client):
        aes = _AES(id=123, status="Pending")

        fake_output = io.BytesIO(b"excel-bytes")
        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel_routes.ExcelService.build_assignment_workbook",
            return_value=(fake_output, "export.xlsx"),
        ):
            resp = logged_in_client.get(f"/excel/assignment/{aes.id}/export")
            resp.close()
            assert resp.status_code == 200
            assert resp.headers.get("Content-Type", "").startswith(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            assert resp.headers.get("X-NGO-Databank-Export-Completed") == "1"
            assert resp.headers.get("X-NGO-Databank-Export-Filename") == "export.xlsx"

    def test_import_ajax_404_when_aes_missing(self, logged_in_client):
        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=None):
            resp = logged_in_client.post(
                "/excel/assignment/123/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={},
            )
            assert resp.status_code == 404
            data = resp.get_json()
            assert data["success"] is False

    def test_import_ajax_400_invalid_extension(self, logged_in_client):
        aes = _AES(id=123, status="Pending")

        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "bad.txt")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 400
            data = resp.get_json()
            assert data["success"] is False

    def test_import_ajax_400_oversize_file(self, logged_in_client):
        aes = _AES(id=123, status="Pending")

        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel_routes.MAX_EXCEL_FILE_SIZE", 10
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"0123456789ABCDEF"), "big.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 400
            assert resp.get_json()["success"] is False

    def test_import_ajax_403_when_not_editable_and_not_admin(self, logged_in_client):
        aes = _AES(id=123, status="Submitted")

        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes), patch(
            "app.services.authorization_service.AuthorizationService.is_admin", return_value=False
        ):
            resp = logged_in_client.post(
                f"/excel/assignment/{aes.id}/import",
                headers={"X-Requested-With": "XMLHttpRequest"},
                data={"excel_file": (io.BytesIO(b"x"), "ok.xlsx")},
                content_type="multipart/form-data",
            )
            assert resp.status_code == 403
            assert resp.get_json()["success"] is False

    def test_import_ajax_success_contract(self, logged_in_client):
        aes = _AES(id=123, status="Pending")

        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel_routes.ExcelService.load_workbook", return_value=object()
        ), patch(
            "app.routes.excel_routes.ExcelService.import_assignment_data",
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
        aes = _AES(id=123, status="Pending")

        with patch("app.routes.excel_routes.get_aes_with_joins", return_value=aes), patch(
            "app.routes.excel_routes.ExcelService.load_workbook", return_value=object()
        ), patch(
            "app.routes.excel_routes.ExcelService.import_assignment_data",
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
            assert data["success"] is False
            assert "errors" in data

