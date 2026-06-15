"""
Tests for app/routes/api/indicators.py

Coverage targets:
- GET  /api/v1/indicator-bank                          (public, filters, exception)
- GET  /api/v1/indicator-bank/<id>                     (public, 404, exception)
- POST /api/v1/indicator-suggestions                   (require_api_key, validation, sector, subsector, email, exception)
- GET  /api/v1/indicator-suggestions                   (require_api_key, filters, pagination)
- GET  /api/v1/indicator-suggestions/<id>              (require_api_key, 404)
- PUT  /api/v1/indicator-suggestions/<id>/status       (require_api_key, admin check, validation, update)
- GET  /api/v1/sectors                                 (require_api_key, empty, with data)
- GET  /api/v1/subsectors                              (require_api_key, empty, with data)
- GET  /api/v1/sectors-subsectors                      (require_api_key, empty, with data)
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models import IndicatorBank, IndicatorSuggestion, Sector, SubSector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _make_indicator(db_session, name="Test Indicator", is_archived=False):
    ind = IndicatorBank(
        name=name,
        type="number",
        definition="A test indicator",
        archived=is_archived,
    )
    db_session.add(ind)
    db_session.flush()
    return ind


def _make_sector(db_session, name="Health", is_active=True):
    s = Sector(name=name, is_active=is_active, display_order=1)
    db_session.add(s)
    db_session.flush()
    return s


def _make_subsector(db_session, sector_id, name="Primary Health", is_active=True):
    ss = SubSector(name=name, sector_id=sector_id, is_active=is_active, display_order=1)
    db_session.add(ss)
    db_session.flush()
    return ss


_SUGGESTION_PAYLOAD = {
    "submitter_name": "Alice",
    "submitter_email": "alice@example.com",
    "suggestion_type": "new_indicator",
    "indicator_name": "New Indicator",
    "reason": "It is needed",
}


# ---------------------------------------------------------------------------
# GET /api/v1/indicator-bank
# ---------------------------------------------------------------------------

class TestGetIndicatorBank:
    """Tests for GET /api/v1/indicator-bank (public, no API key required)."""

    def test_returns_200_no_auth(self, client, db_session):
        """Endpoint is public — no auth needed."""
        resp = client.get(_api("/indicator-bank"))
        assert resp.status_code == 200

    def test_empty_db_returns_empty_list(self, client, db_session):
        resp = client.get(_api("/indicator-bank"))
        data = resp.get_json()
        assert "indicators" in data
        assert isinstance(data["indicators"], list)

    def test_returns_indicators(self, client, db_session, app):
        with app.app_context():
            _make_indicator(db_session, name="Active Indicator")
            db_session.commit()

        resp = client.get(_api("/indicator-bank"))
        data = resp.get_json()
        assert len(data["indicators"]) >= 1

    def test_search_filter(self, client, db_session, app):
        with app.app_context():
            _make_indicator(db_session, name="UniqueSearchTerm9999")
            db_session.commit()

        resp = client.get(_api("/indicator-bank?search=UniqueSearchTerm9999"))
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, db_session):
        with patch("app.routes.api.indicators.get_indicator_list", side_effect=Exception("crash")):
            resp = client.get(_api("/indicator-bank"))
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/indicator-bank/<id>
# ---------------------------------------------------------------------------

class TestGetIndicatorBankDetails:
    """Tests for GET /api/v1/indicator-bank/<indicator_id>."""

    def test_not_found_returns_404(self, client, db_session):
        resp = client.get(_api("/indicator-bank/999999"))
        assert resp.status_code == 404

    def test_found_returns_indicator(self, client, db_session, app):
        with app.app_context():
            ind = _make_indicator(db_session, name="Detail Indicator")
            db_session.commit()
            ind_id = ind.id

        resp = client.get(_api(f"/indicator-bank/{ind_id}"))
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, db_session, app):
        with app.app_context():
            ind = _make_indicator(db_session, name="Exc Indicator")
            db_session.commit()
            ind_id = ind.id

        with patch("app.routes.api.indicators.serialize_indicator_list", side_effect=Exception("crash")):
            resp = client.get(_api(f"/indicator-bank/{ind_id}"))
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# POST /api/v1/indicator-suggestions
# ---------------------------------------------------------------------------

class TestSubmitIndicatorSuggestion:
    """Tests for POST /api/v1/indicator-suggestions."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.post(_api("/indicator-suggestions"), json=_SUGGESTION_PAYLOAD)
        assert resp.status_code == 401

    def test_missing_required_fields_returns_400(self, client, auth_headers, db_session):
        resp = client.post(
            _api("/indicator-suggestions"),
            json={"submitter_name": "Bob"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_empty_required_field_returns_400(self, client, auth_headers, db_session):
        """Empty string in a required field is caught by the explicit check."""
        payload = {**_SUGGESTION_PAYLOAD, "indicator_name": ""}
        resp = client.post(
            _api("/indicator-suggestions"),
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_valid_payload_creates_suggestion(self, client, auth_headers, db_session, app):
        with patch("app.services.email.service.send_suggestion_confirmation_email"), \
             patch("app.services.email.service.send_admin_notification_email"):
            resp = client.post(
                _api("/indicator-suggestions"),
                json=_SUGGESTION_PAYLOAD,
                headers=auth_headers,
            )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "suggestion_id" in data

    def test_sector_dict_with_primary_stored(self, client, auth_headers, db_session, app):
        payload = {
            **_SUGGESTION_PAYLOAD,
            "sector": {"primary": "Health", "secondary": None, "tertiary": None},
        }
        with patch("app.services.email.service.send_suggestion_confirmation_email"), \
             patch("app.services.email.service.send_admin_notification_email"):
            resp = client.post(
                _api("/indicator-suggestions"),
                json=payload,
                headers=auth_headers,
            )
        assert resp.status_code == 201

    def test_sector_dict_missing_primary_returns_400(self, client, auth_headers, db_session):
        payload = {
            **_SUGGESTION_PAYLOAD,
            "sector": {"primary": "", "secondary": None},
        }
        resp = client.post(
            _api("/indicator-suggestions"),
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_subsector_dict_missing_primary_returns_400(self, client, auth_headers, db_session):
        payload = {
            **_SUGGESTION_PAYLOAD,
            "sub_sector": {"primary": "", "secondary": None},
        }
        resp = client.post(
            _api("/indicator-suggestions"),
            json=payload,
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_sector_as_string_accepted(self, client, auth_headers, db_session):
        payload = {**_SUGGESTION_PAYLOAD, "sector": "Health"}
        with patch("app.services.email.service.send_suggestion_confirmation_email"), \
             patch("app.services.email.service.send_admin_notification_email"):
            resp = client.post(
                _api("/indicator-suggestions"),
                json=payload,
                headers=auth_headers,
            )
        assert resp.status_code == 201

    def test_subsector_as_string_accepted(self, client, auth_headers, db_session):
        payload = {**_SUGGESTION_PAYLOAD, "sub_sector": "Primary Health"}
        with patch("app.services.email.service.send_suggestion_confirmation_email"), \
             patch("app.services.email.service.send_admin_notification_email"):
            resp = client.post(
                _api("/indicator-suggestions"),
                json=payload,
                headers=auth_headers,
            )
        assert resp.status_code == 201

    def test_email_failure_does_not_fail_request(self, client, auth_headers, db_session):
        """Email sending failures are swallowed — request still succeeds."""
        with patch("app.services.email.service.send_suggestion_confirmation_email", side_effect=Exception("SMTP error")), \
             patch("app.services.email.service.send_admin_notification_email", side_effect=Exception("SMTP error")):
            resp = client.post(
                _api("/indicator-suggestions"),
                json=_SUGGESTION_PAYLOAD,
                headers=auth_headers,
            )
        assert resp.status_code == 201

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.db") as mock_db:
            mock_db.session.add.side_effect = Exception("db error")
            resp = client.post(
                _api("/indicator-suggestions"),
                json=_SUGGESTION_PAYLOAD,
                headers=auth_headers,
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/indicator-suggestions
# ---------------------------------------------------------------------------

class TestGetIndicatorSuggestions:
    """Tests for GET /api/v1/indicator-suggestions."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/indicator-suggestions"))
        assert resp.status_code == 401

    def test_returns_list(self, client, auth_headers, db_session):
        resp = client.get(_api("/indicator-suggestions"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "suggestions" in data
        assert "pagination" in data

    def test_filter_by_status(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Bob",
                submitter_email="bob@example.com",
                suggestion_type="new_indicator",
                indicator_name="Filtered",
                reason="test",
                status="pending",
            )
            db_session.add(s)
            db_session.commit()

        resp = client.get(_api("/indicator-suggestions?status=pending"), headers=auth_headers)
        assert resp.status_code == 200

    def test_filter_by_suggestion_type(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Carol",
                submitter_email="carol@example.com",
                suggestion_type="correction",
                indicator_name="Modified",
                reason="test",
            )
            db_session.add(s)
            db_session.commit()

        resp = client.get(_api("/indicator-suggestions?suggestion_type=correction"), headers=auth_headers)
        assert resp.status_code == 200

    def test_pagination_params(self, client, auth_headers, db_session):
        resp = client.get(_api("/indicator-suggestions?page=1&per_page=5"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["per_page"] == 5

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.IndicatorSuggestion.query") as mock_q:
            mock_q.side_effect = Exception("db crash")
            resp = client.get(_api("/indicator-suggestions"), headers=auth_headers)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/indicator-suggestions/<id>
# ---------------------------------------------------------------------------

class TestGetIndicatorSuggestion:
    """Tests for GET /api/v1/indicator-suggestions/<suggestion_id>."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/indicator-suggestions/1"))
        assert resp.status_code == 401

    def test_not_found_returns_404(self, client, auth_headers, db_session):
        resp = client.get(_api("/indicator-suggestions/999999"), headers=auth_headers)
        assert resp.status_code == 404

    def test_found_returns_suggestion(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Dave",
                submitter_email="dave@example.com",
                suggestion_type="new_indicator",
                indicator_name="Found",
                reason="test",
            )
            db_session.add(s)
            db_session.commit()
            s_id = s.id

        resp = client.get(_api(f"/indicator-suggestions/{s_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["indicator_name"] == "Found"


# ---------------------------------------------------------------------------
# PUT /api/v1/indicator-suggestions/<id>/status
# ---------------------------------------------------------------------------

class TestUpdateIndicatorSuggestionStatus:
    """Tests for PUT /api/v1/indicator-suggestions/<id>/status."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.put(
            _api("/indicator-suggestions/1/status"),
            json={"status": "approved"},
        )
        assert resp.status_code == 401

    def test_non_admin_returns_403(self, client, auth_headers, db_session):
        """Non-admin API key caller returns 403."""
        with patch("app.routes.api.indicators.AuthorizationService.is_admin", return_value=False):
            resp = client.put(
                _api("/indicator-suggestions/1/status"),
                json={"status": "approved"},
                headers=auth_headers,
            )
        assert resp.status_code == 403

    def test_missing_status_returns_400(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Eve",
                submitter_email="eve@example.com",
                suggestion_type="new_indicator",
                indicator_name="Status Update",
                reason="test",
            )
            db_session.add(s)
            db_session.commit()
            s_id = s.id

        with patch("app.routes.api.indicators.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.api.indicators.current_user") as mock_cu:
            mock_cu.is_authenticated = True
            resp = client.put(
                _api(f"/indicator-suggestions/{s_id}/status"),
                json={},  # missing status
                headers=auth_headers,
            )
        assert resp.status_code == 400

    def test_not_found_returns_404(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.api.indicators.current_user") as mock_cu:
            mock_cu.is_authenticated = True
            resp = client.put(
                _api("/indicator-suggestions/999999/status"),
                json={"status": "approved"},
                headers=auth_headers,
            )
        assert resp.status_code == 404

    def test_valid_status_update(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Frank",
                submitter_email="frank@example.com",
                suggestion_type="new_indicator",
                indicator_name="Update Me",
                reason="test",
                status="pending",
            )
            db_session.add(s)
            db_session.commit()
            s_id = s.id

        with patch("app.routes.api.indicators.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.api.indicators.current_user") as mock_cu:
            mock_cu.is_authenticated = True
            resp = client.put(
                _api(f"/indicator-suggestions/{s_id}/status"),
                json={"status": "approved", "admin_notes": "Looks good"},
                headers=auth_headers,
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "status" in data

    def test_exception_returns_500(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = IndicatorSuggestion(
                submitter_name="Greg",
                submitter_email="greg@example.com",
                suggestion_type="new_indicator",
                indicator_name="Fail Update",
                reason="test",
            )
            db_session.add(s)
            db_session.commit()
            s_id = s.id

        with patch("app.routes.api.indicators.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.api.indicators.current_user") as mock_cu, \
             patch("app.routes.api.indicators.db") as mock_db:
            mock_cu.is_authenticated = True
            mock_db.session.flush.side_effect = Exception("DB error")
            resp = client.put(
                _api(f"/indicator-suggestions/{s_id}/status"),
                json={"status": "approved"},
                headers=auth_headers,
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/sectors
# ---------------------------------------------------------------------------

class TestGetSectors:
    """Tests for GET /api/v1/sectors."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/sectors"))
        assert resp.status_code == 401

    def test_empty_db_returns_empty_sectors(self, client, auth_headers, db_session):
        resp = client.get(_api("/sectors"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sectors" in data
        assert isinstance(data["sectors"], list)

    def test_returns_sectors_with_subsectors(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = _make_sector(db_session, name="Health")
            _make_subsector(db_session, s.id, name="Primary Health")
            db_session.commit()

        resp = client.get(_api("/sectors"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["sectors"]) >= 1
        sector = next((s for s in data["sectors"] if s["name"] == "Health"), None)
        assert sector is not None
        assert "subsectors" in sector

    def test_inactive_sectors_excluded(self, client, auth_headers, db_session, app):
        with app.app_context():
            _make_sector(db_session, name="Inactive", is_active=False)
            db_session.commit()

        resp = client.get(_api("/sectors"), headers=auth_headers)
        data = resp.get_json()
        names = [s["name"] for s in data["sectors"]]
        assert "Inactive" not in names

    def test_response_has_cache_control_header(self, client, auth_headers, db_session):
        resp = client.get(_api("/sectors"), headers=auth_headers)
        assert resp.status_code == 200
        assert "Cache-Control" in resp.headers

    def test_sector_fields_structure(self, client, auth_headers, db_session, app):
        with app.app_context():
            _make_sector(db_session, name="Structure Test")
            db_session.commit()

        resp = client.get(_api("/sectors"), headers=auth_headers)
        data = resp.get_json()
        for field in ["id", "name", "subsectors"]:
            for sector in data["sectors"]:
                assert field in sector

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.Sector.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("crash")
            resp = client.get(_api("/sectors"), headers=auth_headers)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/subsectors
# ---------------------------------------------------------------------------

class TestGetSubsectors:
    """Tests for GET /api/v1/subsectors."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/subsectors"))
        assert resp.status_code == 401

    def test_empty_db_returns_empty_list(self, client, auth_headers, db_session):
        resp = client.get(_api("/subsectors"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "subsectors" in data
        assert isinstance(data["subsectors"], list)

    def test_returns_subsectors_with_parent(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = _make_sector(db_session, name="WASH")
            _make_subsector(db_session, s.id, name="Water")
            db_session.commit()

        resp = client.get(_api("/subsectors"), headers=auth_headers)
        data = resp.get_json()
        assert len(data["subsectors"]) >= 1
        ss = next((ss for ss in data["subsectors"] if ss["name"] == "Water"), None)
        assert ss is not None
        assert ss["parent_sector"]["name"] == "WASH"

    def test_inactive_subsectors_excluded(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = _make_sector(db_session, name="ActiveSector")
            _make_subsector(db_session, s.id, name="InactiveSubsector", is_active=False)
            db_session.commit()

        resp = client.get(_api("/subsectors"), headers=auth_headers)
        data = resp.get_json()
        names = [ss["name"] for ss in data["subsectors"]]
        assert "InactiveSubsector" not in names

    def test_response_has_cache_control_header(self, client, auth_headers, db_session):
        resp = client.get(_api("/subsectors"), headers=auth_headers)
        assert "Cache-Control" in resp.headers

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.SubSector.query") as mock_q:
            mock_q.options.side_effect = Exception("crash")
            resp = client.get(_api("/subsectors"), headers=auth_headers)
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/v1/sectors-subsectors
# ---------------------------------------------------------------------------

class TestGetSectorsSubsectors:
    """Tests for GET /api/v1/sectors-subsectors."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/sectors-subsectors"))
        assert resp.status_code == 401

    def test_empty_db_returns_empty_sectors(self, client, auth_headers, db_session):
        resp = client.get(_api("/sectors-subsectors"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "sectors" in data

    def test_returns_hierarchical_structure(self, client, auth_headers, db_session, app):
        with app.app_context():
            s = _make_sector(db_session, name="Protection")
            _make_subsector(db_session, s.id, name="GBV")
            db_session.commit()

        resp = client.get(_api("/sectors-subsectors"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        sector = next((s for s in data["sectors"] if s["name"] == "Protection"), None)
        assert sector is not None
        assert "subsectors" in sector

    def test_sector_includes_icon_class(self, client, auth_headers, db_session, app):
        """sectors-subsectors includes icon_class in sector data."""
        with app.app_context():
            s = Sector(name="WithIcon", is_active=True, display_order=1, icon_class="fa-heart")
            db_session.add(s)
            db_session.commit()

        resp = client.get(_api("/sectors-subsectors"), headers=auth_headers)
        data = resp.get_json()
        sector = next((s for s in data["sectors"] if s["name"] == "WithIcon"), None)
        assert sector is not None
        assert "icon_class" in sector

    def test_response_has_cache_control_header(self, client, auth_headers, db_session):
        resp = client.get(_api("/sectors-subsectors"), headers=auth_headers)
        assert "Cache-Control" in resp.headers

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.indicators.Sector.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("crash")
            resp = client.get(_api("/sectors-subsectors"), headers=auth_headers)
        assert resp.status_code == 500
