import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/indicator_bank/sector.dart';

void main() {
  group('SubSector', () {
    test('fromJson parses all fields', () {
      final json = {
        'id': 10,
        'name': 'Primary Health Care',
        'localized_name': 'Soins de santé primaires',
        'description': 'PHC programs',
        'localized_description': 'Programmes de SSP',
        'logo_url': 'https://example.com/phc.png',
        'display_order': 2,
        'sector_id': 1,
      };

      final sub = SubSector.fromJson(json);

      expect(sub.id, 10);
      expect(sub.name, 'Primary Health Care');
      expect(sub.localizedName, 'Soins de santé primaires');
      expect(sub.description, 'PHC programs');
      expect(sub.localizedDescription, 'Programmes de SSP');
      expect(sub.logoUrl, 'https://example.com/phc.png');
      expect(sub.displayOrder, 2);
      expect(sub.sectorId, 1);
    });

    test('fromJson with minimal data applies defaults', () {
      final sub = SubSector.fromJson({'id': 1, 'name': 'Nutrition'});

      expect(sub.id, 1);
      expect(sub.name, 'Nutrition');
      expect(sub.localizedName, isNull);
      expect(sub.description, isNull);
      expect(sub.localizedDescription, isNull);
      expect(sub.logoUrl, isNull);
      expect(sub.displayOrder, 0);
      expect(sub.sectorId, isNull);
    });

    test('displayName returns localizedName when present', () {
      final sub = SubSector(id: 1, name: 'Nutrition', localizedName: 'التغذية');
      expect(sub.displayName, 'التغذية');
    });

    test('displayName falls back to name', () {
      final sub = SubSector(id: 1, name: 'Nutrition');
      expect(sub.displayName, 'Nutrition');
    });

    test('displayDescription returns localizedDescription when present', () {
      final sub = SubSector(
        id: 1,
        name: 'X',
        description: 'English desc',
        localizedDescription: 'French desc',
      );
      expect(sub.displayDescription, 'French desc');
    });

    test('displayDescription falls back to description then empty string', () {
      final sub1 = SubSector(id: 1, name: 'X', description: 'English desc');
      expect(sub1.displayDescription, 'English desc');

      final sub2 = SubSector(id: 2, name: 'Y');
      expect(sub2.displayDescription, '');
    });
  });

  group('Sector', () {
    test('fromJson parses all fields including subsectors', () {
      final json = {
        'id': 1,
        'name': 'Health',
        'localized_name': 'Santé',
        'description': 'Health programs',
        'localized_description': 'Programmes de santé',
        'logo_url': 'https://example.com/health.png',
        'display_order': 1,
        'subsectors': [
          {'id': 10, 'name': 'PHC', 'sector_id': 1},
          {'id': 11, 'name': 'Mental Health', 'sector_id': 1},
        ],
      };

      final sector = Sector.fromJson(json);

      expect(sector.id, 1);
      expect(sector.name, 'Health');
      expect(sector.localizedName, 'Santé');
      expect(sector.description, 'Health programs');
      expect(sector.localizedDescription, 'Programmes de santé');
      expect(sector.logoUrl, 'https://example.com/health.png');
      expect(sector.displayOrder, 1);
      expect(sector.subsectors, hasLength(2));
      expect(sector.subsectors[0].name, 'PHC');
      expect(sector.subsectors[1].name, 'Mental Health');
    });

    test('fromJson without subsectors defaults to empty list', () {
      final sector = Sector.fromJson({'id': 2, 'name': 'WASH'});

      expect(sector.id, 2);
      expect(sector.name, 'WASH');
      expect(sector.subsectors, isEmpty);
      expect(sector.displayOrder, 0);
    });

    test('fromJson with explicit null subsectors defaults to empty list', () {
      final sector = Sector.fromJson({
        'id': 3,
        'name': 'Shelter',
        'subsectors': null,
      });

      expect(sector.subsectors, isEmpty);
    });

    test('displayName returns localizedName when present', () {
      final sector = Sector(id: 1, name: 'Health', localizedName: 'صحة');
      expect(sector.displayName, 'صحة');
    });

    test('displayName falls back to name', () {
      final sector = Sector(id: 1, name: 'Health');
      expect(sector.displayName, 'Health');
    });

    test('displayDescription returns localizedDescription when present', () {
      final sector = Sector(
        id: 1,
        name: 'Health',
        description: 'English',
        localizedDescription: 'Français',
      );
      expect(sector.displayDescription, 'Français');
    });

    test('displayDescription falls back to description then empty string', () {
      final s1 = Sector(id: 1, name: 'Health', description: 'Programs');
      expect(s1.displayDescription, 'Programs');

      final s2 = Sector(id: 2, name: 'WASH');
      expect(s2.displayDescription, '');
    });
  });
}
