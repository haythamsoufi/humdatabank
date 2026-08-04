import pytest

from app.services.security.public_data_access import (
    public_data_scope_present,
    validate_public_data_request,
)


class TestPublicDataScopePresent:
    def test_true_for_indicator_bank_id(self):
        assert public_data_scope_present({"indicator_bank_id": "42"})

    def test_true_for_period_name(self):
        assert public_data_scope_present({"period_name": "Annual 2023"})

    def test_false_for_empty(self):
        assert not public_data_scope_present({})


class TestValidatePublicDataRequest:
    def test_unscoped_returns_401(self, app):
        with app.app_context():
            resp = validate_public_data_request({})
        assert resp is not None
        assert resp.status_code == 401

    def test_scoped_returns_none(self, app):
        with app.app_context():
            resp = validate_public_data_request({"indicator_bank_id": "42"})
        assert resp is None

    def test_analysis_blocked(self, app):
        with app.app_context():
            resp = validate_public_data_request(
                {"indicator_bank_id": "42", "analysis": "true"}
            )
        assert resp is not None
        assert resp.status_code == 401
