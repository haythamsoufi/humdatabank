import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/user.dart';

void main() {
  group('User.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'id': 42,
        'email': 'alice@example.org',
        'name': 'Alice',
        'title': 'Manager',
        'role': 'admin',
        'chatbot_enabled': true,
        'profile_color': '#ff0000',
        'country_ids': [1, 2, 3],
        'ai_beta_tester': true,
      };

      final user = User.fromJson(json);

      expect(user.id, 42);
      expect(user.email, 'alice@example.org');
      expect(user.name, 'Alice');
      expect(user.title, 'Manager');
      expect(user.role, 'admin');
      expect(user.chatbotEnabled, true);
      expect(user.profileColor, '#ff0000');
      expect(user.countryIds, [1, 2, 3]);
      expect(user.aiBetaTester, true);
    });

    test('applies defaults for missing required-like fields', () {
      final user = User.fromJson(<String, dynamic>{});

      expect(user.id, 0);
      expect(user.email, '');
      expect(user.role, 'focal_point');
      expect(user.chatbotEnabled, false);
      expect(user.aiBetaTester, false);
    });

    test('leaves optional fields null when absent', () {
      final user = User.fromJson({'id': 1, 'email': 'a@b.c', 'role': 'admin'});

      expect(user.name, isNull);
      expect(user.title, isNull);
      expect(user.profileColor, isNull);
      expect(user.countryIds, isNull);
    });

    test('handles country_ids as empty list', () {
      final user = User.fromJson({
        'id': 1,
        'email': 'a@b.c',
        'role': 'admin',
        'country_ids': <int>[],
      });

      expect(user.countryIds, isEmpty);
    });

    test('ai_beta_tester is false when value is non-boolean truthy', () {
      final user = User.fromJson({
        'id': 1,
        'email': 'x@y.z',
        'ai_beta_tester': 1,
      });

      expect(user.aiBetaTester, false);
    });
  });

  group('User.toJson', () {
    test('produces expected keys and values', () {
      final user = User(
        id: 5,
        email: 'bob@example.org',
        name: 'Bob',
        role: 'focal_point',
        chatbotEnabled: true,
        countryIds: [10],
        aiBetaTester: true,
      );

      final json = user.toJson();

      expect(json['id'], 5);
      expect(json['email'], 'bob@example.org');
      expect(json['name'], 'Bob');
      expect(json['chatbot_enabled'], true);
      expect(json['country_ids'], [10]);
      expect(json['ai_beta_tester'], true);
    });

    test('includes null values for unset optional fields', () {
      final user = User(id: 1, email: 'a@b.c', role: 'admin');
      final json = user.toJson();

      expect(json.containsKey('name'), true);
      expect(json['name'], isNull);
      expect(json.containsKey('title'), true);
      expect(json['title'], isNull);
    });
  });

  group('User round-trip (fromJson → toJson → fromJson)', () {
    test('full round-trip preserves all fields', () {
      final original = {
        'id': 99,
        'email': 'rt@test.io',
        'name': 'Round Trip',
        'title': 'Tester',
        'role': 'view_only',
        'chatbot_enabled': true,
        'profile_color': '#abcdef',
        'country_ids': [4, 5, 6],
        'ai_beta_tester': true,
      };

      final user1 = User.fromJson(original);
      final json = user1.toJson();
      final user2 = User.fromJson(json);

      expect(user2.id, user1.id);
      expect(user2.email, user1.email);
      expect(user2.name, user1.name);
      expect(user2.title, user1.title);
      expect(user2.role, user1.role);
      expect(user2.chatbotEnabled, user1.chatbotEnabled);
      expect(user2.profileColor, user1.profileColor);
      expect(user2.countryIds, user1.countryIds);
      expect(user2.aiBetaTester, user1.aiBetaTester);
    });

    test('round-trip with minimal fields', () {
      final user1 = User.fromJson(<String, dynamic>{});
      final user2 = User.fromJson(user1.toJson());

      expect(user2.id, user1.id);
      expect(user2.email, user1.email);
      expect(user2.role, user1.role);
    });
  });

  group('User.copyWith', () {
    late User base;

    setUp(() {
      base = User(
        id: 1,
        email: 'base@test.io',
        name: 'Base',
        role: 'admin',
        chatbotEnabled: false,
        countryIds: [1],
      );
    });

    test('returns identical copy when no overrides given', () {
      final copy = base.copyWith();

      expect(copy.id, base.id);
      expect(copy.email, base.email);
      expect(copy.name, base.name);
      expect(copy.role, base.role);
      expect(copy.chatbotEnabled, base.chatbotEnabled);
      expect(copy.countryIds, base.countryIds);
    });

    test('overrides only specified fields', () {
      final copy = base.copyWith(email: 'new@test.io', chatbotEnabled: true);

      expect(copy.email, 'new@test.io');
      expect(copy.chatbotEnabled, true);
      expect(copy.id, base.id);
      expect(copy.name, base.name);
    });

    test('can replace countryIds with a new list', () {
      final copy = base.copyWith(countryIds: [7, 8]);

      expect(copy.countryIds, [7, 8]);
      expect(base.countryIds, [1]);
    });
  });

  group('User.displayName', () {
    test('returns name when present', () {
      final user = User(id: 1, email: 'alice@example.org', name: 'Alice', role: 'admin');
      expect(user.displayName, 'Alice');
    });

    test('falls back to email prefix when name is null', () {
      final user = User(id: 1, email: 'alice@example.org', role: 'admin');
      expect(user.displayName, 'alice');
    });
  });
}
