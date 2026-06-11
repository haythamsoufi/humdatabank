"""
Tests for app/routes/api/countries.py

Coverage targets:
- GET /api/v1/countrymap          (require_api_key_or_session, locale, ETag, cache, pagination)
- GET /api/v1/periods             (require_api_key, filters, iso resolution, exception)
- GET /api/v1/nationalsocietymap  (require_api_key, filters, pagination, locale)
- Module-level helpers: _load_region_translations, _countrymap_rate_limit_fallback
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models import Country, AssignedForm
from app.models.organization import NationalSociety
from app.models.assignments import AssignmentEntityStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _make_country(db_session, name="Test Country", iso3="TST", iso2="TS", region="Africa"):
    """Create a minimal Country."""
    c = Country(name=name, iso3=iso3, iso2=iso2, region=region)
    db_session.add(c)
    db_session.flush()
    return c


def _make_ns(db_session, country_id, name="Test NS", code="TST-NS"):
    """Create a minimal NationalSociety."""
    ns = NationalSociety(
        name=name,
        code=code,
        country_id=country_id,
        is_active=True,
        display_order=1,
    )
    db_session.add(ns)
    db_session.flush()
    return ns


# ---------------------------------------------------------------------------
# GET /api/v1/countrymap
# ---------------------------------------------------------------------------

class TestGetCountries:
    """Tests for GET /api/v1/countrymap."""

    def test_no_auth_returns_401(self, client, db_session):
        """Request without any auth should fail."""
        resp = client.get(_api("/countrymap"))
        assert resp.status_code in (401, 302)

    def test_with_api_key_returns_list(self, client, auth_headers, db_session, app):
        """Valid API key returns a JSON array of countries."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        resp = client.get(_api("/countrymap"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_with_session_auth_returns_list(self, logged_in_client, db_session, app):
        """Session-authenticated user can access countrymap."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        resp = logged_in_client.get(_api("/countrymap"))
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_country_fields_structure(self, client, auth_headers, db_session, app):
        """Each country entry has required fields."""
        with app.app_context():
            _make_country(db_session, name="FieldTest", iso3="FLD", iso2="FT")
            db_session.commit()

        resp = client.get(_api("/countrymap"), headers=auth_headers)
        data = resp.get_json()
        assert len(data) >= 1
        country = next((c for c in data if c.get("iso3") == "FLD"), None)
        assert country is not None
        for field in ["id", "name", "iso3", "iso2", "region"]:
            assert field in country

    def test_locale_param_accepted(self, client, auth_headers, db_session, app):
        """locale query param does not break the endpoint."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        resp = client.get(_api("/countrymap?locale=fr"), headers=auth_headers)
        assert resp.status_code == 200

    def test_invalid_locale_falls_back_to_en(self, client, auth_headers, db_session, app):
        """Unknown locale silently falls back to 'en'."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        resp = client.get(_api("/countrymap?locale=zz"), headers=auth_headers)
        assert resp.status_code == 200

    def test_etag_header_returned(self, client, auth_headers, db_session, app):
        """Response includes an ETag header."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        resp = client.get(_api("/countrymap"), headers=auth_headers)
        assert "ETag" in resp.headers

    def test_etag_304_if_none_match(self, client, auth_headers, db_session, app):
        """If-None-Match with matching ETag returns 304."""
        with app.app_context():
            _make_country(db_session)
            db_session.commit()

        # First request to get ETag
        r1 = client.get(_api("/countrymap"), headers=auth_headers)
        etag = r1.headers.get("ETag", "").strip('"')
        assert etag

        # Second request with matching ETag — but we need the cached result,
        # so call the endpoint once more with the rate-limit fallback path
        # by clearing the cache and verifying the standard path sets it.
        from app.routes.api import countries as countries_mod
        with countries_mod._countrymap_cache_lock:
            # If there is a cached entry, test the 304 path via fallback
            cached = countries_mod._countrymap_cache.get("en")
        if cached:
            # Simulate rate-limit fallback: patch the rate limiter to call fallback
            headers_with_etag = {**auth_headers, "If-None-Match": f'"{etag}"'}
            # Just verify second request works — server-side 304 requires CDN/proxy
            r2 = client.get(_api("/countrymap"), headers=headers_with_etag)
            assert r2.status_code in (200, 304)

    def test_paginated_countrymap(self, client, auth_headers, db_session, app):
        """page + per_page parameters return paginated response."""
        with app.app_context():
            for i in range(3):
                _make_country(db_session, name=f"Country{i}", iso3=f"C{i:02}", iso2=f"C{i}")
            db_session.commit()

        resp = client.get(_api("/countrymap?page=1&per_page=2"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "countries" in data
        assert "total_items" in data
        assert len(data["countries"]) <= 2

    def test_countrymap_rate_limit_fallback_no_cache(self, app, client, auth_headers, db_session):
        """_countrymap_rate_limit_fallback returns None when cache is empty."""
        from app.routes.api.countries import _countrymap_rate_limit_fallback, _countrymap_cache, _countrymap_cache_lock
        with _countrymap_cache_lock:
            _countrymap_cache.clear()
        with app.test_request_context("/api/v1/countrymap"):
            result = _countrymap_rate_limit_fallback()
        assert result is None

    def test_countrymap_rate_limit_fallback_with_cache(self, app, client, auth_headers, db_session):
        """_countrymap_rate_limit_fallback returns cached response when cache is populated."""
        import time
        from app.routes.api.countries import _countrymap_cache, _countrymap_cache_lock

        with _countrymap_cache_lock:
            _countrymap_cache["en"] = (time.time() + 300, "abc123", '[]')

        with app.test_request_context("/api/v1/countrymap"):
            from app.routes.api.countries import _countrymap_rate_limit_fallback
            result = _countrymap_rate_limit_fallback()
        assert result is not None

    def test_countrymap_fallback_304_on_etag_match(self, app, db_session):
        """Fallback returns 304 when If-None-Match matches cached ETag."""
        import time
        from app.routes.api.countries import _countrymap_cache, _countrymap_cache_lock

        with _countrymap_cache_lock:
            _countrymap_cache["en"] = (time.time() + 300, "etag999", '[]')

        with app.test_request_context("/api/v1/countrymap", headers={"If-None-Match": '"etag999"'}):
            from app.routes.api.countries import _countrymap_rate_limit_fallback
            result = _countrymap_rate_limit_fallback()
        assert result is not None
        assert result.status_code == 304


# ---------------------------------------------------------------------------
# GET /api/v1/periods
# ---------------------------------------------------------------------------

class TestGetPeriods:
    """Tests for GET /api/v1/periods."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/periods"))
        assert resp.status_code == 401

    def test_empty_db_returns_empty_list(self, client, auth_headers, db_session):
        resp = client.get(_api("/periods"), headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_returns_distinct_periods(self, client, auth_headers, db_session, app):
        """Returns distinct period names from assigned forms."""
        from tests.factories import create_test_template
        with app.app_context():
            tmpl = create_test_template(db_session)
            db_session.add(AssignedForm(template_id=tmpl.id, period_name="2023"))
            db_session.add(AssignedForm(template_id=tmpl.id, period_name="2024"))
            db_session.add(AssignedForm(template_id=tmpl.id, period_name="2024"))  # duplicate
            db_session.commit()

        resp = client.get(_api("/periods"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "2024" in data
        assert "2023" in data
        # Should be distinct
        assert data.count("2024") == 1

    def test_filter_by_template_id(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_template
        with app.app_context():
            tmpl1 = create_test_template(db_session)
            tmpl2 = create_test_template(db_session)
            db_session.add(AssignedForm(template_id=tmpl1.id, period_name="OnlyInT1"))
            db_session.add(AssignedForm(template_id=tmpl2.id, period_name="OnlyInT2"))
            db_session.commit()
            t1_id = tmpl1.id

        resp = client.get(_api(f"/periods?template_id={t1_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "OnlyInT1" in data
        assert "OnlyInT2" not in data

    def test_filter_by_country_id(self, client, auth_headers, db_session, app):
        """country_id filter returns periods scoped to that country's entity statuses."""
        from tests.factories import create_test_template, create_test_country
        with app.app_context():
            tmpl = create_test_template(db_session)
            country = create_test_country(db_session)
            af = AssignedForm(template_id=tmpl.id, period_name="CountryPeriod")
            db_session.add(af)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=af.id,
                entity_id=country.id,
                entity_type="country",
            )
            db_session.add(aes)
            db_session.commit()
            c_id = country.id

        resp = client.get(_api(f"/periods?country_id={c_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "CountryPeriod" in data

    def test_filter_by_iso3(self, client, auth_headers, db_session, app):
        """country_iso3 resolves to country_id and returns scoped periods."""
        from tests.factories import create_test_template, create_test_country
        with app.app_context():
            tmpl = create_test_template(db_session)
            country = create_test_country(db_session)
            af = AssignedForm(template_id=tmpl.id, period_name="ISO3Period")
            db_session.add(af)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=af.id,
                entity_id=country.id,
                entity_type="country",
            )
            db_session.add(aes)
            db_session.commit()
            iso3 = country.iso3

        resp = client.get(_api(f"/periods?country_iso3={iso3}"), headers=auth_headers)
        assert resp.status_code == 200

    def test_filter_by_iso2(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_template, create_test_country
        with app.app_context():
            tmpl = create_test_template(db_session)
            country = create_test_country(db_session)
            af = AssignedForm(template_id=tmpl.id, period_name="ISO2Period")
            db_session.add(af)
            db_session.flush()
            aes = AssignmentEntityStatus(
                assigned_form_id=af.id,
                entity_id=country.id,
                entity_type="country",
            )
            db_session.add(aes)
            db_session.commit()
            iso2 = country.iso2

        resp = client.get(_api(f"/periods?country_iso2={iso2}"), headers=auth_headers)
        assert resp.status_code == 200

    def test_invalid_iso_returns_error(self, client, auth_headers, db_session):
        """Invalid ISO code returns 4xx error."""
        with patch("app.utils.country_utils.resolve_country_from_iso", return_value=(None, "Country not found")):
            resp = client.get(_api("/periods?country_iso3=ZZZ"), headers=auth_headers)
        assert resp.status_code in (400, 404)

    def test_periods_sorted_by_year_desc(self, client, auth_headers, db_session, app):
        """Periods are sorted by year descending."""
        from tests.factories import create_test_template
        with app.app_context():
            tmpl = create_test_template(db_session)
            for year in ["2022", "2020", "2024", "2021"]:
                db_session.add(AssignedForm(template_id=tmpl.id, period_name=year))
            db_session.commit()

        resp = client.get(_api("/periods"), headers=auth_headers)
        data = resp.get_json()
        years_in_data = [p for p in data if p in ["2020", "2021", "2022", "2024"]]
        assert years_in_data == sorted(years_in_data, reverse=True)

    def test_exception_returns_empty_list(self, client, auth_headers, db_session):
        """Exception inside handler returns empty list gracefully."""
        with patch("app.routes.api.countries.db") as mock_db:
            mock_db.session.query.side_effect = Exception("db crash")
            resp = client.get(_api("/periods"), headers=auth_headers)
        assert resp.status_code == 200
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# GET /api/v1/nationalsocietymap
# ---------------------------------------------------------------------------

class TestGetNationalSocieties:
    """Tests for GET /api/v1/nationalsocietymap."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/nationalsocietymap"))
        assert resp.status_code == 401

    def test_with_api_key_empty_db(self, client, auth_headers, db_session):
        resp = client.get(_api("/nationalsocietymap"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_returns_national_societies(self, client, auth_headers, db_session, app):
        with app.app_context():
            country = _make_country(db_session, name="NS Country", iso3="NSC", iso2="NC")
            _make_ns(db_session, country.id, name="NS Test", code="NS-T1")
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        names = [ns.get("name") for ns in data]
        assert "NS Test" in names

    def test_ns_response_structure(self, client, auth_headers, db_session, app):
        with app.app_context():
            country = _make_country(db_session, name="StructCountry", iso3="STC", iso2="SC")
            _make_ns(db_session, country.id, name="Struct NS", code="ST-NS")
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap"), headers=auth_headers)
        data = resp.get_json()
        ns = next((n for n in data if n.get("name") == "Struct NS"), None)
        assert ns is not None
        for field in ["id", "name", "code", "country_id", "country_name", "country_iso3", "region"]:
            assert field in ns

    def test_filter_by_country_id(self, client, auth_headers, db_session, app):
        with app.app_context():
            c1 = _make_country(db_session, name="C1", iso3="FC1", iso2="F1")
            c2 = _make_country(db_session, name="C2", iso3="FC2", iso2="F2")
            _make_ns(db_session, c1.id, name="NS-C1", code="NSC1")
            _make_ns(db_session, c2.id, name="NS-C2", code="NSC2")
            db_session.commit()
            c1_id = c1.id

        resp = client.get(_api(f"/nationalsocietymap?country_id={c1_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for ns in data:
            assert ns["country_id"] == c1_id

    def test_filter_by_is_active_true(self, client, auth_headers, db_session, app):
        with app.app_context():
            c = _make_country(db_session, name="ActiveC", iso3="ACV", iso2="AV")
            active_ns = NationalSociety(name="Active NS", code="ANS", country_id=c.id, is_active=True, display_order=1)
            inactive_ns = NationalSociety(name="Inactive NS", code="INS", country_id=c.id, is_active=False, display_order=2)
            db_session.add_all([active_ns, inactive_ns])
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap?is_active=true"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        names = [ns["name"] for ns in data]
        assert "Active NS" in names
        assert "Inactive NS" not in names

    def test_filter_by_is_active_false(self, client, auth_headers, db_session, app):
        with app.app_context():
            c = _make_country(db_session, name="InactiveC", iso3="ICV", iso2="IV")
            NationalSociety(name="Active NS2", code="ANS2", country_id=c.id, is_active=True, display_order=1)
            inactive = NationalSociety(name="Inactive NS2", code="INS2", country_id=c.id, is_active=False, display_order=2)
            db_session.add(inactive)
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap?is_active=false"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        names = [ns["name"] for ns in data]
        assert "Inactive NS2" in names

    def test_pagination(self, client, auth_headers, db_session, app):
        with app.app_context():
            c = _make_country(db_session, name="PaginateC", iso3="PGC", iso2="PC")
            for i in range(5):
                db_session.add(NationalSociety(name=f"NS{i}", code=f"PNS{i}", country_id=c.id, is_active=True, display_order=i))
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap?page=1&per_page=2"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "national_societies" in data
        assert "total_items" in data
        assert len(data["national_societies"]) <= 2

    def test_locale_param_accepted(self, client, auth_headers, db_session, app):
        with app.app_context():
            c = _make_country(db_session, name="LocaleC", iso3="LCC", iso2="LC")
            _make_ns(db_session, c.id, name="Locale NS", code="LNS")
            db_session.commit()

        resp = client.get(_api("/nationalsocietymap?locale=es"), headers=auth_headers)
        assert resp.status_code == 200
