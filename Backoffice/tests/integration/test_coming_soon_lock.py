"""Tests for the coming-soon and maintenance site lock middleware."""

import pytest


@pytest.mark.integration
class TestComingSoonLock:
    def test_disabled_by_default(self, client):
        resp = client.get("/")
        assert resp.status_code != 503 or b"Coming Soon" not in resp.data

    def test_blocks_routes_when_enabled(self, app, client):
        app.config["COMING_SOON_LOCK"] = True

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Coming Soon" in resp.data

        api_resp = client.get("/api/v1/countrymap", headers={"Accept": "application/json"})
        assert api_resp.status_code == 503
        assert api_resp.get_json()["code"] == "coming_soon"

    def test_health_check_still_works(self, app, client):
        app.config["COMING_SOON_LOCK"] = True

        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "healthy"

    def test_bypass_secret_allows_access(self, app, client):
        app.config["COMING_SOON_LOCK"] = True
        app.config["COMING_SOON_BYPASS_SECRET"] = "team-preview-token"

        blocked = client.get("/login")
        assert blocked.status_code == 200
        assert b"Coming Soon" in blocked.data

        bypassed = client.get("/login?coming_soon_bypass=team-preview-token")
        assert bypassed.status_code in (200, 302)
        assert b"Coming Soon" not in bypassed.data

        follow_up = client.get("/login")
        assert follow_up.status_code in (200, 302)
        assert b"Coming Soon" not in follow_up.data


@pytest.mark.integration
class TestMaintenanceLock:
    def test_blocks_routes_when_enabled(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Maintenance" in resp.data
        assert b"Maintenance in progress" in resp.data

        api_resp = client.get("/api/v1/countrymap", headers={"Accept": "application/json"})
        assert api_resp.status_code == 503
        assert api_resp.get_json()["code"] == "maintenance"

    def test_takes_precedence_over_coming_soon(self, app, client):
        app.config["COMING_SOON_LOCK"] = True
        app.config["MAINTENANCE_LOCK"] = True

        resp = client.get("/")
        assert b"Maintenance in progress" in resp.data
        assert b"Preparing launch" not in resp.data

    def test_bypass_secret_allows_access(self, app, client):
        app.config["MAINTENANCE_LOCK"] = True
        app.config["MAINTENANCE_BYPASS_SECRET"] = "maintenance-team-token"

        blocked = client.get("/login")
        assert blocked.status_code == 200
        assert b"Maintenance" in blocked.data

        bypassed = client.get("/login?maintenance_bypass=maintenance-team-token")
        assert bypassed.status_code in (200, 302)
        assert b"Maintenance in progress" not in bypassed.data

        follow_up = client.get("/login")
        assert follow_up.status_code in (200, 302)
        assert b"Maintenance in progress" not in follow_up.data
