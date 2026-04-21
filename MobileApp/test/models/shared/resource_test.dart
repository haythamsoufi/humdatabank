import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/resource.dart';

void main() {
  group('Resource.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'id': 15,
        'title': 'Annual Report 2024',
        'resource_type': 'publication',
        'language': 'en',
        'publication_date': '2024-12-01T00:00:00.000Z',
        'description': 'Yearly humanitarian overview.',
        'thumbnail_url': 'https://cdn.example.org/thumb.png',
        'is_published': true,
      };

      final r = Resource.fromJson(json);

      expect(r.id, 15);
      expect(r.title, 'Annual Report 2024');
      expect(r.resourceType, 'publication');
      expect(r.language, 'en');
      expect(r.publicationDate, DateTime.parse('2024-12-01T00:00:00.000Z'));
      expect(r.description, 'Yearly humanitarian overview.');
      expect(r.thumbnailUrl, 'https://cdn.example.org/thumb.png');
      expect(r.isPublished, true);
    });

    test('leaves optional fields null when absent', () {
      final r = Resource.fromJson({'id': 1});

      expect(r.title, isNull);
      expect(r.resourceType, isNull);
      expect(r.language, isNull);
      expect(r.publicationDate, isNull);
      expect(r.description, isNull);
      expect(r.thumbnailUrl, isNull);
    });

    test('uses default_title when title is absent', () {
      final r = Resource.fromJson({
        'id': 2,
        'default_title': 'Fallback Title',
      });

      expect(r.title, 'Fallback Title');
    });

    test('prefers title over default_title', () {
      final r = Resource.fromJson({
        'id': 3,
        'title': 'Primary',
        'default_title': 'Fallback',
      });

      expect(r.title, 'Primary');
    });

    test('uses default_description when description is absent', () {
      final r = Resource.fromJson({
        'id': 4,
        'default_description': 'Fallback Desc',
      });

      expect(r.description, 'Fallback Desc');
    });

    test('prefers description over default_description', () {
      final r = Resource.fromJson({
        'id': 5,
        'description': 'Primary Desc',
        'default_description': 'Fallback Desc',
      });

      expect(r.description, 'Primary Desc');
    });

    test('isPublished defaults to true when absent', () {
      final r = Resource.fromJson({'id': 6});
      expect(r.isPublished, true);
    });

    test('isPublished is false when explicitly set', () {
      final r = Resource.fromJson({'id': 7, 'is_published': false});
      expect(r.isPublished, false);
    });

    test('parses subcategory when present', () {
      final r = Resource.fromJson({
        'id': 8,
        'title': 'Doc',
        'subcategory': {'id': 3, 'name': 'Annual', 'display_order': 1},
      });
      expect(r.subcategory, isNotNull);
      expect(r.subcategory!.id, 3);
      expect(r.subcategory!.name, 'Annual');
      expect(r.subcategory!.displayOrder, 1);
    });

    test('subcategory is null when absent', () {
      final r = Resource.fromJson({'id': 9, 'title': 'No sub'});
      expect(r.subcategory, isNull);
    });
  });
}
