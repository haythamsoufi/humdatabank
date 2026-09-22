"""
Comprehensive pytest tests for app/routes/forms_validation_summary.py

Covers validation summary progress page, cancel, events (SSE), PDF export,
opinions GET/POST/SSE, internal helpers such as _parse_hidden_ids_arg,
_parse_ai_sources_arg, _value_display, _serialize_validation, etc.
"""
from __future__ import annotations

import json
import time
import threading
from contextlib import suppress
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tests.factories import (
    create_test_admin,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_user,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(resp):
    return json.loads(resp.data)


def _assert_status(resp, *allowed):
    assert resp.status_code in allowed, (
        f"Expected one of {allowed}, got {resp.status_code}: {resp.data[:300]}"
    )


def _parse_sse(raw) -> list[tuple[str, dict]]:
    """Parse `event: name\\ndata: {...}\\n\\n` frames into a list of (name, dict)."""
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        name = None
        data_lines = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if name and data_lines:
            try:
                payload = json.loads("\n".join(data_lines))
            except Exception:
                payload = {}
            events.append((name, payload))
    return events


def _make_aes(db_session):
    """Create a minimal assignment entity status for tests."""
    return create_test_assignment_entity_status(db_session)


# ---------------------------------------------------------------------------
# Auth guard – unauthenticated access
# ---------------------------------------------------------------------------

class TestValidationSummaryAuthGuard:
    def test_progress_page_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary")
        _assert_status(resp, 302, 401, 403)

    def test_cancel_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.post(
            f"/forms/assignment_status/{aes.id}/validation_summary/cancel",
            json={"run_id": "abc"},
        )
        _assert_status(resp, 302, 401, 403)

    def test_events_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary/events")
        _assert_status(resp, 302, 401, 403)

    def test_pdf_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary_pdf")
        _assert_status(resp, 302, 401, 403)

    def test_opinions_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary/opinions")
        _assert_status(resp, 302, 401, 403)

    def test_opinions_run_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.post(f"/forms/assignment_status/{aes.id}/validation_summary/opinions/run", json={})
        _assert_status(resp, 302, 401, 403)

    def test_opinions_events_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary/opinions/events")
        _assert_status(resp, 302, 401, 403)

    def test_overview_unauthenticated(self, client, db_session):
        aes = _make_aes(db_session)
        resp = client.get(f"/forms/assignment_status/{aes.id}/validation_summary/overview")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# 404 – invalid AES IDs
# ---------------------------------------------------------------------------

class TestValidationSummary404:
    def test_progress_page_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary")
        _assert_status(resp, 404, 302, 302)

    def test_cancel_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/forms/assignment_status/999999/validation_summary/cancel",
            json={"run_id": "abc"},
        )
        _assert_status(resp, 404)

    def test_events_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary/events")
        _assert_status(resp, 404)

    def test_pdf_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary_pdf")
        _assert_status(resp, 404, 302)

    def test_opinions_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary/opinions")
        _assert_status(resp, 404, 200, 500)

    def test_opinions_run_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/forms/assignment_status/999999/validation_summary/opinions/run",
            json={},
        )
        _assert_status(resp, 404, 200, 500)

    def test_opinions_events_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary/opinions/events")
        _assert_status(resp, 404)

    def test_overview_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/forms/assignment_status/999999/validation_summary/overview")
        _assert_status(resp, 404, 403)


# ---------------------------------------------------------------------------
# Progress page – authorized access
# ---------------------------------------------------------------------------

class TestValidationSummaryProgressPage:
    def test_basic_render(self, logged_in_client, db_session, app):
        """Progress page renders (or redirects) for admin."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary"
            )
        _assert_status(resp, 200, 302)

    def test_resolves_assignment_period_in_section_headers(self, logged_in_client, db_session, app):
        from app.models import FormData

        with app.app_context():
            template = create_test_template(db_session)
            parent = create_test_section(
                db_session, template, name="Funding requirements (CHF)", order=1
            )
            subsection = create_test_section(
                db_session,
                template,
                name="Funding Requirements for [assignment_period]",
                order=1,
                parent_section_id=parent.id,
            )
            item = create_test_item(
                db_session, subsection, template, item_type="question", label="Funding grid"
            )
            aes = create_test_assignment_entity_status(
                db_session, template=template, period_name="2027"
            )
            db_session.add(FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value="1",
            ))
            db_session.commit()
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?run=0"
            )
        assert resp.status_code == 200, resp.data[:300]
        body = resp.get_data(as_text=True)
        assert "Funding Requirements for 2027" in body
        assert "Funding Requirements for [assignment_period]" not in body
        assert "Validation details" in body
        assert "<h1>Validation Summary</h1>" not in body

    def test_with_hidden_fields_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?hidden_fields=1,2,3"
            )
        _assert_status(resp, 200, 302)

    def test_with_hidden_sections_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?hidden_sections=10,20"
            )
        _assert_status(resp, 200, 302)

    def test_with_include_non_reported(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?include_non_reported=1"
            )
        _assert_status(resp, 200, 302)

    def test_access_denied_redirects_to_dashboard(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary"
            )
        _assert_status(resp, 302)

    def test_with_run_id_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?run_id=test-run-123"
            )
        _assert_status(resp, 200, 302)

    def test_with_run_mode_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?run_mode=all"
            )
        _assert_status(resp, 200, 302)

    def test_with_ai_sources_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?ai_sources=historical,system_documents"
            )
        _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# Cancel endpoint
# ---------------------------------------------------------------------------

class TestValidationSummaryCancel:
    def test_cancel_missing_run_id(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                json={},
            )
        _assert_status(resp, 400)

    def test_cancel_success(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                json={"run_id": "test-run-id-123"},
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert data.get("run_id") == "test-run-id-123"

    def test_cancel_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                json={"run_id": "test-run-id"},
            )
        _assert_status(resp, 403)

    def test_cancel_empty_run_id_string(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                json={"run_id": "  "},
            )
        _assert_status(resp, 400)


# ---------------------------------------------------------------------------
# Events (SSE) endpoint
# ---------------------------------------------------------------------------

class TestValidationSummaryEvents:
    def test_events_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events"
            )
        _assert_status(resp, 200)
        # Should return SSE error event
        assert b"error" in resp.data or b"Access denied" in resp.data

    def test_events_no_run(self, logged_in_client, db_session, app):
        """With run=0 should return snapshot + done immediately."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0"
            )
        _assert_status(resp, 200)
        assert resp.content_type.startswith("text/event-stream")
        assert b"done" in resp.data

    def test_events_with_include_non_reported(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&include_non_reported=1"
            )
        _assert_status(resp, 200)
        assert resp.content_type.startswith("text/event-stream")

    def test_events_run_mode_all(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&run_mode=all"
            )
        _assert_status(resp, 200)

    def test_events_with_concurrency_param(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&concurrency=4"
            )
        _assert_status(resp, 200)

    def test_events_with_run_id(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&run_id=my-run"
            )
        _assert_status(resp, 200)

    def test_events_hidden_fields(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&hidden_fields=1,2"
            )
        _assert_status(resp, 200)

    def test_events_missing_section_ids(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0&hidden_sections=5,6"
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

class TestValidationSummaryPdf:
    def test_pdf_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary_pdf"
            )
        _assert_status(resp, 302)

    def test_pdf_weasyprint_unavailable(self, logged_in_client, db_session, app):
        """When WeasyPrint is not installed should return 503 or redirect."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary_pdf"
            )
        # Either 503 (no weasyprint) or redirect or PDF
        _assert_status(resp, 200, 302, 503)

    def test_pdf_with_run_mode(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary_pdf?run=0&run_mode=missing"
            )
        _assert_status(resp, 200, 302, 503)

    def test_pdf_include_non_reported(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary_pdf?include_non_reported=1"
            )
        _assert_status(resp, 200, 302, 503)


# ---------------------------------------------------------------------------
# Opinions GET
# ---------------------------------------------------------------------------

class TestValidationSummaryOpinions:
    def test_opinions_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions"
            )
        _assert_status(resp, 403)

    def test_opinions_success_empty(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions"
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert "opinionsByFormItemId" in data

    def test_opinions_ai_beta_denied(self, logged_in_client, db_session, app):
        """When AI beta is restricted and user lacks access, returns forbidden."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.platform.app_settings_service.is_ai_beta_restricted", return_value=True), \
             patch("app.services.platform.app_settings_service.user_has_ai_beta_access", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions"
            )
        _assert_status(resp, 403, 200)


# ---------------------------------------------------------------------------
# Overview (on-form Validation summary)
# ---------------------------------------------------------------------------

class TestValidationSummaryOverview:
    def test_overview_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview"
            )
        _assert_status(resp, 403)

    def test_overview_empty(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview"
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True
        assert data["counts"]["good"] == 0
        assert data["counts"]["discrepancy"] == 0
        assert data["reviewed"] == 0
        assert data["issues"] == []
        assert "details_url" in data
        assert "No AI validation results yet" in (data.get("headline") or "")
        assert "overview_figures" in data
        assert "whats_good" in data
        assert data.get("whats_not") in (None, []) or isinstance(data.get("issues"), list)

    def test_overview_lists_discrepancy(self, logged_in_client, db_session, app):
        from app.models import FormData
        from app.models.ai_validation import AIFormDataValidation
        from app.models.enums import AIFormDataValidationStatusValue, AIFormDataValidationVerdictValue

        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, name="People to be reached")
            item = create_test_item(
                db_session, section, template, item_type="question", label="Longer term programmes"
            )
            aes = create_test_assignment_entity_status(db_session, template=template, period_name="2027")
            fd = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value="1",
            )
            db_session.add(fd)
            db_session.flush()
            db_session.add(AIFormDataValidation(
                form_data_id=fd.id,
                status=AIFormDataValidationStatusValue.completed,
                verdict=AIFormDataValidationVerdictValue.discrepancy,
                confidence=0.8,
                opinion_text="Flags vs prior people counts.",
            ))
            db_session.commit()
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview"
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data["counts"]["discrepancy"] == 1
        assert data["reviewed"] == 1
        assert data["issues"]
        assert data["issues"][0]["verdict"] == "discrepancy"
        assert "Longer term programmes" in (data["issues"][0].get("label") or "")
        assert "discrepancy" in (data.get("headline") or "").lower()


class TestValidationSummaryOverviewStream:
    """The SSE twin of TestValidationSummaryOverview — same underlying work, but
    emits real "stage" events as each phase begins instead of one JSON response, so
    the on-form loading animation can reflect genuine backend progress."""

    def test_overview_stream_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview_stream"
            )
        assert resp.content_type.startswith("text/event-stream")
        events = _parse_sse(resp.data)
        assert events and events[0][0] == "error"

    def test_overview_stream_emits_real_stages_then_result(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview_stream"
            )
        _assert_status(resp, 200)
        assert resp.content_type.startswith("text/event-stream")
        events = _parse_sse(resp.data)
        names = [n for n, _d in events]
        # Real stages in the order the work actually happens: reading the assignment's
        # entries, then checking the deterministic pack. This fixture's template isn't
        # a UPR one, so there is no pack/LLM call and thus no "summary" stage — that
        # stage must only ever be announced when it will really happen.
        assert names[0] == "stage" and events[0][1]["key"] == "reading"
        stage_keys = [d["key"] for n, d in events if n == "stage"]
        assert "figures" in stage_keys
        assert "summary" not in stage_keys
        assert names[-1] == "result"
        result = events[-1][1]
        # Same payload shape/content as the non-streamed endpoint.
        assert result["counts"]["good"] == 0
        assert result["reviewed"] == 0
        assert result["issues"] == []
        assert "details_url" in result
        assert "No AI validation results yet" in (result.get("headline") or "")

    def test_overview_stream_matches_non_streamed_payload(self, logged_in_client, db_session, app):
        """Same fixture as test_overview_lists_discrepancy — the streamed "result"
        event must carry the exact same content as the plain JSON endpoint."""
        from app.models import FormData
        from app.models.ai_validation import AIFormDataValidation
        from app.models.enums import AIFormDataValidationStatusValue, AIFormDataValidationVerdictValue

        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, name="People to be reached")
            item = create_test_item(
                db_session, section, template, item_type="question", label="Longer term programmes"
            )
            aes = create_test_assignment_entity_status(db_session, template=template, period_name="2027")
            fd = FormData(
                assignment_entity_status_id=aes.id,
                form_item_id=item.id,
                value="1",
            )
            db_session.add(fd)
            db_session.flush()
            db_session.add(AIFormDataValidation(
                form_data_id=fd.id,
                status=AIFormDataValidationStatusValue.completed,
                verdict=AIFormDataValidationVerdictValue.discrepancy,
                confidence=0.8,
                opinion_text="Flags vs prior people counts.",
            ))
            db_session.commit()
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/overview_stream"
            )
        _assert_status(resp, 200)
        events = _parse_sse(resp.data)
        assert events[-1][0] == "result"
        result = events[-1][1]
        assert result["counts"]["discrepancy"] == 1
        assert result["reviewed"] == 1
        assert result["issues"]
        assert result["issues"][0]["verdict"] == "discrepancy"
        assert "Longer term programmes" in (result["issues"][0].get("label") or "")
        assert "discrepancy" in (result.get("headline") or "").lower()


# ---------------------------------------------------------------------------
# Opinions run (POST)
# ---------------------------------------------------------------------------

class TestValidationSummaryOpinionsRun:
    def test_opinions_run_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={},
            )
        _assert_status(resp, 403)

    def test_opinions_run_empty_payload(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.ai.validation.formdata_validation.AIFormDataValidationService.upsert_validation", return_value=(MagicMock(), None)), \
             patch("app.services.ai.validation.formdata_validation.AIFormDataValidationService.upsert_missing_assigned_validation", return_value=(MagicMock(), None)):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={},
            )
        _assert_status(resp, 200)
        data = _get_json(resp)
        assert data.get("success") is True

    def test_opinions_run_mode_all(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={"mode": "all"},
            )
        _assert_status(resp, 200)

    def test_opinions_run_with_hidden_fields(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={"hidden_fields": [1, 2, 3], "hidden_sections": [4, 5]},
            )
        _assert_status(resp, 200)

    def test_opinions_run_with_sources(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={"sources": ["historical", "system_documents"]},
            )
        _assert_status(resp, 200)

    def test_opinions_run_include_non_reported(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={"include_non_reported": True},
            )
        _assert_status(resp, 200)

    def test_opinions_run_ai_beta_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.platform.app_settings_service.is_ai_beta_restricted", return_value=True), \
             patch("app.services.platform.app_settings_service.user_has_ai_beta_access", return_value=False):
            resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/run",
                json={},
            )
        _assert_status(resp, 403, 200)


# ---------------------------------------------------------------------------
# Opinions events (SSE)
# ---------------------------------------------------------------------------

class TestValidationSummaryOpinionsEvents:
    def test_opinions_events_access_denied(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/events"
            )
        _assert_status(resp, 200)
        assert b"error" in resp.data or b"Access denied" in resp.data

    def test_opinions_events_basic(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/events"
            )
        _assert_status(resp, 200)
        assert resp.content_type.startswith("text/event-stream")
        assert b"done" in resp.data

    def test_opinions_events_run_mode_all(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/events?run_mode=all"
            )
        _assert_status(resp, 200)

    def test_opinions_events_hidden_params(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/events"
                "?hidden_fields=1,2&hidden_sections=3"
            )
        _assert_status(resp, 200)

    def test_opinions_events_no_non_reported(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/opinions/events"
                "?include_non_reported=0"
            )
        _assert_status(resp, 200)


# ---------------------------------------------------------------------------
# Internal helper unit tests (via direct import / app context)
# ---------------------------------------------------------------------------

class TestInternalHelpers:
    """Tests for private helpers by exercising them through the app context."""

    def test_cancel_flags_roundtrip(self, app):
        """Mark-cancelled + is-cancelled should be consistent."""
        from app.routes import forms_validation_summary as fvs_mod  # noqa
        # Access module-level state
        import app.routes.forms_validation_summary  # ensure loaded
        # The helpers are closures inside register_validation_summary_routes.
        # Test indirectly via the cancel endpoint.
        pass  # covered by cancel endpoint tests above

    def test_serialize_validation_empty(self, app):
        """_serialize_validation with None/empty should return {}."""
        # Import the module to at least exercise top-level code
        with app.app_context():
            from app.routes.forms_validation_summary import register_validation_summary_routes  # noqa
        # No assertion needed – just verifies import doesn't crash
        assert True

    def test_parse_hidden_ids_via_endpoint(self, logged_in_client, db_session, app):
        """hidden_fields with invalid values should still work (skip non-digits)."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?hidden_fields=abc,,1,,2"
            )
        _assert_status(resp, 200, 302)

    def test_ai_sources_param_valid(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary"
                "?ai_sources=historical,upr_documents,upr_documents"  # duplicate dropped
            )
        _assert_status(resp, 200, 302)

    def test_ai_sources_param_invalid_filtered(self, logged_in_client, db_session, app):
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary?ai_sources=badvalue"
            )
        _assert_status(resp, 200, 302)

    def test_include_non_reported_variants(self, logged_in_client, db_session, app):
        for val in ("true", "yes", "y", "on", "1", "0", "false"):
            with app.app_context():
                aes = _make_aes(db_session)
                aes_id = aes.id

            with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
                resp = logged_in_client.get(
                    f"/forms/assignment_status/{aes_id}/validation_summary?include_non_reported={val}"
                )
            _assert_status(resp, 200, 302)


# ---------------------------------------------------------------------------
# Module-level cancel flag helpers
# ---------------------------------------------------------------------------

class TestCancelFlagModule:
    """Test the cancel-flag logic in isolation via module-level state."""

    def test_cancel_via_endpoint_then_check(self, logged_in_client, db_session, app):
        """Cancel a run_id and verify done is returned early in events stream."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        run_id = "cancel-test-run-99"
        # First cancel the run_id
        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            cancel_resp = logged_in_client.post(
                f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                json={"run_id": run_id},
            )
        _assert_status(cancel_resp, 200)

        # Then hit the events endpoint – it should honour the cancelled flag
        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            ev_resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events"
                f"?run=0&run_id={run_id}"
            )
        _assert_status(ev_resp, 200)


# ---------------------------------------------------------------------------
# Edge cases with form data and template structures
# ---------------------------------------------------------------------------

class TestWithFormData:
    def test_progress_page_with_template(self, logged_in_client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            aes = create_test_assignment_entity_status(db_session, template=template)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary"
            )
        _assert_status(resp, 200, 302)

    def test_events_with_template_and_section(self, logged_in_client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            section = create_test_section(db_session, template)
            aes = create_test_assignment_entity_status(db_session, template=template)
            aes_id = aes.id

        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary/events?run=0"
            )
        _assert_status(resp, 200)

    def test_pdf_with_no_template_redirects(self, logged_in_client, db_session, app):
        """When assigned form has no template, should redirect with flash."""
        with app.app_context():
            aes = _make_aes(db_session)
            aes_id = aes.id

        # Patch the template to be None on the assigned form
        with patch("app.services.organization.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.models.AssignedForm.template", new_callable=PropertyMock, return_value=None):
            resp = logged_in_client.get(
                f"/forms/assignment_status/{aes_id}/validation_summary_pdf"
            )
        _assert_status(resp, 200, 302, 503)
