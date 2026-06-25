class Assignment {
  final int id;
  final String name;
  final String status;
  final DateTime? dueDate;
  final DateTime? statusTimestamp;
  final double completionRate;
  final String? templateName;
  final String? periodName;
  final bool isPublic;
  final int? publicSubmissionCount;
  final String? lastModifiedUserName;
  final DateTime? assignedAt;
  final List<String> contributorNames;
  final String? submittedByUserName;
  final DateTime? submittedAt;
  final String? approvedByUserName;
  final DateTime? latestPublicSubmissionAt;
  /// Matches AssignedForm.is_effectively_closed (dashboard Enter Data / reopen rules).
  final bool isEffectivelyClosed;

  /// Server timestamp of the published form template version ([FormTemplateVersion.updated_at]).
  /// Used to detect outdated offline bundles vs the live form definition.
  final DateTime? formDefinitionUpdatedAt;

  Assignment({
    required this.id,
    required this.name,
    required this.status,
    this.dueDate,
    this.statusTimestamp,
    required this.completionRate,
    this.templateName,
    this.periodName,
    this.isPublic = false,
    this.publicSubmissionCount,
    this.lastModifiedUserName,
    this.assignedAt,
    this.contributorNames = const [],
    this.submittedByUserName,
    this.submittedAt,
    this.approvedByUserName,
    this.latestPublicSubmissionAt,
    this.isEffectivelyClosed = false,
    this.formDefinitionUpdatedAt,
  });

  factory Assignment.fromJson(Map<String, dynamic> json) {
    final rawContributors = json['contributor_names'];
    final List<String> contributors = [];
    if (rawContributors is List) {
      for (final e in rawContributors) {
        final s = e?.toString().trim() ?? '';
        if (s.isNotEmpty) {
          contributors.add(s);
        }
      }
    }
    return Assignment(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      status: json['status'] ?? 'Pending',
      dueDate:
          json['due_date'] != null ? DateTime.parse(json['due_date']) : null,
      statusTimestamp: json['status_timestamp'] != null
          ? DateTime.parse(json['status_timestamp'])
          : null,
      completionRate: (json['completion_rate'] ?? 0.0).toDouble(),
      templateName: json['template_name'],
      periodName: json['period_name'],
      isPublic: json['is_public'] ?? false,
      publicSubmissionCount: json['public_submission_count'],
      lastModifiedUserName: json['last_modified_user_name'],
      assignedAt: json['assigned_at'] != null
          ? DateTime.parse(json['assigned_at'])
          : null,
      contributorNames: contributors,
      submittedByUserName: json['submitted_by_user_name'],
      submittedAt: json['submitted_at'] != null
          ? DateTime.parse(json['submitted_at'])
          : null,
      approvedByUserName: json['approved_by_user_name'],
      latestPublicSubmissionAt: json['latest_public_submission_at'] != null
          ? DateTime.parse(json['latest_public_submission_at'])
          : null,
      isEffectivelyClosed: json['is_effectively_closed'] == true,
      formDefinitionUpdatedAt: json['form_definition_updated_at'] != null
          ? DateTime.tryParse(json['form_definition_updated_at'].toString())
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'status': status,
      'due_date': dueDate?.toIso8601String(),
      'status_timestamp': statusTimestamp?.toIso8601String(),
      'completion_rate': completionRate,
      'template_name': templateName,
      'period_name': periodName,
      'is_public': isPublic,
      'public_submission_count': publicSubmissionCount,
      'last_modified_user_name': lastModifiedUserName,
      'assigned_at': assignedAt?.toIso8601String(),
      'contributor_names': contributorNames,
      'submitted_by_user_name': submittedByUserName,
      'submitted_at': submittedAt?.toIso8601String(),
      'approved_by_user_name': approvedByUserName,
      'latest_public_submission_at':
          latestPublicSubmissionAt?.toIso8601String(),
      'is_effectively_closed': isEffectivelyClosed,
      'form_definition_updated_at':
          formDefinitionUpdatedAt?.toUtc().toIso8601String(),
    };
  }

  /// Matches [dashboard.html] overdue rules: past due date and still awaiting submission.
  /// [status] is the raw API value (`pending`, `in_progress`, `approved`, …).
  bool get isOverdue {
    if (dueDate == null) return false;

    if (status == 'submitted' ||
        status == 'approved' ||
        status == 'requires_revision' ||
        status == 'sent_for_review') {
      return false;
    }

    final now = DateTime.now();
    final due = dueDate!.toLocal();
    final today = DateTime(now.year, now.month, now.day);
    final dueDay = DateTime(due.year, due.month, due.day);
    return dueDay.isBefore(today);
  }

  /// Submitted/approved accountability fields may remain on the record after reopen;
  /// only show them when the current status is still in that part of the workflow.
  bool get showSubmittedByDetails {
    switch (status.toLowerCase().trim()) {
      case 'submitted':
      case 'approved':
      case 'requires revision':
        return true;
      default:
        return false;
    }
  }

  bool get showApprovedByDetails {
    return status.toLowerCase().trim() == 'approved';
  }
}
