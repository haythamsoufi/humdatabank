class AdminAssignment {
  final int id;
  final String periodName;
  final String? templateName;
  final int? templateId;
  final bool hasPublicUrl;
  final bool isPublicActive;
  final String? publicUrl;
  final int? publicSubmissionCount;

  AdminAssignment({
    required this.id,
    required this.periodName,
    this.templateName,
    this.templateId,
    required this.hasPublicUrl,
    required this.isPublicActive,
    this.publicUrl,
    this.publicSubmissionCount,
  });

  factory AdminAssignment.fromJson(Map<String, dynamic> json) {
    return AdminAssignment(
      id: json['id'] ?? 0,
      periodName: json['period_name'] ?? '',
      templateName: json['template_name'],
      templateId: json['template_id'],
      hasPublicUrl: json['has_public_url'] ?? false,
      isPublicActive: json['is_public_active'] ?? false,
      publicUrl: json['public_url'],
      publicSubmissionCount: json['public_submission_count'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'period_name': periodName,
      'template_name': templateName,
      'template_id': templateId,
      'has_public_url': hasPublicUrl,
      'is_public_active': isPublicActive,
      'public_url': publicUrl,
      'public_submission_count': publicSubmissionCount,
    };
  }
}
