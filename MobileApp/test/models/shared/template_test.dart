import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/template.dart';

void main() {
  group('Template.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'id': 10,
        'name': 'Health Survey',
        'localized_name': 'Enquête de santé',
        'add_to_self_report': true,
        'owned_by_user_id': 5,
        'owned_by_user_name': 'Alice',
        'created_at': '2025-03-15T08:00:00.000Z',
        'data_count': 42,
      };

      final t = Template.fromJson(json);

      expect(t.id, 10);
      expect(t.name, 'Health Survey');
      expect(t.localizedName, 'Enquête de santé');
      expect(t.addToSelfReport, true);
      expect(t.ownedByUserId, 5);
      expect(t.ownedByUserName, 'Alice');
      expect(t.createdAt, DateTime.parse('2025-03-15T08:00:00.000Z'));
      expect(t.dataCount, 42);
    });

    test('applies defaults for missing fields', () {
      final t = Template.fromJson(<String, dynamic>{});

      expect(t.id, 0);
      expect(t.name, '');
      expect(t.addToSelfReport, false);
      expect(t.localizedName, isNull);
      expect(t.ownedByUserId, isNull);
      expect(t.ownedByUserName, isNull);
      expect(t.dataCount, isNull);
    });

    test('leaves optional fields null when absent', () {
      final t = Template.fromJson({
        'id': 1,
        'name': 'Minimal',
        'add_to_self_report': false,
        'created_at': '2025-01-01T00:00:00.000Z',
      });

      expect(t.localizedName, isNull);
      expect(t.ownedByUserId, isNull);
      expect(t.ownedByUserName, isNull);
      expect(t.dataCount, isNull);
    });
  });

  group('Template.toJson', () {
    test('produces expected keys and values', () {
      final t = Template(
        id: 7,
        name: 'Survey',
        localizedName: 'Encuesta',
        addToSelfReport: true,
        ownedByUserId: 3,
        ownedByUserName: 'Bob',
        createdAt: DateTime.utc(2025, 6, 1),
        dataCount: 10,
      );
      final json = t.toJson();

      expect(json['id'], 7);
      expect(json['name'], 'Survey');
      expect(json['localized_name'], 'Encuesta');
      expect(json['add_to_self_report'], true);
      expect(json['owned_by_user_id'], 3);
      expect(json['owned_by_user_name'], 'Bob');
      expect(json['created_at'], '2025-06-01T00:00:00.000Z');
      expect(json['data_count'], 10);
    });

    test('includes null for unset optional fields', () {
      final t = Template(
        id: 1,
        name: 'X',
        addToSelfReport: false,
        createdAt: DateTime.utc(2025),
      );
      final json = t.toJson();

      expect(json.containsKey('localized_name'), true);
      expect(json['localized_name'], isNull);
      expect(json.containsKey('data_count'), true);
      expect(json['data_count'], isNull);
    });
  });

  group('Template round-trip (fromJson → toJson → fromJson)', () {
    test('full round-trip preserves all fields', () {
      final original = {
        'id': 99,
        'name': 'RT Template',
        'localized_name': 'Modèle RT',
        'add_to_self_report': true,
        'owned_by_user_id': 8,
        'owned_by_user_name': 'Carol',
        'created_at': '2025-09-01T12:00:00.000Z',
        'data_count': 55,
      };

      final t1 = Template.fromJson(original);
      final json = t1.toJson();
      final t2 = Template.fromJson(json);

      expect(t2.id, t1.id);
      expect(t2.name, t1.name);
      expect(t2.localizedName, t1.localizedName);
      expect(t2.addToSelfReport, t1.addToSelfReport);
      expect(t2.ownedByUserId, t1.ownedByUserId);
      expect(t2.ownedByUserName, t1.ownedByUserName);
      expect(t2.dataCount, t1.dataCount);
    });
  });

  group('Template.displayName', () {
    test('returns localizedName when set', () {
      final t = Template(
        id: 1,
        name: 'English Name',
        localizedName: 'Nom français',
        addToSelfReport: false,
        createdAt: DateTime.now(),
      );
      expect(t.displayName, 'Nom français');
    });

    test('falls back to name when localizedName is null', () {
      final t = Template(
        id: 1,
        name: 'English Name',
        addToSelfReport: false,
        createdAt: DateTime.now(),
      );
      expect(t.displayName, 'English Name');
    });
  });
}
