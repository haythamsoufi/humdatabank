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
  });

  factory Assignment.fromJson(Map<String, dynamic> json) {
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
    };
  }

  bool get isOverdue {
    if (dueDate == null) return false;
    return DateTime.now().isAfter(dueDate!) && status != 'Approved';
  }

  bool get isCurrent {
    return status != 'Requires Revision' &&
        (statusTimestamp == null ||
            DateTime.now().difference(statusTimestamp!).inDays < 30);
  }
}
