import 'resource_subcategory.dart';

class Resource {
  final int id;
  final String? title;
  final String? resourceType;
  final String? language;
  final DateTime? publicationDate;
  final String? description;
  final String? thumbnailUrl;
  final String? fileUrl;
  final List<String> availableLanguages;

  /// Languages that have an actual uploaded document file.
  /// Subset of [availableLanguages] — use this when choosing which language
  /// file to open so you don't try to download a translation that has no file.
  final List<String> fileLanguages;

  /// Optional admin-defined subgroup (publications series, etc.).
  final ResourceSubcategory? subcategory;

  final bool isPublished;

  Resource({
    required this.id,
    this.title,
    this.resourceType,
    this.language,
    this.publicationDate,
    this.description,
    this.thumbnailUrl,
    this.fileUrl,
    this.availableLanguages = const [],
    this.fileLanguages = const [],
    this.subcategory,
    this.isPublished = false,
  });

  factory Resource.fromJson(Map<String, dynamic> json) {
    return Resource(
      id: json['id'] as int,
      title: json['title'] as String? ?? json['default_title'] as String?,
      resourceType: json['resource_type'] as String?,
      language: json['language'] as String?,
      publicationDate: json['publication_date'] != null
          ? DateTime.tryParse(json['publication_date'] as String)
          : null,
      description: json['description'] as String? ??
          json['default_description'] as String?,
      thumbnailUrl: json['thumbnail_url'] as String?,
      fileUrl: json['file_url'] as String?,
      availableLanguages: (json['available_languages'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      fileLanguages: (json['file_languages'] as List<dynamic>?)
              ?.map((e) => e.toString().toLowerCase())
              .toList() ??
          const [],
      subcategory: json['subcategory'] != null
          ? ResourceSubcategory.fromJson(
              json['subcategory'] as Map<String, dynamic>,
            )
          : null,
      isPublished: json['is_published'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'default_title': title,
      'resource_type': resourceType,
      'language': language,
      'publication_date': publicationDate?.toUtc().toIso8601String().split('T').first,
      'description': description,
      'thumbnail_url': thumbnailUrl,
      'file_url': fileUrl,
      'available_languages': availableLanguages,
      'file_languages': fileLanguages,
      'subcategory': subcategory?.toJson(),
      'is_published': isPublished,
    };
  }
}
