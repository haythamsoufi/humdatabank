import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/notification.dart';

void main() {
  group('NotificationActor.fromJson', () {
    test('parses fully-populated JSON correctly', () {
      final json = {
        'id': 7,
        'name': 'Alice Smith',
        'initials': 'AS',
        'profile_color': '#e11d48',
      };

      final actor = NotificationActor.fromJson(json);

      expect(actor.id, 7);
      expect(actor.name, 'Alice Smith');
      expect(actor.initials, 'AS');
      expect(actor.profileColor, '#e11d48');
    });

    test('returns defaults when json is null', () {
      final actor = NotificationActor.fromJson(null);

      expect(actor.id, 0);
      expect(actor.name, '');
      expect(actor.initials, '?');
      expect(actor.profileColor, '#64748b');
    });

    test('applies defaults for missing fields', () {
      final actor = NotificationActor.fromJson(<String, dynamic>{});

      expect(actor.id, 0);
      expect(actor.name, '');
      expect(actor.initials, '?');
      expect(actor.profileColor, '#64748b');
    });
  });

  group('NotificationActor.toJson', () {
    test('round-trip preserves all fields', () {
      final original = {
        'id': 3,
        'name': 'Bob',
        'initials': 'B',
        'profile_color': '#0ea5e9',
      };

      final actor = NotificationActor.fromJson(original);
      final json = actor.toJson();

      expect(json['id'], 3);
      expect(json['name'], 'Bob');
      expect(json['initials'], 'B');
      expect(json['profile_color'], '#0ea5e9');
    });
  });

  group('Notification.fromJson', () {
    test('parses all fields populated', () {
      final json = {
        'id': 42,
        'title': 'New Assignment',
        'message': 'You have a new form to fill.',
        'notification_type': 'assignment',
        'is_read': true,
        'created_at': '2025-06-15T10:30:00.000Z',
        'metadata': {'form_id': 5},
        'related_url': '/forms/5',
        'priority': 'high',
        'notification_type_label': 'Assignment',
        'entity_name': 'Health Survey',
        'entity_type': 'form',
        'primary_is_message': true,
        'actor': {
          'id': 1,
          'name': 'Admin',
          'initials': 'A',
          'profile_color': '#ff0000',
        },
        'actor_action_icon': 'fa-clipboard',
        'icon': 'fas fa-tasks',
      };

      final n = Notification.fromJson(json);

      expect(n.id, 42);
      expect(n.title, 'New Assignment');
      expect(n.message, 'You have a new form to fill.');
      expect(n.type, 'assignment');
      expect(n.isRead, true);
      expect(n.createdAt, DateTime.parse('2025-06-15T10:30:00.000Z'));
      expect(n.metadata, {'form_id': 5});
      expect(n.relatedUrl, '/forms/5');
      expect(n.priority, 'high');
      expect(n.notificationTypeLabel, 'Assignment');
      expect(n.entityName, 'Health Survey');
      expect(n.entityType, 'form');
      expect(n.primaryIsMessage, true);
      expect(n.actor, isNotNull);
      expect(n.actor!.name, 'Admin');
      expect(n.actorActionIcon, 'fa-clipboard');
      expect(n.iconClass, 'fas fa-tasks');
    });

    test('applies defaults for missing/minimal fields', () {
      final n = Notification.fromJson(<String, dynamic>{});

      expect(n.id, 0);
      expect(n.title, '');
      expect(n.message, '');
      expect(n.type, 'info');
      expect(n.isRead, false);
      expect(n.priority, 'normal');
      expect(n.primaryIsMessage, false);
      expect(n.actor, isNull);
      expect(n.actorActionIcon, isNull);
      expect(n.iconClass, isNull);
      expect(n.metadata, isEmpty);
    });

    test('prefers notification_type over type key', () {
      final n = Notification.fromJson({
        'notification_type': 'approval',
        'type': 'info',
      });

      expect(n.type, 'approval');
    });

    test('falls back to type key when notification_type is absent', () {
      final n = Notification.fromJson({'type': 'deadline'});
      expect(n.type, 'deadline');
    });

    test('prefers related_url over redirect_url', () {
      final n = Notification.fromJson({
        'related_url': '/a',
        'redirect_url': '/b',
      });
      expect(n.relatedUrl, '/a');
    });

    test('falls back to redirect_url when related_url is absent', () {
      final n = Notification.fromJson({'redirect_url': '/fallback'});
      expect(n.relatedUrl, '/fallback');
    });
  });

  group('Notification.toJson', () {
    test('produces expected keys', () {
      final n = Notification(
        id: 1,
        title: 'T',
        message: 'M',
        type: 'info',
        isRead: false,
        createdAt: DateTime.utc(2025, 1, 1),
      );
      final json = n.toJson();

      expect(json['id'], 1);
      expect(json['title'], 'T');
      expect(json['message'], 'M');
      expect(json['type'], 'info');
      expect(json['is_read'], false);
      expect(json['created_at'], '2025-01-01T00:00:00.000Z');
      expect(json['priority'], 'normal');
      expect(json.containsKey('actor'), true);
      expect(json['actor'], isNull);
    });
  });

  group('Notification.copyWith', () {
    late Notification base;

    setUp(() {
      base = Notification(
        id: 10,
        title: 'Base',
        message: 'msg',
        type: 'info',
        isRead: false,
        createdAt: DateTime.utc(2025, 6, 1),
        priority: 'normal',
      );
    });

    test('returns identical copy when no overrides given', () {
      final copy = base.copyWith();

      expect(copy.id, base.id);
      expect(copy.title, base.title);
      expect(copy.message, base.message);
      expect(copy.type, base.type);
      expect(copy.isRead, base.isRead);
      expect(copy.priority, base.priority);
    });

    test('overrides only specified fields', () {
      final copy = base.copyWith(isRead: true, priority: 'high');

      expect(copy.isRead, true);
      expect(copy.priority, 'high');
      expect(copy.id, base.id);
      expect(copy.title, base.title);
    });
  });

  group('Notification.isHighPriority', () {
    Notification withPriority(String p) => Notification(
          id: 1,
          title: '',
          message: '',
          type: 'info',
          isRead: false,
          createdAt: DateTime.now(),
          priority: p,
        );

    test('returns true for high', () {
      expect(withPriority('high').isHighPriority, true);
    });

    test('returns true for urgent', () {
      expect(withPriority('urgent').isHighPriority, true);
    });

    test('returns false for normal', () {
      expect(withPriority('normal').isHighPriority, false);
    });
  });

  group('Notification.icon', () {
    Notification withType(String t) => Notification(
          id: 1,
          title: '',
          message: '',
          type: t,
          isRead: false,
          createdAt: DateTime.now(),
        );

    test('returns clipboard for assignment', () {
      expect(withType('assignment').icon, '📋');
    });

    test('returns check for approval', () {
      expect(withType('approval').icon, '✅');
    });

    test('returns warning for revision', () {
      expect(withType('revision').icon, '⚠️');
    });

    test('returns clock for deadline', () {
      expect(withType('deadline').icon, '⏰');
    });

    test('returns bell for unknown type', () {
      expect(withType('other').icon, '🔔');
    });
  });
}
