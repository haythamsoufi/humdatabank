import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';

void main() {
  group('Assignment.fromJson', () {
    test('parses fully-populated JSON', () {
      final json = {
        'id': 10,
        'name': 'Q1 Report',
        'status': 'In Progress',
        'due_date': '2026-06-30T00:00:00.000',
        'status_timestamp': '2026-04-01T12:00:00.000',
        'completion_rate': 0.75,
        'template_name': 'Annual Template',
        'period_name': '2026-Q1',
        'is_public': true,
        'public_submission_count': 5,
        'last_modified_user_name': 'Alice',
        'is_effectively_closed': true,
      };

      final a = Assignment.fromJson(json);

      expect(a.id, 10);
      expect(a.name, 'Q1 Report');
      expect(a.status, 'In Progress');
      expect(a.dueDate, isA<DateTime>());
      expect(a.dueDate!.year, 2026);
      expect(a.dueDate!.month, 6);
      expect(a.statusTimestamp, isA<DateTime>());
      expect(a.completionRate, 0.75);
      expect(a.templateName, 'Annual Template');
      expect(a.periodName, '2026-Q1');
      expect(a.isPublic, true);
      expect(a.publicSubmissionCount, 5);
      expect(a.lastModifiedUserName, 'Alice');
      expect(a.isEffectivelyClosed, true);
    });

    test('applies defaults for empty JSON', () {
      final a = Assignment.fromJson(<String, dynamic>{});

      expect(a.id, 0);
      expect(a.name, '');
      expect(a.status, 'Pending');
      expect(a.dueDate, isNull);
      expect(a.statusTimestamp, isNull);
      expect(a.completionRate, 0.0);
      expect(a.templateName, isNull);
      expect(a.isPublic, false);
      expect(a.isEffectivelyClosed, false);
    });

    test('coerces integer completion_rate to double', () {
      final a = Assignment.fromJson({
        'id': 1,
        'name': 'x',
        'completion_rate': 1,
      });

      expect(a.completionRate, isA<double>());
      expect(a.completionRate, 1.0);
    });

    test('is_effectively_closed defaults to false for non-boolean values', () {
      final a = Assignment.fromJson({
        'id': 1,
        'name': 'x',
        'is_effectively_closed': 'yes',
      });

      expect(a.isEffectivelyClosed, false);
    });
  });

  group('Assignment.toJson', () {
    test('serialises all fields', () {
      final a = Assignment(
        id: 3,
        name: 'Test',
        status: 'Approved',
        dueDate: DateTime(2026, 12, 31),
        completionRate: 1.0,
        isPublic: true,
        publicSubmissionCount: 10,
      );

      final json = a.toJson();

      expect(json['id'], 3);
      expect(json['name'], 'Test');
      expect(json['status'], 'Approved');
      expect(json['due_date'], contains('2026-12-31'));
      expect(json['completion_rate'], 1.0);
      expect(json['is_public'], true);
      expect(json['public_submission_count'], 10);
    });

    test('null dates serialise as null', () {
      final a = Assignment(id: 1, name: 'x', status: 'Pending', completionRate: 0);
      final json = a.toJson();

      expect(json['due_date'], isNull);
      expect(json['status_timestamp'], isNull);
    });
  });

  group('Assignment round-trip', () {
    test('fromJson → toJson → fromJson preserves data', () {
      final original = {
        'id': 7,
        'name': 'Round Trip',
        'status': 'Submitted',
        'due_date': '2026-09-15T00:00:00.000',
        'completion_rate': 0.5,
        'template_name': 'T1',
        'period_name': 'P1',
        'is_public': false,
        'is_effectively_closed': false,
      };

      final a1 = Assignment.fromJson(original);
      final a2 = Assignment.fromJson(a1.toJson());

      expect(a2.id, a1.id);
      expect(a2.name, a1.name);
      expect(a2.status, a1.status);
      expect(a2.dueDate, a1.dueDate);
      expect(a2.completionRate, a1.completionRate);
      expect(a2.templateName, a1.templateName);
      expect(a2.isPublic, a1.isPublic);
      expect(a2.isEffectivelyClosed, a1.isEffectivelyClosed);
    });
  });

  group('Assignment.isOverdue', () {
    test('returns false when dueDate is null', () {
      final a = Assignment(id: 1, name: 'x', status: 'Pending', completionRate: 0);
      expect(a.isOverdue, false);
    });

    test('returns false when dueDate is in the future', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'Pending',
        completionRate: 0,
        dueDate: DateTime.now().add(const Duration(days: 30)),
      );
      expect(a.isOverdue, false);
    });

    test('returns true when dueDate is in the past and status is not Approved', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'In Progress',
        completionRate: 0,
        dueDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      expect(a.isOverdue, true);
    });

    test('returns false when dueDate is past but status is Approved', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'Approved',
        completionRate: 1.0,
        dueDate: DateTime.now().subtract(const Duration(days: 1)),
      );
      expect(a.isOverdue, false);
    });
  });

  group('Assignment submission/approval detail visibility', () {
    test('hides submitted/approved rows when reopened to In Progress', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'In Progress',
        completionRate: 0,
        submittedByUserName: 'Bob',
        approvedByUserName: 'Admin',
      );
      expect(a.showSubmittedByDetails, false);
      expect(a.showApprovedByDetails, false);
    });

    test('shows submitted and approved when status is Approved', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'Approved',
        completionRate: 1,
        submittedByUserName: 'Bob',
        approvedByUserName: 'Admin',
      );
      expect(a.showSubmittedByDetails, true);
      expect(a.showApprovedByDetails, true);
    });

    test('shows submitted but not approved for Requires Revision', () {
      final a = Assignment(
        id: 1,
        name: 'x',
        status: 'Requires Revision',
        completionRate: 0.5,
        submittedByUserName: 'Bob',
      );
      expect(a.showSubmittedByDetails, true);
      expect(a.showApprovedByDetails, false);
    });
  });

  group('Assignment.isEffectivelyClosed', () {
    test('reflects the parsed value', () {
      final open = Assignment.fromJson({
        'id': 1,
        'name': 'x',
        'is_effectively_closed': false,
      });
      final closed = Assignment.fromJson({
        'id': 2,
        'name': 'y',
        'is_effectively_closed': true,
      });

      expect(open.isEffectivelyClosed, false);
      expect(closed.isEffectivelyClosed, true);
    });
  });
}
