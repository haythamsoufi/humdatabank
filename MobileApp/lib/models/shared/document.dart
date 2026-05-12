class Document {
  final int id;
  final String? fileName;
  final String? documentType;
  final String? language;
  final int? year;
  final String? status;
  final String? countryName;
  final String? uploadedByName;
  final DateTime? uploadedAt;
  final String? assignmentPeriod;
  final bool isPublic;

  Document({
    required this.id,
    this.fileName,
    this.documentType,
    this.language,
    this.year,
    this.status,
    this.countryName,
    this.uploadedByName,
    this.uploadedAt,
    this.assignmentPeriod,
    this.isPublic = false,
  });

  factory Document.fromJson(Map<String, dynamic> json) {
    return Document(
      id: json['id'] as int,
      fileName: json['file_name'] as String?,
      documentType: json['document_type'] as String?,
      language: json['language'] as String?,
      year: json['year'] as int?,
      status: json['status'] as String?,
      countryName: json['country_name'] as String?,
      uploadedByName: json['uploaded_by_name'] as String?,
      uploadedAt: json['uploaded_at'] != null
          ? DateTime.parse(json['uploaded_at'] as String)
          : null,
      assignmentPeriod: json['assignment_period'] as String?,
      isPublic: json['is_public'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'file_name': fileName,
      'document_type': documentType,
      'language': language,
      'year': year,
      'status': status,
      'country_name': countryName,
      'uploaded_by_name': uploadedByName,
      'uploaded_at': uploadedAt?.toUtc().toIso8601String(),
      'assignment_period': assignmentPeriod,
      'is_public': isPublic,
    };
  }
}
