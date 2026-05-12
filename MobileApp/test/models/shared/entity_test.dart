import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/entity.dart';

void main() {
  group('Entity.fromJson', () {
    test('parses fully-populated JSON', () {
      final json = {
        'entity_type': 'branch',
        'entity_id': 42,
        'name': 'East Branch',
        'display_name': 'East Branch Office',
        'country_id': 7,
        'country_name': 'Lebanon',
      };

      final entity = Entity.fromJson(json);

      expect(entity.entityType, 'branch');
      expect(entity.entityId, 42);
      expect(entity.name, 'East Branch');
      expect(entity.displayName, 'East Branch Office');
      expect(entity.countryId, 7);
      expect(entity.countryName, 'Lebanon');
    });

    test('applies defaults for missing fields', () {
      final entity = Entity.fromJson(<String, dynamic>{});

      expect(entity.entityType, 'country');
      expect(entity.entityId, 0);
      expect(entity.name, '');
      expect(entity.displayName, isNull);
      expect(entity.countryId, isNull);
      expect(entity.countryName, isNull);
    });

    test('handles partial JSON gracefully', () {
      final entity = Entity.fromJson({'entity_type': 'region', 'entity_id': 5});

      expect(entity.entityType, 'region');
      expect(entity.entityId, 5);
      expect(entity.name, '');
    });
  });

  group('Entity.toJson', () {
    test('produces expected map', () {
      final entity = Entity(
        entityType: 'country',
        entityId: 1,
        name: 'Syria',
        displayName: 'Syrian Arab Republic',
        countryId: 1,
        countryName: 'Syria',
      );

      final json = entity.toJson();

      expect(json['entity_type'], 'country');
      expect(json['entity_id'], 1);
      expect(json['name'], 'Syria');
      expect(json['display_name'], 'Syrian Arab Republic');
      expect(json['country_id'], 1);
      expect(json['country_name'], 'Syria');
    });

    test('includes null optional fields', () {
      final entity = Entity(entityType: 'country', entityId: 1, name: 'X');
      final json = entity.toJson();

      expect(json.containsKey('display_name'), true);
      expect(json['display_name'], isNull);
    });
  });

  group('Entity round-trip', () {
    test('fromJson → toJson → fromJson preserves data', () {
      final original = {
        'entity_type': 'branch',
        'entity_id': 99,
        'name': 'HQ',
        'display_name': 'Headquarters',
        'country_id': 3,
        'country_name': 'Jordan',
      };

      final e1 = Entity.fromJson(original);
      final e2 = Entity.fromJson(e1.toJson());

      expect(e2.entityType, e1.entityType);
      expect(e2.entityId, e1.entityId);
      expect(e2.name, e1.name);
      expect(e2.displayName, e1.displayName);
      expect(e2.countryId, e1.countryId);
      expect(e2.countryName, e1.countryName);
    });
  });

  group('Entity equality', () {
    test('two entities with same type and id are equal', () {
      final a = Entity(entityType: 'country', entityId: 1, name: 'A');
      final b = Entity(entityType: 'country', entityId: 1, name: 'B');

      expect(a, equals(b));
    });

    test('different entity types are not equal even with same id', () {
      final a = Entity(entityType: 'country', entityId: 1, name: 'A');
      final b = Entity(entityType: 'branch', entityId: 1, name: 'A');

      expect(a, isNot(equals(b)));
    });

    test('same type but different ids are not equal', () {
      final a = Entity(entityType: 'country', entityId: 1, name: 'A');
      final b = Entity(entityType: 'country', entityId: 2, name: 'A');

      expect(a, isNot(equals(b)));
    });

    test('identical instance is equal to itself', () {
      final a = Entity(entityType: 'country', entityId: 1, name: 'A');
      expect(a, equals(a));
    });
  });

  group('Entity.hashCode', () {
    test('equal entities have the same hashCode', () {
      final a = Entity(entityType: 'country', entityId: 5, name: 'X');
      final b = Entity(entityType: 'country', entityId: 5, name: 'Y');

      expect(a.hashCode, b.hashCode);
    });

    test('can be used in a Set for deduplication', () {
      final entities = {
        Entity(entityType: 'country', entityId: 1, name: 'A'),
        Entity(entityType: 'country', entityId: 1, name: 'B'),
        Entity(entityType: 'branch', entityId: 1, name: 'C'),
      };

      expect(entities.length, 2);
    });
  });

  group('Entity computed properties', () {
    test('displayLabel returns displayName when present', () {
      final entity = Entity(
        entityType: 'country',
        entityId: 1,
        name: 'Short',
        displayName: 'Full Display Name',
      );
      expect(entity.displayLabel, 'Full Display Name');
    });

    test('displayLabel falls back to name when displayName is null', () {
      final entity = Entity(entityType: 'country', entityId: 1, name: 'Short');
      expect(entity.displayLabel, 'Short');
    });

    test('selectionKey combines type and id', () {
      final entity = Entity(entityType: 'branch', entityId: 42, name: 'X');
      expect(entity.selectionKey, 'branch:42');
    });
  });
}
