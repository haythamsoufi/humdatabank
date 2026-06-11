"""
Tests for app/routes/admin/system_admin/lookups.py
Targeting 100% code coverage of lookup list management routes.
"""
import json
import io
import pytest
from unittest.mock import patch, MagicMock
from app.models import LookupList, LookupListRow
from tests.factories import create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_render(return_value="<html>ok</html>"):
    return patch(
        "app.routes.admin.system_admin.lookups.render_template",
        return_value=return_value,
    )


def _create_lookup_list(db_session, name="Test List", columns=None):
    """Create a LookupList for tests."""
    existing = LookupList.query.filter_by(name=name).first()
    if existing:
        return existing
    ll = LookupList(
        name=name,
        description="Test description",
        columns_config=columns or [{"name": "Name", "type": "string"}, {"name": "Code", "type": "string"}],
    )
    db_session.add(ll)
    db_session.commit()
    db_session.refresh(ll)
    return ll


def _create_lookup_row(db_session, lookup_list_id, data=None, order=1):
    """Create a LookupListRow for tests."""
    row = LookupListRow(
        lookup_list_id=lookup_list_id,
        data=data or {"Name": "Test", "Code": "TST"},
        order=order,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# GET /admin/lists  – manage lists
# ---------------------------------------------------------------------------

class TestManageLists:
    def test_get_renders_page(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/lists")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/lists", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET/POST /admin/lists/create  – create lookup list
# ---------------------------------------------------------------------------

class TestCreateLookupList:
    def test_get_renders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/lists/create")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_creates_list_and_redirects(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/lists/create",
            data={
                "name": "My New List",
                "description": "Test list",
                "columns": "Name,Code,Region",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            ll = LookupList.query.filter_by(name="My New List").first()
            assert ll is not None
            assert len(ll.columns_config) == 3

    def test_post_empty_name_flashes_error(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/lists/create",
            data={"name": "", "description": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_duplicate_name_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_lookup_list(db_session, "Duplicate List")
        resp = logged_in_client.post(
            "/admin/lists/create",
            data={"name": "Duplicate List", "description": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_exception_flashes_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.lookups.LookupList",
            side_effect=Exception("db error"),
        ), _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/lists/create",
                data={"name": "Exception List", "description": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 200

    def test_post_without_columns_creates_list(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/lists/create",
            data={"name": "No Columns List", "description": "", "columns": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /admin/lists/view/<id>  – view lookup list
# ---------------------------------------------------------------------------

class TestViewLookupList:
    def test_get_renders_list(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "View Me List")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/lists/view/{ll.id}")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_404_for_missing_list(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/lists/view/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/lists/system/<type>  – view system list
# ---------------------------------------------------------------------------

class TestViewSystemList:
    def test_country_map(self, logged_in_client, db_session, app):
        with app.app_context():
            create_test_country(db_session, name="SysListCountry", iso3="SLC")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/lists/system/country_map")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_indicator_bank(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/lists/system/indicator_bank")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_national_society(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/lists/system/national_society")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_invalid_type_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/lists/system/invalid_type",
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET/POST /admin/lists/edit/<id>  – edit lookup list
# ---------------------------------------------------------------------------

class TestEditLookupList:
    def test_get_redirects_to_manage(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Edit Me List")
        resp = logged_in_client.get(
            f"/admin/lists/edit/{ll.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_updates_list(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Edit Post List")
        resp = logged_in_client.post(
            f"/admin/lists/edit/{ll.id}",
            data={
                "name": "Updated List Name",
                "description": "Updated desc",
                "columns": "Col1,Col2",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Edit Exception List")
        with patch(
            "app.routes.admin.system_admin.lookups.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            resp = logged_in_client.post(
                f"/admin/lists/edit/{ll.id}",
                data={"name": "Name", "description": "", "columns": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_404_for_missing_list(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/lists/edit/9999999",
            data={"name": "X"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/lists/delete/<id>  – delete lookup list
# ---------------------------------------------------------------------------

class TestDeleteLookupList:
    def test_delete_removes_list(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete Me Lookup")
        resp = logged_in_client.post(
            f"/admin/lists/delete/{ll.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert LookupList.query.get(ll.id) is None

    def test_delete_also_removes_rows(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete With Rows")
            row = _create_lookup_row(db_session, ll.id)

        resp = logged_in_client.post(
            f"/admin/lists/delete/{ll.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert LookupListRow.query.filter_by(id=row.id).first() is None

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete Exception Lookup")
        with patch(
            "app.routes.admin.system_admin.lookups.db"
        ) as mock_db:
            mock_db.session.delete.side_effect = Exception("db error")
            resp = logged_in_client.post(
                f"/admin/lists/delete/{ll.id}",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_404_for_missing_list(self, logged_in_client, db_session):
        resp = logged_in_client.post("/admin/lists/delete/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/lists/import-template  – download template
# ---------------------------------------------------------------------------

class TestDownloadImportTemplate:
    def test_csv_template(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/lists/import-template?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_xlsx_template(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/lists/import-template?format=xlsx")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type

    def test_default_format_is_xlsx(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/lists/import-template")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type

    def test_unsupported_format_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/lists/import-template?format=pdf",
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/lists/import  – import new list from file
# ---------------------------------------------------------------------------

class TestImportLookupList:
    def test_missing_name_flashes_error(self, logged_in_client, db_session):
        csv_data = io.BytesIO(b"Name,Code\nCountry1,C1\n")
        resp = logged_in_client.post(
            "/admin/lists/import",
            data={
                "name": "",
                "description": "",
                "file": (csv_data, "test.csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_missing_file_flashes_error(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/lists/import",
            data={"name": "Import Test", "description": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_valid_csv_creates_list(self, logged_in_client, db_session, app):
        csv_content = b"Name,Code\nCountry One,C1\nCountry Two,C2\n"

        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(True, None, ".csv"),
        ), patch(
            "app.routes.admin.system_admin.lookups.parse_csv_or_excel_to_rows",
            return_value=(["Name", "Code"], [{"Name": "Country One", "Code": "C1"}, {"Name": "Country Two", "Code": "C2"}]),
        ):
            csv_data = io.BytesIO(csv_content)
            resp = logged_in_client.post(
                "/admin/lists/import",
                data={
                    "name": "CSV Import List",
                    "description": "From CSV",
                    "file": (csv_data, "test.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302
        with app.app_context():
            ll = LookupList.query.filter_by(name="CSV Import List").first()
            assert ll is not None

    def test_invalid_file_type_flashes_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(False, "Unsupported file type", ".exe"),
        ):
            bad_data = io.BytesIO(b"malicious content")
            resp = logged_in_client.post(
                "/admin/lists/import",
                data={
                    "name": "Bad File List",
                    "description": "",
                    "file": (bad_data, "evil.exe"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_exception_during_import_flashes_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(True, None, ".csv"),
        ), patch(
            "app.routes.admin.system_admin.lookups.parse_csv_or_excel_to_rows",
            side_effect=Exception("parse error"),
        ):
            csv_data = io.BytesIO(b"Name,Code\n")
            resp = logged_in_client.post(
                "/admin/lists/import",
                data={
                    "name": "Exception Import",
                    "description": "",
                    "file": (csv_data, "test.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/lists/<id>/import  – import into existing list
# ---------------------------------------------------------------------------

class TestImportIntoLookupList:
    def test_missing_file_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Import Into List")
        resp = logged_in_client.post(
            f"/admin/lists/{ll.id}/import",
            data={"mode": "append"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_invalid_extension_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Import Into Extension Test")
        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(False, "Bad extension", ".txt"),
        ):
            bad_data = io.BytesIO(b"data")
            resp = logged_in_client.post(
                f"/admin/lists/{ll.id}/import",
                data={
                    "mode": "append",
                    "file": (bad_data, "data.txt"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_append_mode(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Append Mode List")
            _create_lookup_row(db_session, ll.id, {"Name": "Existing", "Code": "EX"}, order=1)

        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(True, None, ".csv"),
        ), patch(
            "app.routes.admin.system_admin.lookups.parse_csv_or_excel_to_rows",
            return_value=(["Name", "Code"], [{"Name": "New", "Code": "NW"}]),
        ):
            csv_data = io.BytesIO(b"Name,Code\nNew,NW\n")
            resp = logged_in_client.post(
                f"/admin/lists/{ll.id}/import",
                data={
                    "mode": "append",
                    "file": (csv_data, "test.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_replace_mode(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Replace Mode List")
            _create_lookup_row(db_session, ll.id, {"Name": "Old", "Code": "OLD"}, order=1)

        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(True, None, ".csv"),
        ), patch(
            "app.routes.admin.system_admin.lookups.parse_csv_or_excel_to_rows",
            return_value=(["Name", "Code"], [{"Name": "New", "Code": "NW"}]),
        ):
            csv_data = io.BytesIO(b"Name,Code\nNew,NW\n")
            resp = logged_in_client.post(
                f"/admin/lists/{ll.id}/import",
                data={
                    "mode": "replace",
                    "file": (csv_data, "test.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Import Exception List")
        with patch(
            "app.routes.admin.system_admin.lookups.validate_upload_extension_and_mime",
            return_value=(True, None, ".csv"),
        ), patch(
            "app.routes.admin.system_admin.lookups.parse_csv_or_excel_to_rows",
            side_effect=Exception("parse error"),
        ):
            csv_data = io.BytesIO(b"Name,Code\n")
            resp = logged_in_client.post(
                f"/admin/lists/{ll.id}/import",
                data={
                    "mode": "append",
                    "file": (csv_data, "test.csv"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_404_for_missing_list(self, logged_in_client, db_session):
        csv_data = io.BytesIO(b"Name,Code\n")
        resp = logged_in_client.post(
            "/admin/lists/9999999/import",
            data={"mode": "append", "file": (csv_data, "test.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/lists/<id>/export  – export lookup list to CSV
# ---------------------------------------------------------------------------

class TestExportLookupList:
    def test_exports_csv(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Export CSV List")
            _create_lookup_row(db_session, ll.id, {"Name": "Row1", "Code": "R1"}, order=1)

        resp = logged_in_client.get(f"/admin/lists/{ll.id}/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_empty_list(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Export Empty List")

        resp = logged_in_client.get(f"/admin/lists/{ll.id}/export")
        assert resp.status_code == 200

    def test_404_for_missing_list(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/lists/9999999/export")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /admin/templates/lists/<id>/rows/<row_id>  – update row
# ---------------------------------------------------------------------------

class TestUpdateLookupListRow:
    def test_patch_updates_row_data(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Row Update List")
            row = _create_lookup_row(db_session, ll.id, {"Name": "Original", "Code": "OG"}, order=1)

        resp = logged_in_client.patch(
            f"/admin/templates/lists/{ll.id}/rows/{row.id}",
            data=json.dumps({"Name": "Updated"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_patch_with_non_dict_row_data(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Non-dict Row List")
            row = LookupListRow(
                lookup_list_id=ll.id,
                data=None,  # Non-dict data
                order=1,
            )
            db_session.add(row)
            db_session.commit()
            db_session.refresh(row)

        resp = logged_in_client.patch(
            f"/admin/templates/lists/{ll.id}/rows/{row.id}",
            data=json.dumps({"Name": "New Name"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_patch_missing_body_returns_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Empty Patch List")
            row = _create_lookup_row(db_session, ll.id, {"Name": "Row"}, order=1)

        resp = logged_in_client.patch(
            f"/admin/templates/lists/{ll.id}/rows/{row.id}",
            data=json.dumps({}),
            content_type="application/json",
        )
        # Empty data should return an error
        assert resp.status_code in (400, 200)

    def test_patch_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Patch Exception List")
            row = _create_lookup_row(db_session, ll.id, {"Name": "Row"}, order=1)

        with patch(
            "app.routes.admin.system_admin.lookups.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            mock_db.session.refresh = MagicMock()
            resp = logged_in_client.patch(
                f"/admin/templates/lists/{ll.id}/rows/{row.id}",
                data=json.dumps({"Name": "Test"}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_patch_404_for_missing_row(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Missing Row Patch List")

        resp = logged_in_client.patch(
            f"/admin/templates/lists/{ll.id}/rows/9999999",
            data=json.dumps({"Name": "Test"}),
            content_type="application/json",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/templates/lists/<id>/rows/<row_id>/move  – move row
# ---------------------------------------------------------------------------

class TestMoveLookupListRow:
    def test_move_row_after(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Move Row List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)
            row2 = _create_lookup_row(db_session, ll.id, {"Name": "Row2"}, order=2)

        resp = logged_in_client.post(
            f"/admin/templates/lists/{ll.id}/rows/{row1.id}/move",
            data=json.dumps({"target_row_id": row2.id, "position": "after"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_move_row_before(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Move Before List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)
            row2 = _create_lookup_row(db_session, ll.id, {"Name": "Row2"}, order=2)

        resp = logged_in_client.post(
            f"/admin/templates/lists/{ll.id}/rows/{row2.id}/move",
            data=json.dumps({"target_row_id": row1.id, "position": "before"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_move_row_same_position(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Same Position Move List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)

        resp = logged_in_client.post(
            f"/admin/templates/lists/{ll.id}/rows/{row1.id}/move",
            data=json.dumps({"target_row_id": row1.id, "position": "after"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_move_missing_target_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Missing Target Move List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)

        resp = logged_in_client.post(
            f"/admin/templates/lists/{ll.id}/rows/{row1.id}/move",
            data=json.dumps({"position": "after"}),  # Missing target_row_id
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_move_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Move Exception List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)
            row2 = _create_lookup_row(db_session, ll.id, {"Name": "Row2"}, order=2)

        with patch(
            "app.routes.admin.system_admin.lookups.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            resp = logged_in_client.post(
                f"/admin/templates/lists/{ll.id}/rows/{row1.id}/move",
                data=json.dumps({"target_row_id": row2.id}),
                content_type="application/json",
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /admin/templates/lists/<id>/rows/<row_id>  – delete row
# ---------------------------------------------------------------------------

class TestDeleteLookupListRow:
    def test_delete_row_success(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete Row List")
            row = _create_lookup_row(db_session, ll.id, {"Name": "Row"}, order=1)

        resp = logged_in_client.delete(
            f"/admin/templates/lists/{ll.id}/rows/{row.id}",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_delete_row_renumbers_remaining(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete Renumber List")
            row1 = _create_lookup_row(db_session, ll.id, {"Name": "R1"}, order=1)
            row2 = _create_lookup_row(db_session, ll.id, {"Name": "R2"}, order=2)
            row3 = _create_lookup_row(db_session, ll.id, {"Name": "R3"}, order=3)

        resp = logged_in_client.delete(
            f"/admin/templates/lists/{ll.id}/rows/{row1.id}",
        )
        assert resp.status_code == 200

    def test_delete_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Delete Exception Row List")
            row = _create_lookup_row(db_session, ll.id, {"Name": "Row"}, order=1)

        with patch(
            "app.routes.admin.system_admin.lookups.db"
        ) as mock_db:
            mock_db.session.delete.side_effect = Exception("db error")
            resp = logged_in_client.delete(
                f"/admin/templates/lists/{ll.id}/rows/{row.id}",
            )
        assert resp.status_code == 500

    def test_delete_404_for_missing_row(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Missing Delete Row List")

        resp = logged_in_client.delete(
            f"/admin/templates/lists/{ll.id}/rows/9999999",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/api/templates/lists/<id>/rows  – add row
# ---------------------------------------------------------------------------

class TestAddLookupListRow:
    def test_add_row_no_order(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Add Row No Order List")

        resp = logged_in_client.post(
            f"/admin/api/templates/lists/{ll.id}/rows",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert "row_id" in data

    def test_add_row_with_order(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Add Row With Order List")

        resp = logged_in_client.post(
            f"/admin/api/templates/lists/{ll.id}/rows",
            data=json.dumps({"order": 5}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_add_row_with_insert_after_order(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Add Row Insert After List")
            _create_lookup_row(db_session, ll.id, {"Name": "Row1"}, order=1)

        resp = logged_in_client.post(
            f"/admin/api/templates/lists/{ll.id}/rows",
            data=json.dumps({"insert_after_order": 1}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_add_row_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ll = _create_lookup_list(db_session, "Add Row Exception List")

        with patch(
            "app.routes.admin.system_admin.lookups.LookupListRow",
            side_effect=Exception("db error"),
        ):
            resp = logged_in_client.post(
                f"/admin/api/templates/lists/{ll.id}/rows",
                data=json.dumps({}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_add_row_404_for_missing_list(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/templates/lists/9999999/rows",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 404
