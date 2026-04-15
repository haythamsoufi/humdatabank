import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/admin/admin_assignment.dart';

void main() {
  group('AdminAssignment.fromJson', () {
    test('parses full data correctly', () {
      final json = {
        'id': 42,
        'period_name': 'Q1 2025',
        'template_name': 'Health Assessment',
        'template_id': 7,
        'has_public_url': true,
        'is_public_active': true,
        'public_url': 'https://example.com/form/abc123',
        'public_submission_count': 15,
      };

      final assignment = AdminAssignment.fromJson(json);

      expect(assignment.id, 42);
      expect(assignment.periodName, 'Q1 2025');
      expect(assignment.templateName, 'Health Assessment');
      expect(assignment.templateId, 7);
      expect(assignment.hasPublicUrl, true);
      expect(assignment.isPublicActive, true);
      expect(assignment.publicUrl, 'https://example.com/form/abc123');
      expect(assignment.publicSubmissionCount, 15);
    });

    test('parses minimal data with defaults', () {
      final assignment = AdminAssignment.fromJson(<String, dynamic>{});

      expect(assignment.id, 0);
      expect(assignment.periodName, '');
      expect(assignment.templateName, isNull);
      expect(assignment.templateId, isNull);
      expect(assignment.hasPublicUrl, false);
      expect(assignment.isPublicActive, false);
      expect(assignment.publicUrl, isNull);
      expect(assignment.publicSubmissionCount, isNull);
    });

    test('handles partial data with some optional fields present', () {
      final assignment = AdminAssignment.fromJson({
        'id': 5,
        'period_name': 'Annual 2024',
        'template_id': 12,
      });

      expect(assignment.id, 5);
      expect(assignment.periodName, 'Annual 2024');
      expect(assignment.templateName, isNull);
      expect(assignment.templateId, 12);
      expect(assignment.hasPublicUrl, false);
    });
  });

  group('AdminAssignment.toJson', () {
    test('produces expected keys and values for full assignment', () {
      final assignment = AdminAssignment(
        id: 10,
        periodName: 'H2 2025',
        templateName: 'WASH Survey',
        templateId: 3,
        hasPublicUrl: true,
        isPublicActive: false,
        publicUrl: 'https://example.com/pub/xyz',
        publicSubmissionCount: 8,
      );

      final json = assignment.toJson();

      expect(json['id'], 10);
      expect(json['period_name'], 'H2 2025');
      expect(json['template_name'], 'WASH Survey');
      expect(json['template_id'], 3);
      expect(json['has_public_url'], true);
      expect(json['is_public_active'], false);
      expect(json['public_url'], 'https://example.com/pub/xyz');
      expect(json['public_submission_count'], 8);
    });

    test('includes null for unset optional fields', () {
      final assignment = AdminAssignment(
        id: 1,
        periodName: 'Q2 2025',
        hasPublicUrl: false,
        isPublicActive: false,
      );

      final json = assignment.toJson();

      expect(json['template_name'], isNull);
      expect(json['template_id'], isNull);
      expect(json['public_url'], isNull);
      expect(json['public_submission_count'], isNull);
    });
  });

  group('AdminAssignment round-trip', () {
    test('fromJson → toJson → fromJson preserves all fields', () {
      final original = {
        'id': 99,
        'period_name': 'FY 2026',
        'template_name': 'Protection',
        'template_id': 20,
        'has_public_url': true,
        'is_public_active': true,
        'public_url': 'https://example.com/pub/rt',
        'public_submission_count': 42,
      };

      final a1 = AdminAssignment.fromJson(original);
      final json = a1.toJson();
      final a2 = AdminAssignment.fromJson(json);

      expect(a2.id, a1.id);
      expect(a2.periodName, a1.periodName);
      expect(a2.templateName, a1.templateName);
      expect(a2.templateId, a1.templateId);
      expect(a2.hasPublicUrl, a1.hasPublicUrl);
      expect(a2.isPublicActive, a1.isPublicActive);
      expect(a2.publicUrl, a1.publicUrl);
      expect(a2.publicSubmissionCount, a1.publicSubmissionCount);
    });
  });
}
