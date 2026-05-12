"""Integration: Azure B2C configured — block parallel local identity paths."""

import pytest
from flask import url_for

from app import db
from app.models import PasswordResetToken, User


def _b2c_monkeypatch(monkeypatch, app):
    monkeypatch.setitem(app.config, "AZURE_B2C_TENANT", "contoso.onmicrosoft.com")
    monkeypatch.setitem(app.config, "AZURE_B2C_POLICY", "B2C_1_signup_signin")
    monkeypatch.setitem(app.config, "AZURE_B2C_CLIENT_ID", "test-client-id")
    monkeypatch.setitem(app.config, "AZURE_B2C_CLIENT_SECRET", "test-client-secret")


@pytest.mark.integration
def test_new_user_redirect_when_b2c_configured(app, logged_in_client, monkeypatch):
    _b2c_monkeypatch(monkeypatch, app)
    with app.app_context():
        url = url_for("user_management.new_user")
        users_list = url_for("user_management.manage_users")
    resp = logged_in_client.get(url, follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.location or ""
    assert users_list in loc or "/admin/users" in loc

    resp_post = logged_in_client.post(
        url,
        data={"csrf_token": "disabled", "submit": "Save"},
        follow_redirects=False,
    )
    assert resp_post.status_code == 302
    assert users_list in (resp_post.location or "") or "/admin/users" in (resp_post.location or "")


@pytest.mark.integration
def test_register_post_rejected_when_b2c_configured(app, db_session, client, monkeypatch):
    _b2c_monkeypatch(monkeypatch, app)
    with app.app_context():
        url = url_for("auth.register")
    resp = client.post(
        url,
        data={
            "csrf_token": "disabled",
            "email": "nobody_should_be_created@example.com",
            "name": "X",
            "password": "Abcd1234!",
            "confirm_password": "Abcd1234!",
            "requested_country_id": "",
            "request_message": "",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    with app.app_context():
        assert User.query.filter_by(email="nobody_should_be_created@example.com").first() is None


@pytest.mark.integration
def test_check_register_email_forbidden_when_b2c_configured(app, client, monkeypatch):
    _b2c_monkeypatch(monkeypatch, app)
    with app.app_context():
        url = url_for("auth.check_register_email", email="anyone@test.example")
    resp = client.get(url)
    assert resp.status_code == 403
    data = resp.get_json()
    assert data is not None
    assert data.get("ok") is False
    assert "exists" not in data


@pytest.mark.integration
def test_forgot_password_skips_token_for_azure_only_user_when_b2c(app, db_session, client, monkeypatch):
    _b2c_monkeypatch(monkeypatch, app)
    with app.app_context():
        u = User(email="b2c_only@example.com", name="B2C Only", active=True)
        u.password_hash = None
        db.session.add(u)
        db.session.commit()
        uid = u.id
        before = PasswordResetToken.query.filter_by(user_id=uid).count()
    with app.app_context():
        url = url_for("auth.forgot_password")
    client.post(
        url,
        data={"csrf_token": "disabled", "email": "b2c_only@example.com", "submit": "Send"},
        follow_redirects=False,
    )
    with app.app_context():
        after = PasswordResetToken.query.filter_by(user_id=uid).count()
    assert after == before
