import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/document.dart';

void main() {
  group('Document.fromJson', () {
    test('parses a fully-populated JSON correctly', () {
      final json = {
        'id': 20,
        'file_name': 'report_q1.pdf',
        'document_type': 'annual_report',
        'language': 'fr',
        'year': 2024,
        'status': 'approved',
        'country_name': 'Lebanon',
        'uploaded_by_name': 'Alice',
        'uploaded_at': '2024-07-15T14:30:00.000Z',
        'assignment_period': '2024 Q1',
        'is_public': true,
      };

      final d = Document.fromJson(json);

      expect(d.id, 20);
      expect(d.fileName, 'report_q1.pdf');
      expect(d.documentType, 'annual_report');
      expect(d.language, 'fr');
      expect(d.year, 2024);
      expect(d.status, 'approved');
      expect(d.countryName, 'Lebanon');
      expect(d.uploadedByName, 'Alice');
      expect(d.uploadedAt, DateTime.parse('2024-07-15T14:30:00.000Z'));
      expect(d.assignmentPeriod, '2024 Q1');
      expect(d.isPublic, true);
    });

    test('leaves optional fields null when absent', () {
      final d = Document.fromJson({'id': 1});

      expect(d.fileName, isNull);
      expect(d.documentType, isNull);
      expect(d.language, isNull);
      expect(d.year, isNull);
      expect(d.status, isNull);
      expect(d.countryName, isNull);
      expect(d.uploadedByName, isNull);
      expect(d.uploadedAt, isNull);
      expect(d.assignmentPeriod, isNull);
    });

    test('isPublic defaults to false when absent', () {
      final d = Document.fromJson({'id': 2});
      expect(d.isPublic, false);
    });

    test('isPublic is true when explicitly set', () {
      final d = Document.fromJson({'id': 3, 'is_public': true});
      expect(d.isPublic, true);
    });

    test('isPublic is false when explicitly set to false', () {
      final d = Document.fromJson({'id': 4, 'is_public': false});
      expect(d.isPublic, false);
    });

    test('parses uploadedAt as null when key is missing', () {
      final d = Document.fromJson({'id': 5, 'file_name': 'x.pdf'});
      expect(d.uploadedAt, isNull);
    });
  });
}
