import io
from unittest.mock import patch

import pytest

from tests.factories import (
    _grant_entity_permission,
    _grant_role_permission,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_user,
)
from tests.helpers import login_session

_AJAX = {"X-Requested-With": "XMLHttpRequest"}


def _excel_aes(db_session, *, status="in_progress", country=None, export=True, import_=True):
    aes = create_test_assignment_entity_status(db_session, status=status, country=country)
    aes.assigned_form.enable_export_excel = export
    aes.assigned_form.enable_import_excel = import_
    db_session.commit()
    return aes


def _focal_for(db_session, aes, *, with_enter=True):
    user = create_test_user(db_session, role="focal_point")
    for code in ("assignment.view", "assignment.edit", "assignment.submit") + (
        ("assignment.enter",) if with_enter else ()
    ):
        _grant_role_permission(db_session, "assignment_editor_submitter", code)
    _grant_entity_permission(db_session, user, aes.entity_type, aes.entity_id)
    db_session.commit()
    return user


def _post_import(client, aes_id, *, filename="ok.xlsx", payload=b"x"):
    return client.post(
        f"/excel/assignment/{aes_id}/import",
        headers=_AJAX,
        data={"excel_file": (io.BytesIO(payload), filename)},
        content_type="multipart/form-data",
    )


@pytest.mark.integration
class TestExcelRoutes:
    @staticmethod
    def _assert_error_json(resp, status_code):
        assert resp.status_code == status_code
        data = resp.get_json()
        assert data is not None
        assert data.get("error") or data.get("success") is False

    def test_export_redirects_when_aes_missing(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/excel/assignment/987654321/export", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)

    @pytest.mark.critical
    def test_export_success_with_real_assignment(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            aes_id = _excel_aes(db_session).id

        fake_output = io.BytesIO(b"excel-bytes")
        with patch(
            "app.routes.excel.ExcelService.build_assignment_workbook",
            return_value=(fake_output, "export.xlsx"),
        ):
            resp = logged_in_sm_client.get(f"/excel/assignment/{aes_id}/export")
            resp.close()
        assert resp.status_code == 200
        assert resp.headers.get("Content-Type", "").startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert resp.headers.get("X-hum-databank-Export-Completed") == "1"
        assert resp.headers.get("X-hum-databank-Export-Filename") == "export.xlsx"

    def test_export_allowed_for_entity_focal_point(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            user = _focal_for(db_session, aes)
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch(
            "app.routes.excel.ExcelService.build_assignment_workbook",
            return_value=(io.BytesIO(b"excel-bytes"), "export.xlsx"),
        ):
            resp = client.get(f"/excel/assignment/{aes_id}/export")
            resp.close()
        assert resp.status_code == 200

    def test_export_denied_for_other_country_focal_point(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            other_country = create_test_country(db_session)
            other_aes = _excel_aes(db_session, country=other_country)
            user = _focal_for(db_session, other_aes)
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch("app.routes.excel.ExcelService.build_assignment_workbook") as build:
            resp = client.get(f"/excel/assignment/{aes_id}/export", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        build.assert_not_called()

    def test_export_denied_for_admin_without_assignment_permission(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            admin = create_test_user(db_session, role="admin")
            aes_id, admin_id = aes.id, admin.id
        login_session(client, admin_id)
        with patch("app.routes.excel.ExcelService.build_assignment_workbook") as build:
            resp = client.get(f"/excel/assignment/{aes_id}/export", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308)
        build.assert_not_called()

    def test_import_ajax_404_when_aes_missing(self, logged_in_sm_client):
        resp = logged_in_sm_client.post(
            "/excel/assignment/987654321/import", headers=_AJAX, data={}
        )
        self._assert_error_json(resp, 404)

    def test_import_ajax_404_for_other_country_focal_point(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            other_aes = _excel_aes(db_session, country=create_test_country(db_session))
            user = _focal_for(db_session, other_aes)
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch("app.routes.excel.ExcelService.import_assignment_data") as importer:
            resp = _post_import(client, aes_id)
        self._assert_error_json(resp, 404)
        importer.assert_not_called()

    def test_import_ajax_400_invalid_extension(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            aes_id = _excel_aes(db_session).id
        resp = _post_import(logged_in_sm_client, aes_id, filename="bad.txt")
        self._assert_error_json(resp, 400)

    def test_import_ajax_400_oversize_file(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            aes_id = _excel_aes(db_session).id
        with patch("app.routes.excel.MAX_EXCEL_FILE_SIZE", 10):
            resp = _post_import(logged_in_sm_client, aes_id, filename="big.xlsx", payload=b"0123456789ABCDEF")
        self._assert_error_json(resp, 400)

    def test_import_ajax_403_when_submitted_and_focal_point(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session, status="submitted")
            user = _focal_for(db_session, aes)
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch("app.routes.excel.ExcelService.import_assignment_data") as importer:
            resp = _post_import(client, aes_id)
        self._assert_error_json(resp, 403)
        importer.assert_not_called()

    def test_import_ajax_403_when_view_only_focal_point(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            user = _focal_for(db_session, aes, with_enter=False)
            _grant_role_permission(db_session, "assignment_editor_submitter", "assignment.view")
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch("app.routes.excel.AuthorizationService.can_edit_assignment", return_value=False), patch(
            "app.routes.excel.ExcelService.import_assignment_data"
        ) as importer:
            resp = _post_import(client, aes_id)
        self._assert_error_json(resp, 403)
        importer.assert_not_called()

    def test_import_ajax_success_contract(self, client, db_session, app):
        with app.app_context():
            aes = _excel_aes(db_session)
            user = _focal_for(db_session, aes)
            aes_id, user_id = aes.id, user.id
        login_session(client, user_id)
        with patch("app.routes.excel.ExcelService.load_workbook", return_value=object()), patch(
            "app.routes.excel.ExcelService.import_assignment_data",
            return_value={"success": True, "updated_count": 1, "errors": []},
        ):
            resp = _post_import(client, aes_id)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["updated_count"] == 1

    def test_import_ajax_failure_contract(self, logged_in_sm_client, db_session, app):
        with app.app_context():
            aes_id = _excel_aes(db_session).id
        with patch("app.routes.excel.ExcelService.load_workbook", return_value=object()), patch(
            "app.routes.excel.ExcelService.import_assignment_data",
            return_value={"success": False, "updated_count": 0, "errors": ["bad"]},
        ):
            resp = _post_import(logged_in_sm_client, aes_id)
        self._assert_error_json(resp, 400)
        assert "errors" in resp.get_json()
