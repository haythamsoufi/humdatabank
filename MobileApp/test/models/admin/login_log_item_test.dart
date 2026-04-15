import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/admin/login_log_item.dart';

void main() {
  group('LoginLogItem.fromJson', () {
    test('parses full data with nested user map', () {
      final json = {
        'id': 101,
        'timestamp': '2025-03-15T10:30:00Z',
        'event_type': 'login_success',
        'email_attempted': 'alice@example.org',
        'user': {
          'name': 'Alice Smith',
          'email': 'alice@example.org',
        },
        'ip_address': '192.168.1.10',
        'location': 'Beirut, Lebanon',
        'browser': 'Chrome 120',
        'device_type': 'Desktop',
        'user_agent': 'Mozilla/5.0 ...',
        'is_suspicious': false,
        'failure_reason': null,
        'failure_reason_display': null,
        'failed_attempts_count': 0,
      };

      final item = LoginLogItem.fromJson(json);

      expect(item.id, 101);
      expect(item.timestampIso, '2025-03-15T10:30:00Z');
      expect(item.eventType, 'login_success');
      expect(item.emailAttempted, 'alice@example.org');
      expect(item.userName, 'Alice Smith');
      expect(item.userEmail, 'alice@example.org');
      expect(item.ipAddress, '192.168.1.10');
      expect(item.location, 'Beirut, Lebanon');
      expect(item.browser, 'Chrome 120');
      expect(item.deviceType, 'Desktop');
      expect(item.userAgent, 'Mozilla/5.0 ...');
      expect(item.isSuspicious, false);
      expect(item.failureReason, isNull);
      expect(item.failureReasonDisplay, isNull);
      expect(item.failedAttemptsCount, 0);
    });

    test('parses data without user map — userName and userEmail are null', () {
      final json = {
        'id': 202,
        'timestamp': '2025-04-01T08:00:00Z',
        'event_type': 'login_failed',
        'email_attempted': 'unknown@hacker.net',
        'ip_address': '10.0.0.5',
        'is_suspicious': true,
        'failure_reason': 'invalid_password',
        'failure_reason_display': 'Invalid password',
        'failed_attempts_count': 3,
      };

      final item = LoginLogItem.fromJson(json);

      expect(item.id, 202);
      expect(item.userName, isNull);
      expect(item.userEmail, isNull);
      expect(item.isSuspicious, true);
      expect(item.failureReason, 'invalid_password');
      expect(item.failureReasonDisplay, 'Invalid password');
      expect(item.failedAttemptsCount, 3);
    });

    test('handles string id by parsing to int', () {
      final item = LoginLogItem.fromJson({
        'id': '55',
        'timestamp': '2025-01-01T00:00:00Z',
        'event_type': 'login_success',
        'email_attempted': 'a@b.c',
        'ip_address': '127.0.0.1',
        'is_suspicious': false,
        'failed_attempts_count': 0,
      });

      expect(item.id, 55);
    });

    test('handles string failed_attempts_count', () {
      final item = LoginLogItem.fromJson({
        'id': 1,
        'timestamp': '2025-01-01T00:00:00Z',
        'event_type': 'login_failed',
        'email_attempted': 'x@y.z',
        'ip_address': '0.0.0.0',
        'is_suspicious': false,
        'failed_attempts_count': '7',
      });

      expect(item.failedAttemptsCount, 7);
    });

    test('defaults for missing optional string fields', () {
      final item = LoginLogItem.fromJson({
        'id': 1,
        'ip_address': '1.2.3.4',
      });

      expect(item.timestampIso, '');
      expect(item.eventType, '');
      expect(item.emailAttempted, '');
      expect(item.location, isNull);
      expect(item.browser, isNull);
      expect(item.deviceType, isNull);
      expect(item.userAgent, isNull);
    });
  });

  group('LoginLogItem.isSuspicious', () {
    test('is true only when JSON value is exactly true', () {
      final suspicious = LoginLogItem.fromJson({
        'id': 1,
        'ip_address': '1.1.1.1',
        'is_suspicious': true,
        'failed_attempts_count': 0,
      });
      expect(suspicious.isSuspicious, true);

      final notSuspicious = LoginLogItem.fromJson({
        'id': 2,
        'ip_address': '1.1.1.1',
        'is_suspicious': 1,
        'failed_attempts_count': 0,
      });
      expect(notSuspicious.isSuspicious, false);
    });
  });
}
