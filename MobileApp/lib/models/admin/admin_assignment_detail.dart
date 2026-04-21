/// One row under an assignment (country, NS branch, etc.) from mobile GET detail.
class AdminAssignmentEntityRow {
  final int id;
  final String entityType;
  final int entityId;
  final String displayName;
  final String status;
  final String? dueDateIso;
  final bool isPublicAvailable;
  final String? submittedAtIso;
  final String? statusTimestampIso;

  const AdminAssignmentEntityRow({
    required this.id,
    required this.entityType,
    required this.entityId,
    required this.displayName,
    required this.status,
    this.dueDateIso,
    required this.isPublicAvailable,
    this.submittedAtIso,
    this.statusTimestampIso,
  });

  factory AdminAssignmentEntityRow.fromJson(Map<String, dynamic> json) {
    final idRaw = json['id'];
    final entityIdRaw = json['entity_id'];
    return AdminAssignmentEntityRow(
      id: idRaw is int ? idRaw : (idRaw is num ? idRaw.toInt() : 0),
      entityType: json['entity_type']?.toString() ?? '',
      entityId: entityIdRaw is int
          ? entityIdRaw
          : (entityIdRaw is num ? entityIdRaw.toInt() : 0),
      displayName: json['display_name']?.toString() ?? '',
      status: json['status']?.toString() ?? '',
      dueDateIso: json['due_date']?.toString(),
      isPublicAvailable: json['is_public_available'] == true,
      submittedAtIso: json['submitted_at']?.toString(),
      statusTimestampIso: json['status_timestamp']?.toString(),
    );
  }
}

/// Full assignment payload from `GET .../admin/content/assignments/<id>`.
class AdminAssignmentDetail {
  final int id;
  final String periodName;
  final String? templateName;
  final int? templateId;
  final String? assignedAtIso;
  final bool isActive;
  final bool isClosed;
  final bool isEffectivelyClosed;
  final String? expiryDateIso;
  final String? earliestDueDateIso;
  final bool hasMultipleDueDates;
  final bool hasPublicUrl;
  final bool isPublicActive;
  final String? publicUrl;
  final int? publicSubmissionCount;
  final List<AdminAssignmentEntityRow> entities;

  AdminAssignmentDetail({
    required this.id,
    required this.periodName,
    this.templateName,
    this.templateId,
    this.assignedAtIso,
    required this.isActive,
    required this.isClosed,
    required this.isEffectivelyClosed,
    this.expiryDateIso,
    this.earliestDueDateIso,
    required this.hasMultipleDueDates,
    required this.hasPublicUrl,
    required this.isPublicActive,
    this.publicUrl,
    this.publicSubmissionCount,
    required this.entities,
  });

  factory AdminAssignmentDetail.fromJson(Map<String, dynamic> json) {
    final rawEntities = json['entities'];
    final list = rawEntities is List<dynamic>
        ? rawEntities
        : rawEntities is List
            ? List<dynamic>.from(rawEntities)
            : const <dynamic>[];
    final idRaw = json['id'];
    final tidRaw = json['template_id'];
    final pscRaw = json['public_submission_count'];
    return AdminAssignmentDetail(
      id: idRaw is int ? idRaw : (idRaw is num ? idRaw.toInt() : 0),
      periodName: json['period_name']?.toString() ?? '',
      templateName: json['template_name']?.toString(),
      templateId: tidRaw is int
          ? tidRaw
          : (tidRaw is num ? tidRaw.toInt() : null),
      assignedAtIso: json['assigned_at']?.toString(),
      isActive: json['is_active'] == true,
      isClosed: json['is_closed'] == true,
      isEffectivelyClosed: json['is_effectively_closed'] == true,
      expiryDateIso: json['expiry_date']?.toString(),
      earliestDueDateIso: json['earliest_due_date']?.toString(),
      hasMultipleDueDates: json['has_multiple_due_dates'] == true,
      hasPublicUrl: json['has_public_url'] == true,
      isPublicActive: json['is_public_active'] == true,
      publicUrl: json['public_url']?.toString(),
      publicSubmissionCount: pscRaw is int
          ? pscRaw
          : (pscRaw is num ? pscRaw.toInt() : null),
      entities: list
          .whereType<Map>()
          .map((e) => AdminAssignmentEntityRow.fromJson(
                Map<String, dynamic>.from(e),
              ))
          .toList(),
    );
  }
}
