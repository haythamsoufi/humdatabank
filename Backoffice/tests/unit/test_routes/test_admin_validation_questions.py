"""Tests for app/routes/admin/validation_questions.py."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _mock_render(text="ok"):
    from flask import make_response
    return make_response(text, 200)


def _perm_patch():
    return patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True)


def _make_question(id=1, status="open", severity="medium"):
    q = MagicMock()
    q.id = id
    q.status = status
    q.severity = severity
    q.question_text = "Is the data correct?"
    q.definition_text = "Check the value"
    q.answer_text = None
    q.answer_outcome = None
    q.answered_at = None
    q.changes_made_approved_at = None
    q.no_changes_approved_at = None
    q.answered_by_user_id = None
    q.parent_question_id = None
    q.follow_up_round = 0
    return q


# ---------------------------------------------------------------------------
# validation_questions_admin GET
# ---------------------------------------------------------------------------


class TestValidationQuestionsAdmin:
    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/validation-questions")
        assert resp.status_code in (301, 302, 308)

    def test_renders_for_permitted_user(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.template_options", return_value=[]), \
             patch("app.routes.admin.validation_questions.render_template", return_value=_mock_render("vq")):
            resp = logged_in_client.get("/admin/validation-questions")
        assert resp.status_code == 200

    def test_denied_without_permission(self, logged_in_client, db_session, app):
        with patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=False):
            resp = logged_in_client.get("/admin/validation-questions")
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# validation_questions_periods_api
# ---------------------------------------------------------------------------


class TestValidationQuestionsPeriods:
    def test_missing_template_id_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-questions/api/periods")
        assert resp.status_code == 400

    def test_returns_periods(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.global_periods_for_template", return_value=["2025", "2024"]):
            resp = logged_in_client.get("/admin/validation-questions/api/periods?template_id=1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["periods"] == ["2025", "2024"]


# ---------------------------------------------------------------------------
# validation_questions_countries_api
# ---------------------------------------------------------------------------


class TestValidationQuestionsCountries:
    def test_missing_params_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-questions/api/countries")
        assert resp.status_code == 400

    def test_missing_period_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch():
            resp = logged_in_client.get("/admin/validation-questions/api/countries?template_id=1")
        assert resp.status_code == 400

    def test_returns_countries(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.list_countries_for_period", return_value=[{"id": 1}]):
            resp = logged_in_client.get("/admin/validation-questions/api/countries?template_id=1&period=2024")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "countries" in data


# ---------------------------------------------------------------------------
# validation_questions_list_api
# ---------------------------------------------------------------------------


class TestValidationQuestionsListApi:
    def test_no_params_returns_all(self, logged_in_client, db_session, app):
        q = _make_question()
        mock_row = {"id": 1, "status": "open"}

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.query_validation_questions", return_value=[q]), \
             patch("app.routes.admin.validation_questions.Country") as mock_c, \
             patch("app.routes.admin.validation_questions.FormTemplate") as mock_ft, \
             patch("app.routes.admin.validation_questions.parent_ids_with_open_follow_up", return_value=set()), \
             patch("app.routes.admin.validation_questions.form_item_labels_for_questions", return_value={}), \
             patch("app.routes.admin.validation_questions.serialize_validation_question_grid_row", return_value=mock_row):
            mock_c.query.all.return_value = []
            mock_ft.query.all.return_value = []
            resp = logged_in_client.get("/admin/validation-questions/api/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rows" in data
        assert "truncated" in data

    def test_truncation_at_500(self, logged_in_client, db_session, app):
        # Return 501 questions so truncation kicks in
        questions = [_make_question(id=i) for i in range(501)]
        mock_row = {"id": 0}

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.query_validation_questions", return_value=questions), \
             patch("app.routes.admin.validation_questions.Country") as mock_c, \
             patch("app.routes.admin.validation_questions.FormTemplate") as mock_ft, \
             patch("app.routes.admin.validation_questions.parent_ids_with_open_follow_up", return_value=set()), \
             patch("app.routes.admin.validation_questions.form_item_labels_for_questions", return_value={}), \
             patch("app.routes.admin.validation_questions.serialize_validation_question_grid_row", return_value=mock_row):
            mock_c.query.all.return_value = []
            mock_ft.query.all.return_value = []
            resp = logged_in_client.get("/admin/validation-questions/api/list")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["truncated"] is True
        assert len(data["rows"]) == 500

    def test_with_filter_params(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.query_validation_questions", return_value=[]) as mock_qvq, \
             patch("app.routes.admin.validation_questions.Country") as mock_c, \
             patch("app.routes.admin.validation_questions.FormTemplate") as mock_ft, \
             patch("app.routes.admin.validation_questions.parent_ids_with_open_follow_up", return_value=set()), \
             patch("app.routes.admin.validation_questions.form_item_labels_for_questions", return_value={}):
            mock_c.query.all.return_value = []
            mock_ft.query.all.return_value = []
            resp = logged_in_client.get(
                "/admin/validation-questions/api/list?template_id=1&period=2024&status=open&country_id=5"
            )
        assert resp.status_code == 200
        # Verify filters were passed to query function
        call_kwargs = mock_qvq.call_args[1]
        assert call_kwargs["template_id"] == 1
        assert call_kwargs["period"] == "2024"
        assert call_kwargs["status"] == "open"
        assert call_kwargs["country_id"] == 5

    def test_cache_control_header_set(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.query_validation_questions", return_value=[]), \
             patch("app.routes.admin.validation_questions.Country") as mock_c, \
             patch("app.routes.admin.validation_questions.FormTemplate") as mock_ft, \
             patch("app.routes.admin.validation_questions.parent_ids_with_open_follow_up", return_value=set()), \
             patch("app.routes.admin.validation_questions.form_item_labels_for_questions", return_value={}):
            mock_c.query.all.return_value = []
            mock_ft.query.all.return_value = []
            resp = logged_in_client.get("/admin/validation-questions/api/list")
        assert "no-store" in resp.headers.get("Cache-Control", "")


# ---------------------------------------------------------------------------
# validation_questions_create_follow_up
# ---------------------------------------------------------------------------


class TestCreateFollowUp:
    def _post(self, logged_in_client, question_id, data):
        return logged_in_client.post(
            f"/admin/validation-questions/api/{question_id}/follow-up",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_success(self, logged_in_client, db_session, app):
        parent = _make_question(id=1)
        follow_up = _make_question(id=2)
        follow_up.parent_question_id = 1
        follow_up.follow_up_round = 1

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.create_follow_up", return_value=follow_up), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None):
            mock_vq.query.get_or_404.return_value = parent
            resp = self._post(logged_in_client, 1, {
                "question_text": "Follow up?", "definition_text": "Check again", "severity": "high"
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 2

    def test_value_error_returns_400(self, logged_in_client, db_session, app):
        parent = _make_question()

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.create_follow_up", side_effect=ValueError("already has open")), \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None):
            mock_vq.query.get_or_404.return_value = parent
            resp = self._post(logged_in_client, 1, {"question_text": "?"})
        assert resp.status_code == 400

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        parent = _make_question()

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.create_follow_up", side_effect=RuntimeError("crash")), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None):
            mock_vq.query.get_or_404.return_value = parent
            resp = self._post(logged_in_client, 1, {"question_text": "?"})
        assert resp.status_code == 500

    def test_csrf_error_returns_403(self, logged_in_client, db_session, app):
        from flask import make_response
        csrf_resp = make_response('{"error": "csrf"}', 403)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(logged_in_client, 1, {})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# validation_questions_update
# ---------------------------------------------------------------------------


class TestValidationQuestionsUpdate:
    def _post(self, logged_in_client, question_id, data):
        return logged_in_client.post(
            f"/admin/validation-questions/api/{question_id}",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_success(self, logged_in_client, db_session, app):
        question = _make_question(id=5)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.apply_manual_question_update"), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 5, {
                "question_text": "Updated?", "status": "answered", "answer_text": "Yes"
            })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 5

    def test_value_error_returns_400(self, logged_in_client, db_session, app):
        question = _make_question(id=5)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.apply_manual_question_update", side_effect=ValueError("bad val")), \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 5, {"question_text": "?"})
        assert resp.status_code == 400

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        question = _make_question(id=5)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.apply_manual_question_update", side_effect=RuntimeError("db")), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 5, {"question_text": "?"})
        assert resp.status_code == 500

    def test_with_timestamps(self, logged_in_client, db_session, app):
        """Test response when question has timestamps set."""
        from datetime import datetime
        question = _make_question(id=7)
        question.answered_at = datetime(2024, 1, 15, 10, 30)
        question.changes_made_approved_at = datetime(2024, 1, 16, 9, 0)
        question.no_changes_approved_at = None

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.apply_manual_question_update"), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 7, {"question_text": "?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["answered_at"] is not None
        assert data["changes_made_approved_at"] is not None
        assert data["no_changes_approved_at"] is None


# ---------------------------------------------------------------------------
# validation_questions_update_status
# ---------------------------------------------------------------------------


class TestValidationQuestionsUpdateStatus:
    def _post(self, logged_in_client, question_id, data):
        return logged_in_client.post(
            f"/admin/validation-questions/api/{question_id}/status",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_invalid_status_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None):
            resp = self._post(logged_in_client, 1, {"status": "invalid_status"})
        assert resp.status_code == 400

    def test_answered_without_answer_text_returns_400(self, logged_in_client, db_session, app):
        question = _make_question(id=1)
        question.answer_text = None

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None):
            mock_vq.query.get_or_404.return_value = question
            resp = self._post(logged_in_client, 1, {"status": "answered", "answer_text": ""})
        assert resp.status_code == 400

    def test_answered_with_answer_text_succeeds(self, logged_in_client, db_session, app):
        question = _make_question(id=1)
        question.answered_at = None

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.mark_answer_received"), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 1, {"status": "answered", "answer_text": "Confirmed data"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1

    def test_answered_already_answered_updates_user(self, logged_in_client, db_session, app):
        from datetime import datetime
        question = _make_question(id=1)
        question.answered_at = datetime(2024, 1, 1)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 42
            resp = self._post(logged_in_client, 1, {"status": "answered", "answer_text": "Still correct"})
        assert resp.status_code == 200
        assert question.answered_by_user_id == 42

    def test_open_clears_answer(self, logged_in_client, db_session, app):
        question = _make_question(id=1, status="answered")

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.clear_answer_received") as mock_car, \
             patch("app.routes.admin.validation_questions.clear_review_state") as mock_crs, \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 1, {"status": "open"})
        assert resp.status_code == 200
        assert question.answer_text is None
        mock_car.assert_called_once()
        mock_crs.assert_called_once()

    def test_waived_clears_review_state(self, logged_in_client, db_session, app):
        question = _make_question(id=1)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.clear_review_state") as mock_crs, \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 1, {"status": "waived"})
        assert resp.status_code == 200
        mock_crs.assert_called_once()

    def test_resolved_status(self, logged_in_client, db_session, app):
        question = _make_question(id=1)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.ValidationQuestion") as mock_vq, \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_vq.query.get_or_404.return_value = question
            cu.id = 1
            resp = self._post(logged_in_client, 1, {"status": "resolved"})
        assert resp.status_code == 200
        assert question.status == "resolved"

    def test_csrf_error(self, logged_in_client, db_session, app):
        from flask import make_response
        csrf_resp = make_response('{"error": "csrf"}', 403)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(logged_in_client, 1, {"status": "open"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# validation_questions_export
# ---------------------------------------------------------------------------


class TestValidationQuestionsExport:
    def test_exports_xlsx(self, logged_in_client, db_session, app):
        fake_buf = io.BytesIO(b"PK fake xlsx content")
        fake_buf.seek(0)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.export_questions_workbook", return_value=fake_buf), \
             patch("app.routes.admin.validation_questions.export_filename", return_value="questions_export.xlsx"):
            resp = logged_in_client.get("/admin/validation-questions/export")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/validation-questions/export")
        assert resp.status_code in (301, 302, 308)

    def test_with_filter_params(self, logged_in_client, db_session, app):
        fake_buf = io.BytesIO(b"PK data")
        fake_buf.seek(0)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.export_questions_workbook", return_value=fake_buf) as mock_eq, \
             patch("app.routes.admin.validation_questions.export_filename", return_value="filtered.xlsx"):
            resp = logged_in_client.get(
                "/admin/validation-questions/export?template_id=1&period=2024&status=open&country_id=5"
            )
        assert resp.status_code == 200
        call_kwargs = mock_eq.call_args[1]
        assert call_kwargs["template_id"] == 1
        assert call_kwargs["period"] == "2024"
        assert call_kwargs["status"] == "open"
        assert call_kwargs["country_id"] == 5


# ---------------------------------------------------------------------------
# validation_questions_import_template
# ---------------------------------------------------------------------------


class TestValidationQuestionsImportTemplate:
    def test_downloads_xlsx_template(self, logged_in_client, db_session, app):
        fake_buf = io.BytesIO(b"PK template xlsx")
        fake_buf.seek(0)

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.build_import_template_workbook", return_value=fake_buf):
            resp = logged_in_client.get("/admin/validation-questions/import-template")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.content_type
        assert "attachment" in resp.headers.get("Content-Disposition", "")

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/validation-questions/import-template")
        assert resp.status_code in (301, 302, 308)


# ---------------------------------------------------------------------------
# validation_questions_import
# ---------------------------------------------------------------------------


class TestValidationQuestionsImport:
    def test_csrf_validation_failure_returns_400(self, logged_in_client, db_session, app):
        """When CSRF form validation fails, returns 400."""
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = False
            mock_form_class.return_value = mock_form
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data={},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_no_file_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data={},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_empty_filename_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            data = {"excel_file": (io.BytesIO(b""), "")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_invalid_file_type_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class, \
             patch("app.routes.admin.validation_questions.validate_upload_extension_and_mime", return_value=(False, "Invalid file type", None)):
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            data = {"excel_file": (io.BytesIO(b"not excel"), "malware.exe")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_success(self, logged_in_client, db_session, app):
        mock_result = MagicMock()
        mock_result.updated = 5
        mock_result.skipped = 1
        mock_result.errors = []

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class, \
             patch("app.routes.admin.validation_questions.validate_upload_extension_and_mime", return_value=(True, None, ".xlsx")), \
             patch("app.routes.admin.validation_questions.import_question_updates", return_value=mock_result), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            cu.id = 1
            data = {"excel_file": (io.BytesIO(b"PK valid xlsx"), "questions.xlsx")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        resp_data = resp.get_json()
        assert resp_data["updated"] == 5
        assert resp_data["skipped"] == 1
        assert resp_data["has_errors"] is False

    def test_value_error_returns_400(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class, \
             patch("app.routes.admin.validation_questions.validate_upload_extension_and_mime", return_value=(True, None, ".xlsx")), \
             patch("app.routes.admin.validation_questions.import_question_updates", side_effect=ValueError("bad format")), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            cu.id = 1
            data = {"excel_file": (io.BytesIO(b"PK bad"), "questions.xlsx")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_exception_returns_500(self, logged_in_client, db_session, app):
        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class, \
             patch("app.routes.admin.validation_questions.validate_upload_extension_and_mime", return_value=(True, None, ".xlsx")), \
             patch("app.routes.admin.validation_questions.import_question_updates", side_effect=RuntimeError("crash")), \
             patch("app.routes.admin.validation_questions.db") as mock_db, \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            cu.id = 1
            data = {"excel_file": (io.BytesIO(b"PK bad"), "questions.xlsx")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 500

    def test_success_with_errors_has_errors_true(self, logged_in_client, db_session, app):
        mock_result = MagicMock()
        mock_result.updated = 3
        mock_result.skipped = 2
        mock_result.errors = ["Row 5: invalid status"]

        with _perm_patch(), \
             patch("app.routes.admin.validation_questions.FlaskForm") as mock_form_class, \
             patch("app.routes.admin.validation_questions.validate_upload_extension_and_mime", return_value=(True, None, ".xlsx")), \
             patch("app.routes.admin.validation_questions.import_question_updates", return_value=mock_result), \
             patch("app.routes.admin.validation_questions.current_user") as cu:
            mock_form = MagicMock()
            mock_form.validate_on_submit.return_value = True
            mock_form_class.return_value = mock_form
            cu.id = 1
            data = {"excel_file": (io.BytesIO(b"PK xlsx"), "questions.xlsx")}
            resp = logged_in_client.post(
                "/admin/validation-questions/import",
                data=data,
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200
        resp_data = resp.get_json()
        assert resp_data["has_errors"] is True
        assert "Row 5" in resp_data["errors"][0]
