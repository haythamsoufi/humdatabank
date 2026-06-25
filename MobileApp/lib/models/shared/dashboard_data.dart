import 'assignment.dart';
import 'entity.dart';
import 'focal_point_contact.dart';

/// Dashboard data model
class DashboardData {
  final List<Assignment> currentAssignments;
  final List<Assignment> pastAssignments;
  final List<Entity> entities;
  final Entity? selectedEntity;
  final List<FocalPointContact> nsFocalPoints;
  final List<FocalPointContact> orgFocalPoints;
  final DateTime? timestamp;

  DashboardData({
    required this.currentAssignments,
    required this.pastAssignments,
    required this.entities,
    this.selectedEntity,
    this.nsFocalPoints = const [],
    this.orgFocalPoints = const [],
    this.timestamp,
  });
}
