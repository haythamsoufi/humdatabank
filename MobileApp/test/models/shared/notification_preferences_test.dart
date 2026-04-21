import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/notification_preferences.dart';

void main() {
  group('NotificationPreferences.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'email_notifications': false,
        'notification_types_enabled': ['assignment', 'approval'],
        'notification_frequency': 'weekly',
        'digest_day': 'monday',
        'digest_time': '09:00',
        'sound_enabled': true,
        'push_notifications': false,
        'push_notification_types_enabled': ['deadline'],
      };

      final p = NotificationPreferences.fromJson(json);

      expect(p.emailNotifications, false);
      expect(p.notificationTypesEnabled, ['assignment', 'approval']);
      expect(p.notificationFrequency, 'weekly');
      expect(p.digestDay, 'monday');
      expect(p.digestTime, '09:00');
      expect(p.soundEnabled, true);
      expect(p.pushNotifications, false);
      expect(p.pushNotificationTypesEnabled, ['deadline']);
    });

    test('applies defaults for missing fields', () {
      final p = NotificationPreferences.fromJson(<String, dynamic>{});

      expect(p.emailNotifications, true);
      expect(p.notificationTypesEnabled, isEmpty);
      expect(p.notificationFrequency, 'instant');
      expect(p.digestDay, isNull);
      expect(p.digestTime, isNull);
      expect(p.soundEnabled, false);
      expect(p.pushNotifications, true);
      expect(p.pushNotificationTypesEnabled, isEmpty);
    });

    test('notification_types_enabled defaults to empty list when null', () {
      final p = NotificationPreferences.fromJson({
        'notification_types_enabled': null,
      });
      expect(p.notificationTypesEnabled, isEmpty);
    });

    test('push_notification_types_enabled defaults to empty list when null',
        () {
      final p = NotificationPreferences.fromJson({
        'push_notification_types_enabled': null,
      });
      expect(p.pushNotificationTypesEnabled, isEmpty);
    });
  });

  group('NotificationPreferences.toJson', () {
    test('produces expected keys and values', () {
      final p = NotificationPreferences(
        emailNotifications: true,
        notificationTypesEnabled: ['assignment'],
        notificationFrequency: 'daily',
        digestDay: 'friday',
        digestTime: '18:00',
        soundEnabled: true,
        pushNotifications: true,
        pushNotificationTypesEnabled: ['approval', 'revision'],
      );
      final json = p.toJson();

      expect(json['email_notifications'], true);
      expect(json['notification_types_enabled'], ['assignment']);
      expect(json['notification_frequency'], 'daily');
      expect(json['digest_day'], 'friday');
      expect(json['digest_time'], '18:00');
      expect(json['sound_enabled'], true);
      expect(json['push_notifications'], true);
      expect(json['push_notification_types_enabled'], ['approval', 'revision']);
    });

    test('includes null digest fields when unset', () {
      final p = NotificationPreferences(
        emailNotifications: true,
        notificationTypesEnabled: [],
        notificationFrequency: 'instant',
        soundEnabled: false,
        pushNotifications: true,
        pushNotificationTypesEnabled: [],
      );
      final json = p.toJson();

      expect(json.containsKey('digest_day'), true);
      expect(json['digest_day'], isNull);
      expect(json.containsKey('digest_time'), true);
      expect(json['digest_time'], isNull);
    });
  });

  group('NotificationPreferences round-trip', () {
    test('fromJson → toJson → fromJson preserves all fields', () {
      final original = {
        'email_notifications': false,
        'notification_types_enabled': ['deadline', 'revision'],
        'notification_frequency': 'weekly',
        'digest_day': 'tuesday',
        'digest_time': '08:30',
        'sound_enabled': true,
        'push_notifications': false,
        'push_notification_types_enabled': ['assignment'],
      };

      final p1 = NotificationPreferences.fromJson(original);
      final json = p1.toJson();
      final p2 = NotificationPreferences.fromJson(json);

      expect(p2.emailNotifications, p1.emailNotifications);
      expect(p2.notificationTypesEnabled, p1.notificationTypesEnabled);
      expect(p2.notificationFrequency, p1.notificationFrequency);
      expect(p2.digestDay, p1.digestDay);
      expect(p2.digestTime, p1.digestTime);
      expect(p2.soundEnabled, p1.soundEnabled);
      expect(p2.pushNotifications, p1.pushNotifications);
      expect(
          p2.pushNotificationTypesEnabled, p1.pushNotificationTypesEnabled);
    });
  });

  group('NotificationPreferences.copyWith', () {
    late NotificationPreferences base;

    setUp(() {
      base = NotificationPreferences(
        emailNotifications: true,
        notificationTypesEnabled: ['assignment'],
        notificationFrequency: 'instant',
        digestDay: null,
        digestTime: null,
        soundEnabled: false,
        pushNotifications: true,
        pushNotificationTypesEnabled: ['deadline'],
      );
    });

    test('returns identical copy when no overrides given', () {
      final copy = base.copyWith();

      expect(copy.emailNotifications, base.emailNotifications);
      expect(copy.notificationTypesEnabled, base.notificationTypesEnabled);
      expect(copy.notificationFrequency, base.notificationFrequency);
      expect(copy.soundEnabled, base.soundEnabled);
      expect(copy.pushNotifications, base.pushNotifications);
    });

    test('overrides only specified fields', () {
      final copy = base.copyWith(
        emailNotifications: false,
        notificationFrequency: 'weekly',
        digestDay: 'wednesday',
      );

      expect(copy.emailNotifications, false);
      expect(copy.notificationFrequency, 'weekly');
      expect(copy.digestDay, 'wednesday');
      expect(copy.soundEnabled, base.soundEnabled);
      expect(copy.pushNotifications, base.pushNotifications);
      expect(copy.notificationTypesEnabled, base.notificationTypesEnabled);
    });

    test('can replace list fields', () {
      final copy = base.copyWith(
        notificationTypesEnabled: ['approval', 'revision'],
        pushNotificationTypesEnabled: [],
      );

      expect(copy.notificationTypesEnabled, ['approval', 'revision']);
      expect(copy.pushNotificationTypesEnabled, isEmpty);
    });
  });
}
