import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/indicator.dart';

void main() {
  group('Indicator.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'id': 30,
        'name': 'People Reached',
        'type': 'numeric',
        'sector': 'Health',
        'sub_sector': 'Primary Care',
        'is_emergency': true,
        'is_archived': true,
        'description': 'Total number of people reached.',
      };

      final i = Indicator.fromJson(json);

      expect(i.id, 30);
      expect(i.name, 'People Reached');
      expect(i.type, 'numeric');
      expect(i.sector, 'Health');
      expect(i.subSector, 'Primary Care');
      expect(i.isEmergency, true);
      expect(i.isArchived, true);
      expect(i.description, 'Total number of people reached.');
    });

    test('leaves optional fields null when absent', () {
      final i = Indicator.fromJson({'id': 1});

      expect(i.name, isNull);
      expect(i.type, isNull);
      expect(i.sector, isNull);
      expect(i.subSector, isNull);
      expect(i.description, isNull);
    });

    test('isEmergency defaults to false', () {
      final i = Indicator.fromJson({'id': 2});
      expect(i.isEmergency, false);
    });

    test('isArchived defaults to false', () {
      final i = Indicator.fromJson({'id': 3});
      expect(i.isArchived, false);
    });

    test('boolean fields are true when explicitly set', () {
      final i = Indicator.fromJson({
        'id': 4,
        'is_emergency': true,
        'is_archived': true,
      });

      expect(i.isEmergency, true);
      expect(i.isArchived, true);
    });

    test('boolean fields are false when explicitly false', () {
      final i = Indicator.fromJson({
        'id': 5,
        'is_emergency': false,
        'is_archived': false,
      });

      expect(i.isEmergency, false);
      expect(i.isArchived, false);
    });
  });
}
