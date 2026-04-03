class Resource {
  final int id;
  final String? title;
  final String? resourceType;
  final String? language;
  final DateTime? publicationDate;
  final String? description;
  final String? thumbnailUrl;
  final bool isPublished;

  Resource({
    required this.id,
    this.title,
    this.resourceType,
    this.language,
    this.publicationDate,
    this.description,
    this.thumbnailUrl,
    this.isPublished = false,
  });

  factory Resource.fromJson(Map<String, dynamic> json) {
    return Resource(
      id: json['id'] as int,
      title: json['title'] as String? ?? json['default_title'] as String?,
      resourceType: json['resource_type'] as String?,
      language: json['language'] as String?,
      publicationDate: json['publication_date'] != null
          ? DateTime.parse(json['publication_date'] as String)
          : null,
      description: json['description'] as String? ??
          json['default_description'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      isPublished: json['is_published'] as bool? ?? true,
    );
  }
}
