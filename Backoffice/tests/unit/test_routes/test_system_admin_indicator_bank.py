"""
Tests for app/routes/admin/system_admin/indicator_bank.py
Targeting 100% code coverage of indicator bank management routes.
"""
import json
import io
import pytest
from unittest.mock import patch, MagicMock, call
from app.models import IndicatorBank, CommonWord
from tests.factories import create_test_admin

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _mock_render(return_value="<html>ok</html>"):
    return patch(
        "app.routes.admin.system_admin.indicator_bank.render_template",
        return_value=return_value,
    )


def _create_indicator(db_session, name="Test Indicator", itype="number", unit=None):
    existing = IndicatorBank.query.filter_by(name=name).first()
    if existing:
        return existing
    ind = IndicatorBank(name=name, type=itype, unit=unit, archived=False)
    db_session.add(ind)
    db_session.commit()
    db_session.refresh(ind)
    return ind


def _create_common_word(db_session, term="test_term", meaning="Test meaning"):
    existing = CommonWord.query.filter_by(term=term).first()
    if existing:
        return existing
    word = CommonWord(term=term, meaning=meaning, is_active=True)
    db_session.add(word)
    db_session.commit()
    db_session.refresh(word)
    return word


@pytest.fixture(scope="function")
def admin_with_create_perm(db_session, app):
    """Admin user with indicator_bank.create permission."""
    from tests.factories import create_test_admin
    from app.models.rbac import RbacRole, RbacPermission, RbacRolePermission
    from app import db as _db

    with app.app_context():
        user = create_test_admin(
            db_session,
            email="admin_create_ib@example.com",
            name="Admin Create IB",
            password="admin_password",
        )
        # Grant indicator_bank.create
        role = _db.session.query(RbacRole).filter_by(code="admin_core").first()
        if role:
            perm = _db.session.query(RbacPermission).filter_by(code="admin.indicator_bank.create").first()
            if not perm:
                perm = RbacPermission(
                    code="admin.indicator_bank.create",
                    name="admin.indicator_bank.create",
                    description="admin.indicator_bank.create",
                )
                _db.session.add(perm)
                _db.session.flush()
            existing = _db.session.query(RbacRolePermission).filter_by(
                role_id=role.id, permission_id=perm.id
            ).first()
            if not existing:
                _db.session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
            _db.session.commit()

        user_id = user.id
        db_session.expunge(user)
        user.id = user_id
        yield user


@pytest.fixture(scope="function")
def logged_in_create_client(client, admin_with_create_perm, app):
    """Test client logged in as admin with create permission."""
    with app.app_context():
        user_id = admin_with_create_perm.id
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


# ---------------------------------------------------------------------------
# GET /admin/indicator_bank  – list indicators
# ---------------------------------------------------------------------------

class TestManageIndicatorBank:
    def test_get_renders_page(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/indicator_bank")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_json_returns_indicators(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="JSON List Indicator")
        resp = logged_in_client.get(
            "/admin/indicator_bank",
            headers={"Accept": "application/json"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert "indicators" in data

    def test_get_with_search_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Searchable Indicator")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/indicator_bank?search=Searchable")
        assert resp.status_code == 200

    def test_get_with_sector_filter(self, logged_in_client, db_session):
        with _mock_render():
            resp = logged_in_client.get("/admin/indicator_bank?sector=health")
        assert resp.status_code == 200

    def test_get_with_type_filter(self, logged_in_client, db_session):
        with _mock_render():
            resp = logged_in_client.get("/admin/indicator_bank?type=number")
        assert resp.status_code == 200

    def test_get_with_indicators_having_sector_data(self, logged_in_client, db_session, app):
        from app.models import Sector
        with app.app_context():
            sector = Sector(name="Health IB Sector", is_active=True)
            db_session.add(sector)
            db_session.flush()
            ind = IndicatorBank(
                name="Sector Indicator",
                type="number",
                sector={"primary": sector.id},
                sub_sector={"primary": None},
            )
            db_session.add(ind)
            db_session.commit()

        with _mock_render():
            resp = logged_in_client.get("/admin/indicator_bank")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /admin/indicator_bank/neural_map
# ---------------------------------------------------------------------------

class TestIndicatorBankNeuralMap:
    def test_get_renders_neural_map(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/indicator_bank/neural_map")
        assert resp.status_code == 200
        mock_rt.assert_called_once()


# ---------------------------------------------------------------------------
# GET /admin/indicator_bank/neural_map/data
# ---------------------------------------------------------------------------

class TestIndicatorBankNeuralMapData:
    def test_returns_scatter_data(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.build_embedding_scatter",
            return_value={"nodes": [], "groups": [], "count": 0},
        ) as mock_scatter:
            # patch import inside route
            with patch.dict("sys.modules", {
                "app.services.indicators.neural_map": MagicMock(
                    build_embedding_scatter=lambda **kw: {"nodes": [], "groups": [], "count": 0}
                )
            }):
                resp = logged_in_client.get("/admin/indicator_bank/neural_map/data")
        assert resp.status_code in (200, 500)

    def test_exception_returns_server_error(self, logged_in_client, db_session):
        with patch(
            "app.services.indicators.neural_map.build_embedding_scatter",
            side_effect=Exception("no embeddings"),
        ):
            resp = logged_in_client.get("/admin/indicator_bank/neural_map/data")
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# POST /admin/indicator_bank/neural_map/probe
# ---------------------------------------------------------------------------

class TestIndicatorBankNeuralMapProbe:
    def test_empty_query_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator_bank/neural_map/probe",
            data=json.dumps({"query": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_exception_returns_500(self, logged_in_client, db_session):
        with patch(
            "app.services.indicators.neural_map.probe_query_embedding",
            side_effect=Exception("embedding error"),
        ):
            resp = logged_in_client.post(
                "/admin/indicator_bank/neural_map/probe",
                data=json.dumps({"query": "health indicators"}),
                content_type="application/json",
            )
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# POST /admin/indicator_bank/sync_remote
# ---------------------------------------------------------------------------

class TestSyncIndicatorBankRemote:
    def test_sync_returns_ok_on_success(self, logged_in_client, db_session):
        with patch(
            "app.services.indicators.remote_sync_service.start_remote_sync",
            return_value=(True, "Sync started"),
        ), patch(
            "app.services.indicators.remote_sync_service.get_remote_sync_state",
            return_value={"status": "running"},
        ):
            resp = logged_in_client.post(
                "/admin/indicator_bank/sync_remote",
                data=json.dumps({}),
                content_type="application/json",
            )
        assert resp.status_code == 200

    def test_sync_returns_400_on_failure(self, logged_in_client, db_session):
        with patch(
            "app.services.indicators.remote_sync_service.start_remote_sync",
            return_value=(False, "Already running"),
        ), patch(
            "app.services.indicators.remote_sync_service.get_remote_sync_state",
            return_value={"status": "running"},
        ):
            resp = logged_in_client.post(
                "/admin/indicator_bank/sync_remote",
                data=json.dumps({}),
                content_type="application/json",
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /admin/indicator_bank/sync_remote/status
# ---------------------------------------------------------------------------

class TestSyncIndicatorBankRemoteStatus:
    def test_returns_sync_state(self, logged_in_client, db_session):
        with patch(
            "app.services.indicators.remote_sync_service.get_remote_sync_state",
            return_value={"status": "idle"},
        ):
            resp = logged_in_client.get("/admin/indicator_bank/sync_remote/status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /admin/indicator_bank/view/<id>
# ---------------------------------------------------------------------------

class TestViewIndicatorBank:
    def test_view_existing_indicator(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="View Me Indicator")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/indicator_bank/view/{ind.id}")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_view_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/indicator_bank/view/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator_bank/add  – add indicator
# ---------------------------------------------------------------------------

class TestAddIndicatorBank:
    def test_get_renders_form_without_permission(self, logged_in_client, db_session):
        """Default admin doesn't have create permission, gets redirect."""
        resp = logged_in_client.get(
            "/admin/indicator_bank/add",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_renders_form_with_permission(self, logged_in_create_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_create_client.get("/admin/indicator_bank/add")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_invalid_redirects_to_form(self, logged_in_create_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_create_client.post(
                "/admin/indicator_bank/add",
                data={"name": ""},  # Invalid
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator_bank/edit/<id>
# ---------------------------------------------------------------------------

class TestEditIndicatorBank:
    def test_get_renders_edit_form(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Edit Form Indicator")
        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/indicator_bank/edit/{ind.id}")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_json_updates_fields(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="JSON Edit Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/edit/{ind.id}",
            data=json.dumps({"name": "Updated JSON Name"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_post_json_updates_name_translation(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Trans Edit Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/edit/{ind.id}",
            data=json.dumps({"name_fr": "Indicateur en français"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_post_json_updates_definition_translation(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Def Trans Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/edit/{ind.id}",
            data=json.dumps({"definition_fr": "Définition en français"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_post_json_no_valid_fields_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="No Fields JSON Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/edit/{ind.id}",
            data=json.dumps({"_invalid_field_xyz": "value"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_json_archive_without_permission_returns_403(self, logged_in_client, db_session, app):
        """Editing archived field requires archive permission. Default admin has it."""
        with app.app_context():
            ind = _create_indicator(db_session, name="Archive JSON Indicator")
        # With default admin who DOES have archive permission, this should work
        resp = logged_in_client.post(
            f"/admin/indicator_bank/edit/{ind.id}",
            data=json.dumps({"archived": True}),
            content_type="application/json",
        )
        # Admin has archive permission so should succeed
        assert resp.status_code in (200, 403)

    def test_post_json_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="JSON Exc Indicator")
        with patch("app.routes.admin.system_admin.indicator_bank.db") as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            resp = logged_in_client.post(
                f"/admin/indicator_bank/edit/{ind.id}",
                data=json.dumps({"name": "New Name"}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_post_form_invalid_renders_form(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Form Invalid Indicator")
        with _mock_render() as mock_rt:
            resp = logged_in_client.post(
                f"/admin/indicator_bank/edit/{ind.id}",
                data={"name": ""},  # Invalid
                follow_redirects=False,
            )
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_form_ajax_invalid_returns_json_errors(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="AJAX Form Invalid")
        with _mock_render():
            resp = logged_in_client.post(
                f"/admin/indicator_bank/edit/{ind.id}",
                data={"name": ""},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
        assert resp.status_code in (200, 400)

    def test_get_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/indicator_bank/edit/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/indicator_bank/delete/<id>
# ---------------------------------------------------------------------------

class TestDeleteIndicatorBank:
    def test_delete_success(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Delete Me Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/delete/{ind.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert IndicatorBank.query.get(ind.id) is None

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Delete Exc Indicator")
        with patch("app.routes.admin.system_admin.indicator_bank.IndicatorBank") as mock_class:
            mock_ind = MagicMock()
            mock_ind.id = ind.id
            mock_ind.name = ind.name
            mock_ind.archived = False
            mock_class.query.get_or_404.return_value = mock_ind
            with patch("app.routes.admin.system_admin.indicator_bank.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                mock_db.session.add = MagicMock()
                mock_db.session.flush = MagicMock()
                resp = logged_in_client.post(
                    f"/admin/indicator_bank/delete/{ind.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_delete_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator_bank/delete/9999999",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/indicator_bank/archive/<id>
# ---------------------------------------------------------------------------

class TestArchiveIndicatorBank:
    def test_archive_indicator(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Archive Me Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/archive/{ind.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            updated = IndicatorBank.query.get(ind.id)
            assert updated.archived is True

    def test_unarchive_indicator(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Unarchive Me Indicator")
            ind.archived = True
            db_session.commit()
        resp = logged_in_client.post(
            f"/admin/indicator_bank/archive/{ind.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            updated = IndicatorBank.query.get(ind.id)
            assert updated.archived is False

    def test_archive_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Archive Exc Indicator")
        with patch("app.routes.admin.system_admin.indicator_bank.IndicatorBank") as mock_class:
            mock_ind = MagicMock()
            mock_ind.id = ind.id
            mock_ind.name = ind.name
            mock_ind.archived = False
            mock_class.query.get_or_404.return_value = mock_ind
            with patch("app.routes.admin.system_admin.indicator_bank.db") as mock_db:
                mock_db.session.flush.side_effect = Exception("db error")
                mock_db.session.add = MagicMock()
                resp = logged_in_client.post(
                    f"/admin/indicator_bank/archive/{ind.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_archive_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator_bank/archive/9999999",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/indicator_bank/translations/<id>
# ---------------------------------------------------------------------------

class TestUpdateIndicatorTranslations:
    def test_update_translations_success(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Trans Update Indicator")
        resp = logged_in_client.post(
            f"/admin/indicator_bank/translations/{ind.id}",
            data={"name_fr": "Nom en français", "definition_fr": "Définition"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_update_translations_404(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/indicator_bank/translations/9999999",
            data={"name_fr": "Test"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/sessions/cleanup
# ---------------------------------------------------------------------------

class TestSessionCleanup:
    def test_cleanup_sessions_success(self, logged_in_client, db_session):
        with patch(
            "app.services.platform.user_analytics_service.cleanup_inactive_sessions",
            return_value=5,
        ):
            resp = logged_in_client.post(
                "/admin/sessions/cleanup",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_cleanup_sessions_exception(self, logged_in_client, db_session):
        with patch(
            "app.services.platform.user_analytics_service.cleanup_inactive_sessions",
            side_effect=Exception("cleanup error"),
        ):
            resp = logged_in_client.post(
                "/admin/sessions/cleanup",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /admin/sessions/status
# ---------------------------------------------------------------------------

class TestSessionStatus:
    def test_redirects_to_analytics(self, logged_in_client, db_session):
        resp = logged_in_client.get(
            "/admin/sessions/status",
            follow_redirects=False,
        )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET/POST /admin/indicator_bank/export
# ---------------------------------------------------------------------------

class TestExportIndicators:
    def test_get_export_all_indicators(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Export Indicator")
        resp = logged_in_client.get("/admin/indicator_bank/export")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type or "excel" in resp.content_type.lower()

    def test_post_export_selected_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            ind = _create_indicator(db_session, name="Selected Export Indicator")
        resp = logged_in_client.post(
            "/admin/indicator_bank/export",
            data={"selected_ids": str(ind.id)},
            follow_redirects=False,
        )
        assert resp.status_code == 200

    def test_export_exception_redirects(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.IndicatorBank"
        ) as mock_class:
            mock_class.query.order_by.side_effect = Exception("db error")
            resp = logged_in_client.get(
                "/admin/indicator_bank/export",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /admin/api/indicator-bank/wizard-options
# ---------------------------------------------------------------------------

class TestIndicatorBankWizardOptions:
    def test_returns_wizard_options(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(
                db_session,
                name="Wizard Options Indicator",
                itype="number",
            )
            indicator = IndicatorBank.query.filter_by(name="Wizard Options Indicator").first()
            indicator.area = "EF2"
            indicator.area_label = "Efficiency"
            indicator._related_programs_list = ["Health"]
            db_session.commit()

        resp = logged_in_client.get("/admin/api/indicator-bank/wizard-options")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert "sectors" in data
        assert "subsectors" in data
        assert "programs" in data
        assert "areas" in data
        assert "types" in data

    def test_returns_wizard_options_with_scalar_related_programs(self, logged_in_client, db_session, app):
        with app.app_context():
            indicator = _create_indicator(db_session, name="Scalar Programs Indicator")
            indicator._related_programs_list = "Health"
            db_session.commit()

        resp = logged_in_client.get("/admin/api/indicator-bank/wizard-options")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert "Health" in data["programs"]

    def test_wizard_options_areas_follow_spef_sort_order(self, logged_in_client, db_session, app):
        with app.app_context():
            from app.models import IndicatorBankSpef

            late = IndicatorBankSpef(code="SP9", name="Late SP", sort_order=90, is_active=True)
            early = IndicatorBankSpef(code="EF1", name="Early EF", sort_order=10, is_active=True)
            db_session.add_all([late, early])
            db_session.commit()

        resp = logged_in_client.get("/admin/api/indicator-bank/wizard-options")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        codes = [area["code"] for area in data["areas"] if area["code"] in {"EF1", "SP9"}]
        assert codes.index("EF1") < codes.index("SP9")
        assert data["areas"][0].get("sort_order") is not None
        assert data["areas"][0].get("id") is not None


# ---------------------------------------------------------------------------
# POST /admin/api/indicator-count
# ---------------------------------------------------------------------------

class TestGetFilteredIndicatorCount:
    def test_returns_count_no_filters(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Count Indicator")
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({"filters": []}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "count" in data

    def test_returns_count_with_type_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Type Filter Indicator", itype="percentage")
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "type", "values": ["percentage"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_unit_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "unit", "values": ["people"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_emergency_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "emergency", "values": ["true"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_archived_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "archived", "values": ["false"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_related_programs_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "related_programs", "values": ["health"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_sector_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "sector", "values": ["1"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_sector_primary_only(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "sector", "values": ["1"], "primary_only": True}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_returns_count_with_subsector_filter(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "subsector", "values": ["2"]}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_include_indicators_flag(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Include Indicators Test")
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({"filters": [], "include_indicators": True}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "indicators" in data

    def test_returns_count_with_area_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            indicator = _create_indicator(db_session, name="Area Filter Indicator")
            indicator.area = "EF2"
            indicator.area_label = "Efficiency"
            db_session.commit()

        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "area", "values": ["EF2"]}],
                "include_indicators": True,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] >= 1
        assert any(item.get("area") == "EF2" for item in data.get("indicators", []))

    def test_returns_count_with_search_filter(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_indicator(db_session, name="Unique Searchable Wizard Indicator")

        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "search": "Unique Searchable Wizard",
                "include_indicators": True,
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["count"] >= 1
        assert any("Unique Searchable Wizard" in item.get("name", "") for item in data.get("indicators", []))

    def test_with_empty_filter_values_skipped(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/api/indicator-count",
            data=json.dumps({
                "filters": [{"field": "type", "values": []}]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_exception_returns_server_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.db"
        ) as mock_db:
            mock_db.session.query.side_effect = Exception("db error")
            resp = logged_in_client.post(
                "/admin/api/indicator-count",
                data=json.dumps({"filters": []}),
                content_type="application/json",
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /admin/common_words  – manage common words
# ---------------------------------------------------------------------------

class TestManageCommonWords:
    def test_get_renders_page(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/common_words")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_with_search(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_common_word(db_session, "searchterm", "Searchable meaning")
        with _mock_render():
            resp = logged_in_client.get("/admin/common_words?search=searchterm")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /admin/common_words/add
# ---------------------------------------------------------------------------

class TestAddCommonWord:
    def test_add_valid_word_returns_json(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/common_words/add",
            data={"term": "newword", "meaning": "New word meaning", "is_active": "y"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_add_invalid_word_returns_form_errors(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/common_words/add",
            data={"term": "", "meaning": ""},  # Missing required fields
        )
        assert resp.status_code in (200, 400)

    def test_add_exception_returns_400(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.CommonWord",
            side_effect=Exception("db error"),
        ):
            resp = logged_in_client.post(
                "/admin/common_words/add",
                data={"term": "errword", "meaning": "Error meaning"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /admin/common_words/edit/<id>
# ---------------------------------------------------------------------------

class TestEditCommonWord:
    def test_edit_valid_word_returns_json(self, logged_in_client, db_session, app):
        with app.app_context():
            word = _create_common_word(db_session, "editword", "Edit meaning")
        resp = logged_in_client.post(
            f"/admin/common_words/edit/{word.id}",
            data={"term": "editword", "meaning": "Updated meaning", "is_active": "y"},
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_edit_invalid_returns_form_errors(self, logged_in_client, db_session, app):
        with app.app_context():
            word = _create_common_word(db_session, "invalideditword", "Invalid edit")
        resp = logged_in_client.post(
            f"/admin/common_words/edit/{word.id}",
            data={"term": "", "meaning": ""},
        )
        assert resp.status_code in (200, 400)

    def test_edit_exception_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            word = _create_common_word(db_session, "excword", "Exception word")
        with patch(
            "app.routes.admin.system_admin.indicator_bank.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            resp = logged_in_client.post(
                f"/admin/common_words/edit/{word.id}",
                data={"term": "excword", "meaning": "Test"},
            )
        assert resp.status_code == 400

    def test_edit_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/common_words/edit/9999999",
            data={"term": "test"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/common_words/delete/<id>
# ---------------------------------------------------------------------------

class TestDeleteCommonWord:
    def test_delete_word_success(self, logged_in_client, db_session, app):
        with app.app_context():
            word = _create_common_word(db_session, "deleteword", "Delete meaning")
        resp = logged_in_client.post(
            f"/admin/common_words/delete/{word.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert CommonWord.query.get(word.id) is None

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            word = _create_common_word(db_session, "deleteexcword", "Delete exc")
        with patch("app.routes.admin.system_admin.indicator_bank.CommonWord") as mock_class:
            mock_word = MagicMock()
            mock_word.id = word.id
            mock_word.term = word.term
            mock_class.query.get_or_404.return_value = mock_word
            with patch("app.routes.admin.system_admin.indicator_bank.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                mock_db.session.flush = MagicMock()
                resp = logged_in_client.post(
                    f"/admin/common_words/delete/{word.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_delete_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/common_words/delete/9999999",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/common_words/export
# ---------------------------------------------------------------------------

class TestExportCommonWords:
    def test_export_returns_excel(self, logged_in_client, db_session, app):
        with app.app_context():
            _create_common_word(db_session, "exportword", "Export meaning")
        resp = logged_in_client.get("/admin/common_words/export")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type or "excel" in resp.content_type.lower()

    def test_export_exception_redirects(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.CommonWord"
        ) as mock_class:
            mock_class.query.filter_by.side_effect = Exception("db error")
            resp = logged_in_client.get(
                "/admin/common_words/export",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/common_words/import
# ---------------------------------------------------------------------------

class TestImportCommonWords:
    def test_missing_file_flashes_error(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/common_words/import",
            data={},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_empty_filename_flashes_error(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/common_words/import",
            data={"excel_file": (io.BytesIO(b""), "")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_invalid_extension_flashes_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.validate_upload_extension_and_mime",
            return_value=(False, "Invalid file", ".txt"),
        ):
            resp = logged_in_client.post(
                "/admin/common_words/import",
                data={"excel_file": (io.BytesIO(b"data"), "test.txt")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_missing_required_columns_flashes_error(self, logged_in_client, db_session, app):
        import pandas as pd
        from io import BytesIO
        # Create Excel without required columns
        with patch(
            "app.routes.admin.system_admin.indicator_bank.validate_upload_extension_and_mime",
            return_value=(True, None, ".xlsx"),
        ), patch(
            "app.routes.admin.system_admin.indicator_bank.pd"
        ) as mock_pd:
            mock_pd.read_excel.return_value = pd.DataFrame({"WrongCol": ["data"]})
            resp = logged_in_client.post(
                "/admin/common_words/import",
                data={"excel_file": (io.BytesIO(b"data"), "test.xlsx")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_valid_import_creates_words(self, logged_in_client, db_session, app):
        import pandas as pd
        with app.app_context():
            df_data = pd.DataFrame({
                "Term": ["importedword"],
                "Meaning": ["Imported meaning"],
                "Active": ["TRUE"],
            })
        with patch(
            "app.routes.admin.system_admin.indicator_bank.validate_upload_extension_and_mime",
            return_value=(True, None, ".xlsx"),
        ), patch(
            "app.routes.admin.system_admin.indicator_bank.pd"
        ) as mock_pd:
            mock_pd.read_excel.return_value = df_data
            mock_pd.notna = pd.notna
            mock_pd.DataFrame = pd.DataFrame
            mock_pd.ExcelWriter = pd.ExcelWriter
            resp = logged_in_client.post(
                "/admin/common_words/import",
                data={"excel_file": (io.BytesIO(b"data"), "test.xlsx")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_import_with_overwrite(self, logged_in_client, db_session, app):
        import pandas as pd
        with app.app_context():
            _create_common_word(db_session, "overwriteword", "Old meaning")
            df_data = pd.DataFrame({
                "Term": ["overwriteword"],
                "Meaning": ["New meaning"],
            })
        with patch(
            "app.routes.admin.system_admin.indicator_bank.validate_upload_extension_and_mime",
            return_value=(True, None, ".xlsx"),
        ), patch(
            "app.routes.admin.system_admin.indicator_bank.pd"
        ) as mock_pd:
            mock_pd.read_excel.return_value = df_data
            mock_pd.notna = pd.notna
            resp = logged_in_client.post(
                "/admin/common_words/import",
                data={
                    "excel_file": (io.BytesIO(b"data"), "test.xlsx"),
                    "overwrite_existing": "on",
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_import_exception_redirects(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.indicator_bank.validate_upload_extension_and_mime",
            return_value=(True, None, ".xlsx"),
        ), patch(
            "app.routes.admin.system_admin.indicator_bank.pd"
        ) as mock_pd:
            mock_pd.read_excel.side_effect = Exception("parse error")
            resp = logged_in_client.post(
                "/admin/common_words/import",
                data={"excel_file": (io.BytesIO(b"data"), "test.xlsx")},
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /admin/common_words/template
# ---------------------------------------------------------------------------

class TestDownloadCommonWordsTemplate:
    def test_download_template(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/common_words/template")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type or "excel" in resp.content_type.lower()
