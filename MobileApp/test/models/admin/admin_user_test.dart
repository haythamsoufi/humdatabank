import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/admin/admin_user.dart';

void main() {
  group('CountryEntity', () {
    test('fromJson parses all fields', () {
      final entity = CountryEntity.fromJson({
        'id': 7,
        'name': 'Lebanon',
        'code': 'LB',
      });

      expect(entity.id, 7);
      expect(entity.name, 'Lebanon');
      expect(entity.code, 'LB');
    });

    test('fromJson applies defaults for missing fields', () {
      final entity = CountryEntity.fromJson(<String, dynamic>{});

      expect(entity.id, 0);
      expect(entity.name, '');
      expect(entity.code, isNull);
    });

    test('toJson produces expected map', () {
      final entity = CountryEntity(id: 3, name: 'Jordan', code: 'JO');
      final json = entity.toJson();

      expect(json, {'id': 3, 'name': 'Jordan', 'code': 'JO'});
    });

    test('toJson includes null code', () {
      final entity = CountryEntity(id: 1, name: 'Syria');
      final json = entity.toJson();

      expect(json['code'], isNull);
    });
  });

  group('AdminUser.fromJson', () {
    test('parses full data including countries and entityCounts', () {
      final json = {
        'id': 10,
        'email': 'admin@example.org',
        'name': 'Admin User',
        'title': 'Director',
        'role': 'admin',
        'chatbot_enabled': true,
        'profile_color': '#00ff00',
        'country_ids': [1, 2],
        'active': true,
        'countries': [
          {'id': 1, 'name': 'Lebanon', 'code': 'LB'},
          {'id': 2, 'name': 'Jordan', 'code': 'JO'},
        ],
        'entity_counts': {'branches': 3, 'divisions': 1},
      };

      final user = AdminUser.fromJson(json);

      expect(user.id, 10);
      expect(user.email, 'admin@example.org');
      expect(user.name, 'Admin User');
      expect(user.title, 'Director');
      expect(user.role, 'admin');
      expect(user.chatbotEnabled, true);
      expect(user.profileColor, '#00ff00');
      expect(user.countryIds, [1, 2]);
      expect(user.active, true);
      expect(user.countries, hasLength(2));
      expect(user.countries![0].name, 'Lebanon');
      expect(user.countries![1].code, 'JO');
      expect(user.entityCounts, {'branches': 3, 'divisions': 1});
    });

    test('parses minimal data with defaults', () {
      final user = AdminUser.fromJson(<String, dynamic>{});

      expect(user.id, 0);
      expect(user.email, '');
      expect(user.role, 'focal_point');
      expect(user.active, true);
      expect(user.countries, isNull);
      expect(user.entityCounts, isNull);
      expect(user.chatbotEnabled, false);
    });

    test('leaves optional fields null when absent', () {
      final user = AdminUser.fromJson({'id': 5, 'email': 'x@y.z', 'active': false});

      expect(user.name, isNull);
      expect(user.title, isNull);
      expect(user.profileColor, isNull);
      expect(user.countryIds, isNull);
      expect(user.countries, isNull);
      expect(user.entityCounts, isNull);
      expect(user.active, false);
    });
  });

  group('AdminUser.toJson', () {
    test('includes parent User fields plus active, countries, entityCounts', () {
      final user = AdminUser(
        id: 1,
        email: 'test@test.com',
        name: 'Test',
        role: 'admin',
        chatbotEnabled: true,
        active: true,
        countries: [CountryEntity(id: 5, name: 'Iraq', code: 'IQ')],
        entityCounts: {'branches': 2},
      );

      final json = user.toJson();

      expect(json['id'], 1);
      expect(json['email'], 'test@test.com');
      expect(json['name'], 'Test');
      expect(json['role'], 'admin');
      expect(json['chatbot_enabled'], true);
      expect(json['active'], true);
      expect(json['countries'], hasLength(1));
      expect(json['countries'][0]['name'], 'Iraq');
      expect(json['entity_counts'], {'branches': 2});
    });

    test('omits countries and entityCounts when null', () {
      final user = AdminUser(
        id: 2,
        email: 'min@test.com',
        role: 'focal_point',
        active: false,
      );

      final json = user.toJson();

      expect(json['active'], false);
      expect(json.containsKey('countries'), false);
      expect(json.containsKey('entity_counts'), false);
    });
  });

  group('AdminUser.roleDisplayName', () {
    test('returns "Admin" for admin role', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'admin', active: true);
      expect(user.roleDisplayName, 'Admin');
    });

    test('returns "Focal Point" for focal_point role', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'focal_point', active: true);
      expect(user.roleDisplayName, 'Focal Point');
    });

    test('returns "System Manager" for system_manager role', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'system_manager', active: true);
      expect(user.roleDisplayName, 'System Manager');
    });

    test('title-cases unknown roles with underscores', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'data_entry_clerk', active: true);
      expect(user.roleDisplayName, 'Data Entry Clerk');
    });
  });

  group('AdminUser.entitiesSummary', () {
    test('returns "Global" for system_manager', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'system_manager', active: true);
      expect(user.entitiesSummary, 'Global');
    });

    test('returns single country name when one country assigned', () {
      final user = AdminUser(
        id: 1,
        email: 'a@b.c',
        role: 'admin',
        active: true,
        countries: [CountryEntity(id: 1, name: 'Lebanon')],
      );
      expect(user.entitiesSummary, 'Lebanon');
    });

    test('returns count string when multiple countries assigned', () {
      final user = AdminUser(
        id: 1,
        email: 'a@b.c',
        role: 'focal_point',
        active: true,
        countries: [
          CountryEntity(id: 1, name: 'Lebanon'),
          CountryEntity(id: 2, name: 'Jordan'),
          CountryEntity(id: 3, name: 'Iraq'),
        ],
      );
      expect(user.entitiesSummary, '3 countries');
    });

    test('includes entityCounts in summary', () {
      final user = AdminUser(
        id: 1,
        email: 'a@b.c',
        role: 'admin',
        active: true,
        countries: [CountryEntity(id: 1, name: 'Lebanon')],
        entityCounts: {'branches': 2, 'divisions': 1},
      );
      expect(user.entitiesSummary, 'Lebanon, 2 branches, 1 divisions');
    });

    test('skips entity counts with zero value', () {
      final user = AdminUser(
        id: 1,
        email: 'a@b.c',
        role: 'admin',
        active: true,
        countries: [CountryEntity(id: 1, name: 'Syria')],
        entityCounts: {'branches': 0, 'divisions': 3},
      );
      expect(user.entitiesSummary, 'Syria, 3 divisions');
    });

    test('returns "-" when no countries and no entityCounts', () {
      final user = AdminUser(id: 1, email: 'a@b.c', role: 'focal_point', active: true);
      expect(user.entitiesSummary, '-');
    });

    test('returns "-" when countries and entityCounts are empty', () {
      final user = AdminUser(
        id: 1,
        email: 'a@b.c',
        role: 'admin',
        active: true,
        countries: [],
        entityCounts: {},
      );
      expect(user.entitiesSummary, '-');
    });
  });
}
