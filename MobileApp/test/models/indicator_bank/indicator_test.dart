import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/indicator_bank/indicator.dart';

void main() {
  group('Indicator.fromJson', () {
    test('parses full data correctly', () {
      final json = {
        'id': 1,
        'name': 'Population Served',
        'localized_name': 'Population desservie',
        'definition': 'Total population served by NS',
        'localized_definition': 'Population totale desservie',
        'type': 'numeric',
        'localized_type': 'numérique',
        'unit': 'people',
        'localized_unit': 'personnes',
        'sector': 'Health',
        'sub_sector': 'Primary Health Care',
        'emergency': true,
        'related_programs': ['WASH', 'Shelter'],
        'archived': false,
      };

      final indicator = Indicator.fromJson(json);

      expect(indicator.id, 1);
      expect(indicator.name, 'Population Served');
      expect(indicator.localizedName, 'Population desservie');
      expect(indicator.definition, 'Total population served by NS');
      expect(indicator.localizedDefinition, 'Population totale desservie');
      expect(indicator.type, 'numeric');
      expect(indicator.localizedType, 'numérique');
      expect(indicator.unit, 'people');
      expect(indicator.localizedUnit, 'personnes');
      expect(indicator.sector, 'Health');
      expect(indicator.subSector, 'Primary Health Care');
      expect(indicator.emergency, true);
      expect(indicator.relatedPrograms, ['WASH', 'Shelter']);
      expect(indicator.archived, false);
    });

    test('parses minimal data with defaults', () {
      final indicator = Indicator.fromJson({'id': 5, 'name': 'Budget'});

      expect(indicator.id, 5);
      expect(indicator.name, 'Budget');
      expect(indicator.localizedName, isNull);
      expect(indicator.definition, isNull);
      expect(indicator.sector, isNull);
      expect(indicator.subSector, isNull);
      expect(indicator.emergency, isNull);
      expect(indicator.relatedPrograms, isNull);
      expect(indicator.archived, false);
    });

    test('defaults name to empty string when null in JSON', () {
      final indicator = Indicator.fromJson({'id': 9, 'name': null});
      expect(indicator.name, '');
    });

    test('parses sector and subSector as Map', () {
      final indicator = Indicator.fromJson({
        'id': 3,
        'name': 'Test',
        'sector': {'name': 'Health', 'localized_name': 'Santé'},
        'sub_sector': {'name': 'Nutrition', 'primary': 'Nutrition FR'},
      });

      expect(indicator.sector, isA<Map>());
      expect(indicator.subSector, isA<Map>());
    });
  });

  group('Indicator.displayName', () {
    test('returns localizedName when available', () {
      final indicator = Indicator(id: 1, name: 'Budget', localizedName: 'Presupuesto');
      expect(indicator.displayName, 'Presupuesto');
    });

    test('falls back to name when localizedName is null', () {
      final indicator = Indicator(id: 1, name: 'Budget');
      expect(indicator.displayName, 'Budget');
    });
  });

  group('Indicator.displaySector', () {
    test('returns string sector directly', () {
      final indicator = Indicator(id: 1, name: 'X', sector: 'Health');
      expect(indicator.displaySector, 'Health');
    });

    test('returns localized_name from map sector', () {
      final indicator = Indicator(
        id: 1,
        name: 'X',
        sector: {'name': 'Health', 'localized_name': 'Santé'},
      );
      expect(indicator.displaySector, 'Santé');
    });

    test('falls back to primary then name in map sector', () {
      final ind1 = Indicator(
        id: 1,
        name: 'X',
        sector: {'name': 'Health', 'primary': 'Health FR'},
      );
      expect(ind1.displaySector, 'Health FR');

      final ind2 = Indicator(
        id: 2,
        name: 'X',
        sector: {'name': 'Health'},
      );
      expect(ind2.displaySector, 'Health');
    });

    test('returns empty string when sector is null', () {
      final indicator = Indicator(id: 1, name: 'X');
      expect(indicator.displaySector, '');
    });

    test('calls toString for non-String non-Map sector', () {
      final indicator = Indicator(id: 1, name: 'X', sector: 42);
      expect(indicator.displaySector, '42');
    });
  });

  group('Indicator.displaySubSector', () {
    test('returns string subSector directly', () {
      final indicator = Indicator(id: 1, name: 'X', subSector: 'Nutrition');
      expect(indicator.displaySubSector, 'Nutrition');
    });

    test('returns localized_name from map subSector', () {
      final indicator = Indicator(
        id: 1,
        name: 'X',
        subSector: {'name': 'Nutrition', 'localized_name': 'Nutrición'},
      );
      expect(indicator.displaySubSector, 'Nutrición');
    });

    test('falls back to primary then name in map subSector', () {
      final ind1 = Indicator(
        id: 1,
        name: 'X',
        subSector: {'name': 'Nutrition', 'primary': 'Nutrition FR'},
      );
      expect(ind1.displaySubSector, 'Nutrition FR');

      final ind2 = Indicator(
        id: 2,
        name: 'X',
        subSector: {'name': 'Nutrition'},
      );
      expect(ind2.displaySubSector, 'Nutrition');
    });

    test('returns empty string when subSector is null', () {
      final indicator = Indicator(id: 1, name: 'X');
      expect(indicator.displaySubSector, '');
    });

    test('calls toString for non-String non-Map subSector', () {
      final indicator = Indicator(id: 1, name: 'X', subSector: true);
      expect(indicator.displaySubSector, 'true');
    });
  });

  group('Indicator display helpers', () {
    test('displayType prefers localizedType', () {
      final ind = Indicator(id: 1, name: 'X', type: 'number', localizedType: 'nombre');
      expect(ind.displayType, 'nombre');
    });

    test('displayUnit prefers localizedUnit', () {
      final ind = Indicator(id: 1, name: 'X', unit: 'kg', localizedUnit: 'كغ');
      expect(ind.displayUnit, 'كغ');
    });

    test('displayDefinition prefers localizedDefinition', () {
      final ind = Indicator(
        id: 1,
        name: 'X',
        definition: 'Count of items',
        localizedDefinition: 'Nombre d\'éléments',
      );
      expect(ind.displayDefinition, 'Nombre d\'éléments');
    });

    test('display helpers return empty string when both values are null', () {
      final ind = Indicator(id: 1, name: 'X');
      expect(ind.displayType, '');
      expect(ind.displayUnit, '');
      expect(ind.displayDefinition, '');
    });
  });
}
