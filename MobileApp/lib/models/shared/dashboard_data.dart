import 'assignment.dart';
import 'entity.dart';

/// Dashboard data model
class DashboardData {
  final List<Assignment> currentAssignments;
  final List<Assignment> pastAssignments;
  final List<Entity> entities;
  final Entity? selectedEntity;
  final DateTime? timestamp;

  DashboardData({
    required this.currentAssignments,
    required this.pastAssignments,
    required this.entities,
    this.selectedEntity,
    this.timestamp,
  });
}
