import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/admin/session_log_item.dart';

void main() {
  group('SessionLogItem.fromJson', () {
    test('parses full data with nested user map', () {
      final json = {
        'session_id': 'sess-abc-123',
        'session_start': '2025-03-10T09:00:00Z',
        'session_end': '2025-03-10T11:00:00Z',
        'last_activity': '2025-03-10T10:55:00Z',
        'duration_minutes': 120,
        'page_views': 45,
        'activity_count': 30,
        'is_active': false,
        'device_type': 'Desktop',
        'browser': 'Firefox 115',
        'operating_system': 'Windows 11',
        'ip_address': '192.168.0.100',
        'user_agent': 'Mozilla/5.0 ...',
        'user': {
          'name': 'Bob Jones',
          'email': 'bob@example.org',
        },
      };

      final item = SessionLogItem.fromJson(json);

      expect(item.sessionId, 'sess-abc-123');
      expect(item.sessionStartIso, '2025-03-10T09:00:00Z');
      expect(item.sessionEndIso, '2025-03-10T11:00:00Z');
      expect(item.lastActivityIso, '2025-03-10T10:55:00Z');
      expect(item.durationMinutes, 120);
      expect(item.pageViews, 45);
      expect(item.activityCount, 30);
      expect(item.isActive, false);
      expect(item.deviceType, 'Desktop');
      expect(item.browser, 'Firefox 115');
      expect(item.operatingSystem, 'Windows 11');
      expect(item.ipAddress, '192.168.0.100');
      expect(item.userAgent, 'Mozilla/5.0 ...');
      expect(item.userName, 'Bob Jones');
      expect(item.userEmail, 'bob@example.org');
    });

    test('parses minimal data with defaults', () {
      final item = SessionLogItem.fromJson(<String, dynamic>{});

      expect(item.sessionId, '');
      expect(item.sessionStartIso, isNull);
      expect(item.sessionEndIso, isNull);
      expect(item.lastActivityIso, isNull);
      expect(item.durationMinutes, isNull);
      expect(item.pageViews, 0);
      expect(item.activityCount, 0);
      expect(item.isActive, false);
      expect(item.deviceType, isNull);
      expect(item.browser, isNull);
      expect(item.operatingSystem, isNull);
      expect(item.ipAddress, isNull);
      expect(item.userAgent, isNull);
      expect(item.userName, isNull);
      expect(item.userEmail, isNull);
    });

    test('extracts userName and userEmail from nested user map', () {
      final item = SessionLogItem.fromJson({
        'session_id': 'sess-xyz',
        'page_views': 10,
        'activity_count': 5,
        'is_active': true,
        'user': {'name': 'Carol', 'email': 'carol@test.io'},
      });

      expect(item.userName, 'Carol');
      expect(item.userEmail, 'carol@test.io');
      expect(item.isActive, true);
    });

    test('leaves userName/userEmail null when user key is absent', () {
      final item = SessionLogItem.fromJson({
        'session_id': 'sess-no-user',
        'page_views': 0,
        'activity_count': 0,
        'is_active': false,
      });

      expect(item.userName, isNull);
      expect(item.userEmail, isNull);
    });

    test('leaves userName/userEmail null when user is not a Map', () {
      final item = SessionLogItem.fromJson({
        'session_id': 'sess-bad-user',
        'user': 'not-a-map',
        'page_views': 0,
        'activity_count': 0,
        'is_active': false,
      });

      expect(item.userName, isNull);
      expect(item.userEmail, isNull);
    });

    test('handles string page_views and activity_count', () {
      final item = SessionLogItem.fromJson({
        'session_id': 'sess-str',
        'page_views': '12',
        'activity_count': '8',
        'is_active': false,
      });

      expect(item.pageViews, 12);
      expect(item.activityCount, 8);
    });

    test('handles string duration_minutes', () {
      final item = SessionLogItem.fromJson({
        'session_id': 'sess-dur',
        'duration_minutes': '90',
        'page_views': 0,
        'activity_count': 0,
        'is_active': false,
      });

      expect(item.durationMinutes, 90);
    });

    test('isActive is true only when JSON value is exactly true', () {
      final active = SessionLogItem.fromJson({
        'session_id': 's1',
        'is_active': true,
        'page_views': 0,
        'activity_count': 0,
      });
      expect(active.isActive, true);

      final inactive = SessionLogItem.fromJson({
        'session_id': 's2',
        'is_active': 1,
        'page_views': 0,
        'activity_count': 0,
      });
      expect(inactive.isActive, false);
    });
  });
}
