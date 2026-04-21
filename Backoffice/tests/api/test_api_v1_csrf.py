import pytest

from flask_wtf.csrf import CSRFError
import uuid


@pytest.mark.api
@pytest.mark.integration
class TestApiV1CsrfSessionEndpoints:
    def test_profile_update_requires_csrf(self, client, db_session, app, monkeypatch):
        import app.utils.request_validation as rv
        from app.models import User

        with app.app_context():
            email = f"csrf_test_{uuid.uuid4().hex}@example.com"
            user = User(email=email, name="CSRF Test", active=True)
            user.set_password("test_password")
            db_session.add(user)
            db_session.flush()
            user_id = int(user.id)
            db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        def _raise():
            raise CSRFError("CSRF token missing")

        monkeypatch.setattr(rv.csrf, "protect", _raise)

        resp = client.put("/api/v1/user/profile", json={"name": "New Name"})
        assert resp.status_code == 400
        data = resp.get_json() or {}
        assert data.get("error") == "CSRF validation failed"

    def test_quiz_submit_requires_csrf(self, client, db_session, app, monkeypatch):
        import app.utils.request_validation as rv
        from app.models import User

        with app.app_context():
            email = f"csrf_test_{uuid.uuid4().hex}@example.com"
            user = User(email=email, name="CSRF Test 2", active=True)
            user.set_password("test_password")
            db_session.add(user)
            db_session.flush()
            user_id = int(user.id)
            db_session.commit()

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_id)
            sess["_fresh"] = True

        def _raise():
            raise CSRFError("CSRF token missing")

        monkeypatch.setattr(rv.csrf, "protect", _raise)

        resp = client.post("/api/v1/quiz/submit-score", json={"score": 1})
        assert resp.status_code == 400
        data = resp.get_json() or {}
        assert data.get("error") == "CSRF validation failed"

