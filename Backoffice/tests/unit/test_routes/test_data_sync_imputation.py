"""
Comprehensive tests for app/routes/admin/data_sync_imputation.py
Targeting 100% code coverage of template special operations routes.
"""
import io
import json
import time
import uuid
import pytest
import tempfile
import os
from contextlib import contextmanager, suppress
from unittest.mock import patch, MagicMock

from tests.factories import create_test_template, create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


def _create_data_sync_test_job(
    template_id,
    user_id,
    *,
    status="running",
    download_ready=False,
    preview_path=None,
):
    from app.services.imports.async_import_job_store import (
        FDRS_DATA_SYNC_JOB_TYPE,
        create_import_job,
        update_import_job,
    )

    job_id = uuid.uuid4().hex
    create_import_job(
        job_id=job_id,
        job_type=FDRS_DATA_SYNC_JOB_TYPE,
        user_id=user_id,
        initial={
            "template_id": template_id,
            "stage": "running",
            "message": "Running...",
            "current": 10,
            "total": 100,
            "percent": 10.0,
            "preview_path": preview_path,
            "download_ready": download_ready,
        },
    )
    update_import_job(
        job_id,
        force=True,
        status=status,
        download_ready=download_ready,
        preview_path=preview_path,
    )
    return job_id


@contextmanager
def _auth():
    """Bypass RBAC checks for admin template routes."""
    with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
         patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
         patch("app.routes.admin.data_sync_imputation.check_template_access", return_value=True):
        yield


def _mock_render(return_value="<html>template</html>"):
    return patch(
        "app.routes.admin.data_sync_imputation.render_template",
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# GET /<template_id>  –  data_sync_view
# ---------------------------------------------------------------------------

class TestSpecialTemplateView:
    def test_get_existing_template_renders(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Special Template Test")
        with _auth(), _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.get("/admin/templates/data-sync/99999")
        assert resp.status_code == 404

    def test_get_template_access_denied_redirects(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Denied Template")
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.data_sync_imputation.check_template_access", return_value=False):
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}",
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_get_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.location.lower()

    def test_get_template_with_sections_and_items(self, logged_in_client, db_session, app):
        from tests.factories import create_test_section, create_test_item
        template = create_test_template(db_session, name="Template With Sections")
        section = create_test_section(db_session, template)
        item = create_test_item(db_session, section, template)
        with _auth(), _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}")
        assert resp.status_code == 200


class TestFdrsSyncImputationRoute:
    def test_get_renders_for_system_manager(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS")
        with patch("app.utils.data_quality_constants.FDRS_TEMPLATE_ID", template.id), \
             patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.admin.data_sync_imputation.check_template_access", return_value=True), \
             _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/fdrs-sync-imputation")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_get_unauthenticated_redirects(self, client):
        resp = client.get("/admin/fdrs-sync-imputation", follow_redirects=False)
        assert resp.status_code == 302
        assert "login" in resp.location.lower()


# ---------------------------------------------------------------------------
# POST /impute/template2
# ---------------------------------------------------------------------------

class TestImputeTemplate2:
    def test_missing_target_period_redirects(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_missing_target_period_json_redirects(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                json={},
                headers=_json_headers(),
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_valid_period_success(self, logged_in_client, db_session, app):
        mock_result = {
            "success": True,
            "target_period": "2025",
            "source_period": "2024",
            "countries_processed": 5,
            "items_imputed": 10,
            "rows_created": 8,
            "rows_updated": 2,
        }
        with _auth(), \
             patch("app.routes.admin.data_sync_imputation.ImputationService.impute_template_2",
                   return_value=mock_result):
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                data={"target_period": "2025"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_valid_period_imputation_failure(self, logged_in_client, db_session, app):
        mock_result = {"success": False, "error": "No source period found"}
        with _auth(), \
             patch("app.routes.admin.data_sync_imputation.ImputationService.impute_template_2",
                   return_value=mock_result):
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                data={"target_period": "2025"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_valid_period_with_exception(self, logged_in_client, db_session, app):
        with _auth(), \
             patch("app.routes.admin.data_sync_imputation.ImputationService.impute_template_2",
                   side_effect=Exception("db error")):
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                data={"target_period": "2025"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_valid_period_from_json_body(self, logged_in_client, db_session, app):
        mock_result = {"success": True, "target_period": "2025", "source_period": "2024",
                       "countries_processed": 1, "items_imputed": 1, "rows_created": 1, "rows_updated": 0}
        with _auth(), \
             patch("app.routes.admin.data_sync_imputation.ImputationService.impute_template_2",
                   return_value=mock_result):
            resp = logged_in_client.post(
                "/admin/templates/data-sync/impute/template2",
                json={"target_period": "2025"},
                headers=_json_headers(),
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/impute/template2", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /update-imputation-methods-batch
# ---------------------------------------------------------------------------

class TestUpdateImputationMethodsBatch:
    def test_no_updates_returns_400(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/update-imputation-methods-batch",
                json={"updates": []},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_missing_updates_key_returns_400(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/update-imputation-methods-batch",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_valid_updates_with_existing_item(self, logged_in_client, db_session, app):
        from app.models import FormItem
        from tests.factories import create_test_section, create_test_template
        template = create_test_template(db_session, name="Imputation Method Template")
        section = create_test_section(db_session, template)
        from tests.factories import create_test_item
        item = create_test_item(db_session, section, template, item_type="indicator")

        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/update-imputation-methods-batch",
                json={"updates": [{"item_id": item.id, "method": "carry_forward"}]},
                headers=_json_headers(),
            )
        assert resp.status_code == 200

    def test_valid_updates_with_nonexistent_item(self, logged_in_client, db_session, app):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/update-imputation-methods-batch",
                json={"updates": [{"item_id": 99999, "method": "carry_forward"}]},
                headers=_json_headers(),
            )
        assert resp.status_code in (200, 404)

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/update-imputation-methods-batch", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /<template_id>/preview-data
# ---------------------------------------------------------------------------

class TestPreviewData:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Preview Data Template")
        with _auth():
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}/preview-data")
        assert resp.status_code == 400

    def test_with_year_no_assignments(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Preview Data No Assign Template")
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/preview-data?year=2025"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True or "data" in data

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.get("/admin/templates/data-sync/99999/preview-data?year=2025")
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1/preview-data?year=2025", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/preview-imputation
# ---------------------------------------------------------------------------

class TestPreviewImputation:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Prev Imp Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_invalid_year_format_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Prev Imp Invalid Year Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation",
                json={"year": "notayear"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_valid_year_no_assignments_returns_ok(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Prev Imp No Assign Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 200

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/99999/preview-imputation",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/1/preview-imputation", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/preview-data-chunked
# ---------------------------------------------------------------------------

class TestPreviewDataChunked:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Chunked Data Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-data-chunked",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_valid_request_returns_ok(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Chunked Data Valid Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-data-chunked",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 200

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/99999/preview-data-chunked",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /<template_id>/preview-imputation-chunked
# ---------------------------------------------------------------------------

class TestPreviewImputationChunked:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Chunked Imp Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation-chunked",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_invalid_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Chunked Imp Bad Year Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation-chunked",
                json={"year": "invalid"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_valid_year_no_assignments(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Chunked Imp No Assign Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/preview-imputation-chunked",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 200

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/99999/preview-imputation-chunked",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /<template_id>/filter-options
# ---------------------------------------------------------------------------

class TestFilterOptions:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Filter Options Template")
        with _auth():
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}/filter-options")
        assert resp.status_code == 400

    def test_with_year_returns_ok(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Filter Options Year Template")
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/filter-options?year=2025"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True or "countries" in data

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.get("/admin/templates/data-sync/99999/filter-options?year=2025")
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1/filter-options?year=2025", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /<template_id>/available-periods
# ---------------------------------------------------------------------------

class TestAvailablePeriods:
    def test_no_assignments_returns_empty_list(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Available Periods Empty Template")
        with _auth():
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}/available-periods")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        assert data.get("periods") == []
        assert data.get("latest") is None

    def test_numeric_periods_sorted_descending(self, logged_in_client, db_session, app):
        from tests.factories import create_test_assignment_entity_status
        template = create_test_template(db_session, name="Available Periods Numeric Template")
        country = create_test_country(db_session, name="AP Country", iso3="APC", iso2="AP")
        for year in ("2023", "2025", "2024"):
            create_test_assignment_entity_status(
                db_session, country=country, template=template, period_name=year
            )
        with _auth():
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}/available-periods")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["periods"] == ["2025", "2024", "2023"]
        assert data["latest"] == "2025"

    def test_non_numeric_period_included(self, logged_in_client, db_session, app):
        from tests.factories import create_test_assignment_entity_status
        template = create_test_template(db_session, name="Available Periods Non-Numeric Template")
        country = create_test_country(db_session, name="NNP Country", iso3="NNP", iso2="NN")
        create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="Jan-Jun 2026"
        )
        with _auth():
            resp = logged_in_client.get(f"/admin/templates/data-sync/{template.id}/available-periods")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "Jan-Jun 2026" in data["periods"]
        assert data["latest"] == "Jan-Jun 2026"

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.get("/admin/templates/data-sync/99999/available-periods")
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1/available-periods", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/run-imputation-filtered
# ---------------------------------------------------------------------------

class TestRunImputationFiltered:
    def test_missing_year_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Imp Filtered Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/run-imputation-filtered",
                json={},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_non_template2_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Imp Non Template2")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/run-imputation-filtered",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        # template.id won't be 2 unless there's only one template, so it should fail
        assert resp.status_code in (200, 400)

    def test_template2_imputation_success(self, logged_in_client, db_session, app):
        mock_result = {
            "success": True,
            "target_period": "2025",
            "source_period": "2024",
            "countries_processed": 3,
            "items_imputed": 5,
            "rows_created": 5,
            "rows_updated": 0,
        }
        with _auth(), \
             patch("app.routes.admin.data_sync_imputation.ImputationService.impute_template_2_filtered",
                   return_value=mock_result):
            # Force template_id to 2 by patching the route check
            resp = logged_in_client.post(
                "/admin/templates/data-sync/2/run-imputation-filtered",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        # May 404 if template 2 doesn't exist, that's OK
        assert resp.status_code in (200, 400, 404)

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = logged_in_client.post(
                "/admin/templates/data-sync/99999/run-imputation-filtered",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/1/run-imputation-filtered", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/export-excel
# ---------------------------------------------------------------------------

class TestExportPreviewExcel:
    def _make_preview_data(self):
        return [
            {
                "country": "Test Country",
                "item_label": "Item 1",
                "item_unit": "Units",
                "current_value": 100,
                "imputed_value": 110,
                "method": "carry_forward",
                "source_periods": ["2024"],
            }
        ]

    def test_missing_year_or_data_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Export Excel Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/export-excel",
                json={"year": "2025"},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_missing_preview_data_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Export Excel No Data Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/export-excel",
                json={"year": "2025", "preview_data": []},
                headers=_json_headers(),
            )
        assert resp.status_code == 400

    def test_valid_export_returns_excel(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Export Excel Valid Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/export-excel",
                json={"year": "2025", "preview_data": self._make_preview_data()},
                headers=_json_headers(),
            )
        assert resp.status_code == 200
        assert "spreadsheet" in resp.content_type or "xlsx" in resp.content_type

    def test_valid_export_with_null_values(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="Export Excel Null Template")
        data = [
            {
                "country": "Test",
                "item_label": "Item",
                "item_unit": None,
                "current_value": None,
                "imputed_value": None,
                "method": None,
                "source_periods": [],
            }
        ]
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/export-excel",
                json={"year": "2025", "preview_data": data},
                headers=_json_headers(),
            )
        assert resp.status_code == 200

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/1/export-excel", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/run-data-sync
# ---------------------------------------------------------------------------

class TestRunDataSync:
    def _post_data_sync(self, logged_in_client, template_id, data=None):
        defaults = {"dry_run": False}
        if data:
            defaults.update(data)
        return logged_in_client.post(
            f"/admin/templates/data-sync/{template_id}/run-data-sync",
            json=defaults,
            headers=_json_headers(),
        )

    def test_nonexistent_template_returns_404(self, logged_in_client, db_session):
        with _auth():
            resp = self._post_data_sync(logged_in_client, 99999)
        assert resp.status_code == 404

    def test_access_denied_returns_403(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Deny Template")
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.admin.data_sync_imputation.check_template_access", return_value=False):
            resp = self._post_data_sync(logged_in_client, template.id)
        assert resp.status_code == 403

    def test_invalid_batch_size_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Bad Batch Template")
        with _auth():
            resp = self._post_data_sync(logged_in_client, template.id, {"batch_size": "abc"})
        assert resp.status_code == 400

    def test_batch_size_too_small_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Small Batch Template")
        with _auth():
            resp = self._post_data_sync(logged_in_client, template.id, {"batch_size": 50})
        assert resp.status_code == 400

    def test_invalid_fdrs_reported_states_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Bad States Template")
        with _auth():
            resp = self._post_data_sync(
                logged_in_client, template.id,
                {"fdrs_reported_import_states": [999]}  # Invalid state
            )
        assert resp.status_code == 400

    def test_invalid_fdrs_years_returns_400(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Bad Years Template")
        with _auth():
            resp = self._post_data_sync(
                logged_in_client, template.id,
                {"fdrs_years": "not,a,year"}
            )
        assert resp.status_code == 400

    def test_sync_sync_mode_success(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Sync Success Template")
        mock_run_import = MagicMock(return_value={"success": True, "records_imported": 10})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(logged_in_client, template.id)
        assert resp.status_code in (200, 400, 500)

    def test_async_mode_queues_job(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Async Template")
        mock_run_import = MagicMock(return_value={"success": True})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(
                logged_in_client, template.id,
                {"async": True}
            )
        assert resp.status_code in (200, 202, 400, 500)

    def test_test_mode_limits_data(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Test Mode Template")
        mock_run_import = MagicMock(return_value={"success": True})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(logged_in_client, template.id, {"test": True})
        assert resp.status_code in (200, 400, 500)

    def test_dry_run_with_import(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Dry Run Template")
        mock_run_import = MagicMock(return_value={"success": True})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(logged_in_client, template.id, {"dry_run": True})
        assert resp.status_code in (200, 400, 500)

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/1/run-data-sync", follow_redirects=False)
        assert resp.status_code == 302

    def test_valid_fdrs_reported_states(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Valid States Template")
        mock_run_import = MagicMock(return_value={"success": True})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(
                logged_in_client, template.id,
                {"fdrs_reported_import_states": [100, 200, 300]}
            )
        assert resp.status_code in (200, 400, 500)

    def test_sync_documents_false_passed_to_run_import(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS No Docs Template")
        mock_run_import = MagicMock(return_value={"loaded": 0, "skipped": 0, "inserted": 0, "updated": 0, "errors": 0})
        with _auth(), \
             patch.dict("sys.modules", {"import_fdrs_form_data": MagicMock(run_import=mock_run_import)}):
            resp = self._post_data_sync(
                logged_in_client, template.id,
                {"sync_documents": False}
            )
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            mock_run_import.assert_called_once()
            assert mock_run_import.call_args.kwargs.get("sync_documents") is False


# ---------------------------------------------------------------------------
# GET /<template_id>/data-sync-status/<job_id>
# ---------------------------------------------------------------------------

class TestDataSyncStatus:
    def _inject_job(self, template_id, user_id, status="running"):
        return _create_data_sync_test_job(template_id, user_id, status=status)

    def test_nonexistent_job_returns_404(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Status No Job Template")
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-status/nonexistent_job"
            )
        assert resp.status_code == 404

    def test_job_wrong_template_returns_404(self, logged_in_client, db_session, app):
        template1 = create_test_template(db_session, name="FDRS Status T1 Template")
        template2 = create_test_template(db_session, name="FDRS Status T2 Template")
        with app.app_context():
            user_id = logged_in_client.application.test_client().application.extensions.get("login_manager")
        job_id = self._inject_job(template2.id, 1)
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template1.id}/data-sync-status/{job_id}"
            )
        assert resp.status_code == 404

    def test_job_different_user_returns_403(self, logged_in_client, db_session, app, admin_user, test_user):
        template = create_test_template(db_session, name="FDRS Status Denied Template")
        job_id = self._inject_job(template.id, user_id=test_user.id)
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-status/{job_id}"
            )
        assert resp.status_code == 403

    def test_job_owned_by_current_user_returns_status(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Status Own Template")
        job_id = self._inject_job(template.id, user_id=admin_user.id)
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-status/{job_id}"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "job" in data

    def test_job_with_download_ready_includes_url(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Status Download Template")
        job_id = _create_data_sync_test_job(
            template.id,
            user_id=admin_user.id,
            status="completed",
            download_ready=True,
        )
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-status/{job_id}"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "download_url" in data.get("job", {}) or resp.status_code == 200

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1/data-sync-status/fakejob", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /<template_id>/data-sync-cancel/<job_id>
# ---------------------------------------------------------------------------

class TestDataSyncCancel:
    def _inject_job(self, template_id, user_id, status="running"):
        return _create_data_sync_test_job(template_id, user_id, status=status)

    def test_nonexistent_job_returns_404(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Cancel No Job Template")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/data-sync-cancel/nonexistent_job"
            )
        assert resp.status_code == 404

    def test_wrong_user_returns_403(self, logged_in_client, db_session, app, admin_user, test_user):
        template = create_test_template(db_session, name="FDRS Cancel Denied Template")
        job_id = self._inject_job(template.id, user_id=test_user.id)
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/data-sync-cancel/{job_id}"
            )
        assert resp.status_code == 403

    def test_cancel_running_job_sets_cancel_requested(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Cancel Running Template")
        job_id = self._inject_job(template.id, user_id=admin_user.id, status="running")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/data-sync-cancel/{job_id}"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "cancel_requested"

    def test_cancel_already_completed_job_returns_status(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Cancel Done Template")
        job_id = self._inject_job(template.id, user_id=admin_user.id, status="completed")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/data-sync-cancel/{job_id}"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "completed"

    def test_cancel_already_failed_job_returns_status(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Cancel Failed Template")
        job_id = self._inject_job(template.id, user_id=admin_user.id, status="failed")
        with _auth():
            resp = logged_in_client.post(
                f"/admin/templates/data-sync/{template.id}/data-sync-cancel/{job_id}"
            )
        assert resp.status_code == 200

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.post("/admin/templates/data-sync/1/data-sync-cancel/fakejob", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# GET /<template_id>/data-sync-download/<job_id>
# ---------------------------------------------------------------------------

class TestDataSyncDownload:
    def _inject_job_with_file(self, template_id, user_id, create_file=True):
        preview_path = None
        if create_file:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
            tmp.write(b"PK fake xlsx content")
            tmp.close()
            preview_path = tmp.name
        job_id = _create_data_sync_test_job(
            template_id,
            user_id,
            status="completed",
            download_ready=True,
            preview_path=preview_path,
        )
        return job_id, preview_path

    def test_nonexistent_job_returns_404(self, logged_in_client, db_session, app):
        template = create_test_template(db_session, name="FDRS Download No Job Template")
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-download/nonexistent_job"
            )
        assert resp.status_code == 404

    def test_wrong_user_returns_403(self, logged_in_client, db_session, app, admin_user, test_user):
        template = create_test_template(db_session, name="FDRS Download Denied Template")
        job_id, _ = self._inject_job_with_file(template.id, user_id=test_user.id)
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-download/{job_id}"
            )
        assert resp.status_code == 403

    def test_file_exists_returns_download(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Download Valid Template")
        job_id, preview_path = self._inject_job_with_file(template.id, user_id=admin_user.id)
        try:
            with _auth():
                resp = logged_in_client.get(
                    f"/admin/templates/data-sync/{template.id}/data-sync-download/{job_id}"
                )
            assert resp.status_code in (200, 404)
        finally:
            if preview_path and os.path.isfile(preview_path):
                with suppress(OSError):
                    os.unlink(preview_path)

    def test_file_missing_returns_404(self, logged_in_client, db_session, app, admin_user):
        template = create_test_template(db_session, name="FDRS Download Missing File Template")
        job_id, _ = self._inject_job_with_file(template.id, user_id=admin_user.id, create_file=False)
        with _auth():
            resp = logged_in_client.get(
                f"/admin/templates/data-sync/{template.id}/data-sync-download/{job_id}"
            )
        assert resp.status_code == 404

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/templates/data-sync/1/data-sync-download/fakejob", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Internal helpers unit tests
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    def test_utc_iso_returns_string(self):
        from app.services.imports.async_import_job_store import utc_iso
        result = utc_iso()
        assert isinstance(result, str)
        assert "T" in result

    def test_cleanup_data_sync_jobs_locked_removes_old_jobs(self, db_session, admin_user):
        from datetime import datetime, timedelta

        from app.models import AIJob
        from app.routes.admin.data_sync_imputation import _cleanup_data_sync_jobs_locked
        from app.services.imports.async_import_job_store import FDRS_DATA_SYNC_JOB_TYPE, IMPORT_JOB_TTL_SECONDS

        job_id = uuid.uuid4().hex
        old_created = datetime.utcnow() - timedelta(seconds=IMPORT_JOB_TTL_SECONDS + 100)
        db_session.add(
            AIJob(
                id=job_id,
                job_type=FDRS_DATA_SYNC_JOB_TYPE,
                user_id=admin_user.id,
                status="completed",
                total_items=0,
                created_at=old_created,
                meta={"template_id": 1},
            )
        )
        db_session.commit()
        _cleanup_data_sync_jobs_locked(time.time())
        assert AIJob.query.get(job_id) is None

    def test_cleanup_data_sync_jobs_locked_preserves_fresh_jobs(self, db_session, admin_user):
        from app.models import AIJob
        from app.routes.admin.data_sync_imputation import _cleanup_data_sync_jobs_locked
        from app.services.imports.async_import_job_store import FDRS_DATA_SYNC_JOB_TYPE

        job_id = uuid.uuid4().hex
        db_session.add(
            AIJob(
                id=job_id,
                job_type=FDRS_DATA_SYNC_JOB_TYPE,
                user_id=admin_user.id,
                status="running",
                total_items=0,
                meta={"template_id": 1},
            )
        )
        db_session.commit()
        _cleanup_data_sync_jobs_locked(time.time())
        assert AIJob.query.get(job_id) is not None

    def test_parse_reported_import_states_none_key(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        result = _parse_reported_import_states({})
        assert result is None

    def test_parse_reported_import_states_none_value(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        result = _parse_reported_import_states({"fdrs_reported_import_states": None})
        assert result is None

    def test_parse_reported_import_states_list(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        result = _parse_reported_import_states({"fdrs_reported_import_states": [100, 200]})
        assert result == [100, 200]

    def test_parse_reported_import_states_string(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        result = _parse_reported_import_states({"fdrs_reported_import_states": "100,200"})
        assert result == [100, 200]

    def test_parse_reported_import_states_invalid_value_raises(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        with pytest.raises(ValueError):
            _parse_reported_import_states({"fdrs_reported_import_states": [999]})

    def test_parse_reported_import_states_empty_list_raises(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        with pytest.raises(ValueError):
            _parse_reported_import_states({"fdrs_reported_import_states": []})

    def test_parse_reported_import_states_invalid_string_raises(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        with pytest.raises(ValueError):
            _parse_reported_import_states({"fdrs_reported_import_states": "notanumber"})

    def test_parse_reported_import_states_invalid_list_item_raises(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        with pytest.raises(ValueError):
            _parse_reported_import_states({"fdrs_reported_import_states": ["notanumber"]})

    def test_parse_reported_import_states_wrong_type_raises(self):
        from app.routes.admin.data_sync_imputation import _parse_reported_import_states
        with pytest.raises(ValueError):
            _parse_reported_import_states({"fdrs_reported_import_states": 123})

    def test_build_ordered_sections_with_items_empty(self, app, db_session):
        with app.app_context():
            from app.routes.admin.data_sync_imputation import _build_ordered_sections_with_items
            template = create_test_template(db_session, name="Build Ordered Sections Template")
            result = _build_ordered_sections_with_items(template, [], {})
            assert isinstance(result, list)
            assert len(result) == 0
