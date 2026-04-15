import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/dashboard_data.dart';
import 'package:hum_databank_app/models/shared/entity.dart';

void main() {
  group('DashboardData constructor', () {
    test('creates instance with empty lists', () {
      final data = DashboardData(
        currentAssignments: [],
        pastAssignments: [],
        entities: [],
      );

      expect(data.currentAssignments, isEmpty);
      expect(data.pastAssignments, isEmpty);
      expect(data.entities, isEmpty);
      expect(data.selectedEntity, isNull);
      expect(data.timestamp, isNull);
    });

    test('creates instance with populated assignments', () {
      final current = [
        Assignment(id: 1, name: 'Current 1', status: 'In Progress', completionRate: 0.5),
        Assignment(id: 2, name: 'Current 2', status: 'Pending', completionRate: 0.0),
      ];
      final past = [
        Assignment(id: 3, name: 'Past 1', status: 'Approved', completionRate: 1.0),
      ];

      final data = DashboardData(
        currentAssignments: current,
        pastAssignments: past,
        entities: [],
      );

      expect(data.currentAssignments, hasLength(2));
      expect(data.pastAssignments, hasLength(1));
      expect(data.currentAssignments.first.name, 'Current 1');
      expect(data.pastAssignments.first.status, 'Approved');
    });

    test('creates instance with entities', () {
      final entities = [
        Entity(entityType: 'country', entityId: 1, name: 'Lebanon'),
        Entity(entityType: 'branch', entityId: 2, name: 'Beirut Office'),
      ];

      final data = DashboardData(
        currentAssignments: [],
        pastAssignments: [],
        entities: entities,
      );

      expect(data.entities, hasLength(2));
      expect(data.entities.first.name, 'Lebanon');
      expect(data.entities.last.entityType, 'branch');
    });

    test('stores selectedEntity when provided', () {
      final entity = Entity(entityType: 'country', entityId: 1, name: 'Jordan');

      final data = DashboardData(
        currentAssignments: [],
        pastAssignments: [],
        entities: [entity],
        selectedEntity: entity,
      );

      expect(data.selectedEntity, isNotNull);
      expect(data.selectedEntity!.name, 'Jordan');
      expect(data.selectedEntity, equals(entity));
    });

    test('stores timestamp when provided', () {
      final ts = DateTime(2026, 4, 7, 12, 0);

      final data = DashboardData(
        currentAssignments: [],
        pastAssignments: [],
        entities: [],
        timestamp: ts,
      );

      expect(data.timestamp, isNotNull);
      expect(data.timestamp!.year, 2026);
      expect(data.timestamp!.month, 4);
    });

    test('selectedEntity can differ from entities list', () {
      final selected = Entity(entityType: 'country', entityId: 99, name: 'Other');

      final data = DashboardData(
        currentAssignments: [],
        pastAssignments: [],
        entities: [Entity(entityType: 'country', entityId: 1, name: 'Lebanon')],
        selectedEntity: selected,
      );

      expect(data.selectedEntity!.entityId, 99);
      expect(data.entities.first.entityId, 1);
    });
  });

  group('DashboardData with realistic data', () {
    test('mixed current and past assignments with entity selection', () {
      final entity = Entity(entityType: 'country', entityId: 5, name: 'Iraq');
      final now = DateTime.now();

      final data = DashboardData(
        currentAssignments: [
          Assignment(
            id: 1,
            name: 'Active Report',
            status: 'In Progress',
            completionRate: 0.3,
            dueDate: now.add(const Duration(days: 10)),
          ),
        ],
        pastAssignments: [
          Assignment(
            id: 2,
            name: 'Old Report',
            status: 'Approved',
            completionRate: 1.0,
            dueDate: now.subtract(const Duration(days: 90)),
          ),
        ],
        entities: [entity],
        selectedEntity: entity,
        timestamp: now,
      );

      expect(data.currentAssignments.first.isOverdue, false);
      expect(data.pastAssignments.first.completionRate, 1.0);
      expect(data.selectedEntity, equals(entity));
      expect(data.timestamp, isNotNull);
    });
  });
}
