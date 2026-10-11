"""Integration tests for POST /api/mobile/v1/diagnostics/client-error."""
import pytest

from app.models import SecurityEvent
from tests.api.mobile.helpers import assert_mobile_error, assert_mobile_ok

URL = '/api/mobile/v1/diagnostics/client-error'


def _payload(**overrides):
    body = {
        'category': 'offline_download',
        'message': 'Offline copy is incomplete: 1 script/style file(s) could not be saved',
        'error_type': 'AssignmentOfflineBundleException',
        'stack': '#0 downloadAndSave (assignment_offline_bundle_service.dart:845)\n#1 main',
        'assignment_id': 123,
        'template_id': 45,
        'language': 'en',
        'platform': 'ios',
        'details': {'missing_assets': ['/static/js/x.js', '/static/css/y.css']},
    }
    body.update(overrides)
    return body


@pytest.mark.api
@pytest.mark.integration
class TestMobileClientErrorDiagnostics:
    def test_requires_authentication(self, client, db_session):
        resp = client.post(URL, json=_payload())
        assert resp.status_code in (401, 403)

    def test_records_audit_only_security_event(self, client, jwt_headers, db_session):
        resp = client.post(URL, json=_payload(), headers=jwt_headers)
        assert_mobile_ok(resp)

        event = SecurityEvent.query.filter_by(event_type='mobile_client_error').one()
        assert event.severity == 'low'
        assert event.user_id is not None
        assert 'offline_download' in event.description
        ctx = event.context_data
        assert ctx['assignment_id'] == 123
        assert ctx['template_id'] == 45
        assert ctx['details']['missing_assets'] == ['/static/js/x.js', '/static/css/y.css']
        assert 'assignment_offline_bundle_service.dart:845' in ctx['stack']

    def test_never_emails_admins(self, client, jwt_headers, db_session, monkeypatch):
        from app.services.security.monitoring import SecurityMonitor

        sent = []
        monkeypatch.setattr(SecurityMonitor, '_send_security_alert', lambda *a, **k: sent.append(1))
        client.post(URL, json=_payload(), headers=jwt_headers)
        assert sent == []

    def test_rejects_unknown_category(self, client, jwt_headers, db_session):
        resp = client.post(URL, json=_payload(category='anything'), headers=jwt_headers)
        assert_mobile_error(resp, 400)
        assert SecurityEvent.query.filter_by(event_type='mobile_client_error').count() == 0

    def test_redacts_credentials_and_bounds_size(self, client, jwt_headers, db_session):
        long_text = 'x' * 25_000
        resp = client.post(
            URL,
            json=_payload(
                message='failed Cookie: session=abc123; other=1 and Bearer eyJhbGciOi.payload.sig',
                stack=long_text,
                details={'url': 'https://h/p?token=SECRET&a=1', 'blob': long_text},
            ),
            headers=jwt_headers,
        )
        assert_mobile_ok(resp)
        event = SecurityEvent.query.filter_by(event_type='mobile_client_error').one()
        ctx = event.context_data
        dumped = str(ctx) + event.description
        assert 'abc123' not in dumped
        assert 'eyJhbGciOi' not in dumped
        assert 'SECRET' not in dumped
        assert len(ctx['stack']) <= 6000
        assert len(ctx['details']['blob']) <= 1500
