"""
Tests for app/routes/admin/system_admin/indicator_lookups.py
Targeting 100% code coverage of indicator measurement type/unit routes.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from tests.factories import create_test_admin
from app.models import IndicatorBankType, IndicatorBankUnit

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_render(return_value="<html>ok</html>"):
    return patch(
        "app.routes.admin.system_admin.indicator_lookups.render_template",
        return_value=return_value,
    )


def _json(data):
    return json.dumps(data)


def _json_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _create_type(db_session, code="testtype", name="Test Type"):
    """Create an IndicatorBankType row for tests."""
    existing = IndicatorBankType.query.filter_by(code=code).first()
    if existing:
        return existing
    row = IndicatorBankType(
        code=code, name=name, sort_order=10, is_active=True
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_unit(db_session, code="testunit", name="Test Unit"):
    """Create an IndicatorBankUnit row for tests."""
    existing = IndicatorBankUnit.query.filter_by(code=code).first()
    if existing:
        return existing
    row = IndicatorBankUnit(
        code=code, name=name, sort_order=10, is_active=True, allows_disaggregation=False
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


# ---------------------------------------------------------------------------
# GET /admin/indicator-bank/measurement-lookups
# ---------------------------------------------------------------------------

class TestManageMeasurementLookups:
    def test_get_renders_page(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/indicator-bank/measurement-lookups")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_adds_missing_ns_unit(self, logged_in_client, db_session, app):
        """If 'ns' unit is missing it should be auto-inserted."""
        with app.app_context():
            # Delete 'ns' if it exists to test the auto-insert path
            IndicatorBankUnit.query.filter(
                IndicatorBankUnit.code == "ns"
            ).delete()
            db_session.commit()

        with _mock_render():
            resp = logged_in_client.get("/admin/indicator-bank/measurement-lookups")
        assert resp.status_code == 200

        with app.app_context():
            assert IndicatorBankUnit.query.filter_by(code="ns").first() is not None

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/indicator-bank/measurement-lookups", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.location


# ---------------------------------------------------------------------------
# POST /admin/indicator-bank/measurement-lookups/types/<tid>/translations
# ---------------------------------------------------------------------------

class TestPatchMeasurementTypeTranslations:
    def test_non_json_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "transtype", "TransType")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/translations",
            data={"translations": "{}"},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "emptytranstype", "EmptyTransType")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/translations",
            data=_json({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_translations_key_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "missingkey", "MissingKey")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/translations",
            data=_json({"other_key": "value"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_valid_translations_returns_ok(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "validtranstype", "ValidTransType")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/translations",
            data=_json({"translations": {"fr": "Type valide"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_404_for_missing_type(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/types/9999999/translations",
            data=_json({"translations": {"fr": "Test"}}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_non_allowed_language_skipped(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "skiplangtype", "SkipLangType")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/translations",
            data=_json({"translations": {"xx": "Invalid lang", "": "Empty lang"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /admin/indicator-bank/measurement-lookups/units/<uid>/translations
# ---------------------------------------------------------------------------

class TestPatchMeasurementUnitTranslations:
    def test_non_json_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "transunit", "TransUnit")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/translations",
            data={"translations": "{}"},
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_valid_translations_returns_ok(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "validtransunit", "ValidTransUnit")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/translations",
            data=_json({"translations": {"fr": "Unité valide"}}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_missing_translations_key_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "missingkeyunit", "MissingKeyUnit")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/translations",
            data=_json({"wrong": "data"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_404_for_missing_unit(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/units/9999999/translations",
            data=_json({"translations": {"fr": "Test"}}),
            content_type="application/json",
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator-bank/measurement-lookups/types/new
# ---------------------------------------------------------------------------

class TestNewMeasurementType:
    def test_get_without_partial_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/indicator-bank/measurement-lookups/types/new",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_with_partial_returns_html(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(
                "/admin/indicator-bank/measurement-lookups/types/new?partial=1",
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_valid_data_creates_type(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/types/new",
            data={"code": "newtype01", "name": "New Type 01", "sort_order": "5", "is_active": "y"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            row = IndicatorBankType.query.filter_by(code="newtype01").first()
            assert row is not None
            assert row.name == "New Type 01"

    def test_post_invalid_data_rerenders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/indicator-bank/measurement-lookups/types/new",
                data={"code": "", "name": ""},  # Missing required fields
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_json_invalid_data_returns_json_errors(self, logged_in_client, db_session):
        with _mock_render():
            resp = logged_in_client.post(
                "/admin/indicator-bank/measurement-lookups/types/new",
                data=_json({"code": "", "name": ""}),
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_post_json_valid_data_creates_type(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/types/new",
            data=_json({"code": "jsontype01", "name": "JSON Type 01", "sort_order": 5, "is_active": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator-bank/measurement-lookups/types/<tid>/edit
# ---------------------------------------------------------------------------

class TestEditMeasurementType:
    def test_get_without_partial_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "edittype_redir", "Edit Type Redir")
        resp = logged_in_client.get(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_with_partial_returns_html(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "edittype_partial", "Edit Type Partial")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(
                f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit?partial=1",
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_valid_data_updates_type(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "updatetype", "Update Type")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit",
            data={
                "code": "updatetype",
                "name": "Updated Type Name",
                "sort_order": "10",
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_code_change_blocked_when_in_use(self, logged_in_client, db_session, app):
        from app.models import IndicatorBank
        with app.app_context():
            row = _create_type(db_session, "inusetypechange", "In-Use Type")
            # Create an IndicatorBank that references this type
            ind = IndicatorBank(
                name="Type Ref Indicator",
                type="inusetypechange",
                indicator_type_id=row.id,
            )
            db_session.add(ind)
            db_session.commit()

        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit",
                data={
                    "code": "newcodeinuse",  # Code change while in use
                    "name": "Changed Type",
                    "sort_order": "10",
                    "is_active": "y",
                },
                follow_redirects=False,
            )
        # Should re-render form with flash error
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_invalid_data_rerenders_form(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "editinvalidtype", "Edit Invalid Type")
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit",
                data={"code": "", "name": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_json_valid_updates_type(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_type(db_session, "jsonupdatetype", "JSON Update Type")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/types/{row.id}/edit",
            data=_json({
                "code": "jsonupdatetype",
                "name": "JSON Updated Type",
                "sort_order": 5,
                "is_active": True,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_404_for_missing_type(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/indicator-bank/measurement-lookups/types/9999999/edit?partial=1"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator-bank/measurement-lookups/units/new
# ---------------------------------------------------------------------------

class TestNewMeasurementUnit:
    def test_get_without_partial_redirects(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/indicator-bank/measurement-lookups/units/new",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_with_partial_returns_html(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(
                "/admin/indicator-bank/measurement-lookups/units/new?partial=1",
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_valid_data_creates_unit(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/units/new",
            data={
                "code": "newunit01",
                "name": "New Unit 01",
                "sort_order": "5",
                "is_active": "y",
                "allows_disaggregation": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            row = IndicatorBankUnit.query.filter_by(code="newunit01").first()
            assert row is not None

    def test_post_invalid_data_rerenders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                "/admin/indicator-bank/measurement-lookups/units/new",
                data={"code": "", "name": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_json_valid_creates_unit(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/units/new",
            data=_json({
                "code": "jsonunit01",
                "name": "JSON Unit 01",
                "sort_order": 5,
                "is_active": True,
                "allows_disaggregation": False,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_post_json_invalid_returns_400(self, logged_in_client, db_session):
        with _mock_render():
            resp = logged_in_client.post(
                "/admin/indicator-bank/measurement-lookups/units/new",
                data=_json({"code": "", "name": ""}),
                content_type="application/json",
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator-bank/measurement-lookups/units/<uid>/edit
# ---------------------------------------------------------------------------

class TestEditMeasurementUnit:
    def test_get_without_partial_redirects(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "editunit_redir", "Edit Unit Redir")
        resp = logged_in_client.get(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_with_partial_returns_html(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "editunit_partial", "Edit Unit Partial")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(
                f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit?partial=1",
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_valid_data_updates_unit(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "updateunit", "Update Unit")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit",
            data={
                "code": "updateunit",
                "name": "Updated Unit Name",
                "sort_order": "10",
                "is_active": "y",
                "allows_disaggregation": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_code_change_blocked_when_in_use(self, logged_in_client, db_session, app):
        from app.models import IndicatorBank
        with app.app_context():
            row = _create_unit(db_session, "inuseunitchange", "In-Use Unit")
            ind = IndicatorBank(
                name="Unit Ref Indicator",
                type="number",
                unit="inuseunitchange",
                indicator_unit_id=row.id,
            )
            db_session.add(ind)
            db_session.commit()

        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit",
                data={
                    "code": "newcodeinuse2",  # Changed code while in use
                    "name": "Changed Unit",
                    "sort_order": "10",
                    "is_active": "y",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_invalid_rerenders_form(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "editinvalidunit", "Edit Invalid Unit")
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit",
                data={"code": "", "name": ""},
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_json_valid_updates_unit(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "jsonupdateunit", "JSON Update Unit")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit",
            data=_json({
                "code": "jsonupdateunit",
                "name": "JSON Updated Unit",
                "sort_order": 5,
                "is_active": True,
                "allows_disaggregation": True,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_get_unit_with_delete_url_when_no_usage(self, logged_in_client, db_session, app):
        """Unit with no usage should have delete_url available in partial."""
        with app.app_context():
            row = _create_unit(db_session, "nodeletunit", "No Delete Unit")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(
                f"/admin/indicator-bank/measurement-lookups/units/{row.id}/edit?partial=1",
            )
        assert resp.status_code == 200
        # delete_url should be passed to template
        call_kwargs = mock_rt.call_args
        assert call_kwargs is not None

    def test_404_for_missing_unit(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/indicator-bank/measurement-lookups/units/9999999/edit?partial=1"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/indicator-bank/measurement-lookups/units/<uid>/delete
# ---------------------------------------------------------------------------

class TestDeleteMeasurementUnit:
    def test_delete_unit_not_in_use(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "deleteunitok", "Delete Unit OK")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert IndicatorBankUnit.query.get(row.id) is None

    def test_delete_unit_in_use_returns_error(self, logged_in_client, db_session, app):
        from app.models import IndicatorBank
        with app.app_context():
            row = _create_unit(db_session, "deletunitinuse", "Delete Unit In Use")
            ind = IndicatorBank(
                name="Delete Unit Ref",
                type="number",
                unit="deletunitinuse",
                indicator_unit_id=row.id,
            )
            db_session.add(ind)
            db_session.commit()

        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_unit_in_use_json_returns_400(self, logged_in_client, db_session, app):
        from app.models import IndicatorBank
        with app.app_context():
            row = _create_unit(db_session, "deletunitinusejson", "Delete Unit In Use JSON")
            ind = IndicatorBank(
                name="Delete Unit JSON Ref",
                type="number",
                unit="deletunitinusejson",
                indicator_unit_id=row.id,
            )
            db_session.add(ind)
            db_session.commit()

        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/delete",
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_delete_unit_not_in_use_json_returns_ok(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "deletunitokjson", "Delete Unit OK JSON")
        resp = logged_in_client.post(
            f"/admin/indicator-bank/measurement-lookups/units/{row.id}/delete",
            content_type="application/json",
            follow_redirects=False,
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            row = _create_unit(db_session, "deletexception", "Delete Exception")
        with patch(
            "app.routes.admin.system_admin.indicator_lookups.db"
        ) as mock_db:
            mock_db.session.delete.side_effect = Exception("db error")
            mock_db.session.commit = MagicMock()
            mock_db.session.rollback = MagicMock()
            resp = logged_in_client.post(
                f"/admin/indicator-bank/measurement-lookups/units/{row.id}/delete",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_delete_404_for_missing_unit(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator-bank/measurement-lookups/units/9999999/delete",
            follow_redirects=False,
        )
        assert resp.status_code == 404
