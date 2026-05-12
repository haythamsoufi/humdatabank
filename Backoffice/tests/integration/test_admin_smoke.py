import pytest

from tests.factories import create_test_user


@pytest.mark.integration
class TestAdminSmoke:
    def test_admin_endpoints_denied_for_regular_user(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="user")
            user_id = user.id

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        # Should be blocked (redirect to login or 403)
        resp = client.get("/admin/api/system/health", follow_redirects=False)
        assert resp.status_code in (302, 403)

        resp = client.get("/admin/api/users", follow_redirects=False)
        assert resp.status_code in (302, 403)

        resp = client.get("/admin/plugins", headers={"Accept": "application/json"}, follow_redirects=False)
        assert resp.status_code in (302, 403)

    def test_admin_json_endpoints_work_for_admin(self, logged_in_client):
        resp = logged_in_client.get("/admin/api/system/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("status") == "success"
        assert "data" in data and "database_healthy" in data["data"]

        resp = logged_in_client.get("/admin/api/users")
        assert resp.status_code == 200
        out = resp.get_json()
        assert isinstance(out, dict)
        assert out.get("status") == "success"
        assert "data" in out
        assert isinstance(out["data"], list)

        resp = logged_in_client.get("/admin/plugins", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        out = resp.get_json()
        assert out.get("success") is True
        assert "plugins" in out

