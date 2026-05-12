"""Unit tests for app.utils.mobile_jwt — app context only, no database."""
import pytest
import jwt as pyjwt


@pytest.mark.unit
class TestIssueTokenPair:
    def test_returns_required_keys(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_token_pair
            result = issue_token_pair(user_id=1)
            assert 'access_token' in result
            assert 'refresh_token' in result
            assert result['token_type'] == 'Bearer'
            assert isinstance(result['expires_in'], int)
            assert result['expires_in'] > 0

    def test_tokens_are_distinct(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_token_pair
            result = issue_token_pair(user_id=1)
            assert result['access_token'] != result['refresh_token']


@pytest.mark.unit
class TestDecodeToken:
    def test_roundtrip_access(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_access_token, decode_mobile_token
            token = issue_access_token(user_id=42, session_id='s1')
            claims = decode_mobile_token(token, expected_type='access')
            assert claims.user_id == 42
            assert claims.token_type == 'access'
            assert claims.sid == 's1'

    def test_roundtrip_refresh(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_refresh_token, decode_mobile_token
            token = issue_refresh_token(user_id=7)
            claims = decode_mobile_token(token, expected_type='refresh')
            assert claims.user_id == 7
            assert claims.token_type == 'refresh'

    def test_wrong_expected_type_raises(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_access_token, decode_mobile_token
            token = issue_access_token(user_id=1)
            with pytest.raises(pyjwt.InvalidTokenError):
                decode_mobile_token(token, expected_type='refresh')

    def test_expired_token_raises(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_access_token, decode_mobile_token
            token = issue_access_token(user_id=1, ttl_minutes=-1)
            with pytest.raises(pyjwt.ExpiredSignatureError):
                decode_mobile_token(token)

    def test_wrong_audience_raises(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import _jwt_secret, MOBILE_TOKEN_ISSUER
            payload = {
                'sub': '1', 'type': 'access', 'iat': 0, 'exp': 9999999999,
                'aud': 'wrong-audience', 'iss': MOBILE_TOKEN_ISSUER, 'ver': 1,
            }
            token = pyjwt.encode(payload, _jwt_secret(), algorithm='HS256')
            from app.utils.mobile_jwt import decode_mobile_token
            with pytest.raises(pyjwt.InvalidAudienceError):
                decode_mobile_token(token)

    def test_sid_none_when_omitted(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import issue_access_token, decode_mobile_token
            token = issue_access_token(user_id=1)
            claims = decode_mobile_token(token)
            assert claims.sid is None


@pytest.mark.unit
class TestJwtSecret:
    def test_falls_back_to_secret_key(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import _jwt_secret
            app.config.pop('MOBILE_JWT_SECRET', None)
            assert _jwt_secret() == app.config['SECRET_KEY']

    def test_prefers_mobile_jwt_secret(self, app):
        with app.app_context():
            from app.utils.mobile_jwt import _jwt_secret
            app.config['MOBILE_JWT_SECRET'] = 'mobile-only-secret'
            try:
                assert _jwt_secret() == 'mobile-only-secret'
            finally:
                app.config.pop('MOBILE_JWT_SECRET', None)
