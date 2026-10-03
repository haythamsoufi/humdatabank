import 'indicator_level_ids.dart';

class Indicator {
  final int id;
  final String? name;
  final String? type;
  final String? unit;
  final String? fdrsKpiCode;
  /// List view / legacy string labels when API returns flattened names.
  final String? sector;
  final String? subSector;
  /// Edit/detail: structured sector and sub-sector IDs.
  final IndicatorLevelIds? sectorLevels;
  final IndicatorLevelIds? subSectorLevels;
  final Map<String, String> nameTranslations;
  final Map<String, String> definitionTranslations;
  final List<String> translatableLanguages;
  final String? comments;
  final String? relatedPrograms;
  final bool isEmergency;
  final bool isArchived;
  final bool canArchive;
  final String? description;

  Indicator({
    required this.id,
    this.name,
    this.type,
    this.unit,
    this.fdrsKpiCode,
    this.sector,
    this.subSector,
    this.sectorLevels,
    this.subSectorLevels,
    Map<String, String>? nameTranslations,
    Map<String, String>? definitionTranslations,
    List<String>? translatableLanguages,
    this.comments,
    this.relatedPrograms,
    this.isEmergency = false,
    this.isArchived = false,
    this.canArchive = true,
    this.description,
  })  : nameTranslations = nameTranslations ?? const {},
        definitionTranslations = definitionTranslations ?? const {},
        translatableLanguages = translatableLanguages ?? const [];

  static Map<String, String> _stringMap(dynamic raw) {
    if (raw == null || raw is! Map) return {};
    return raw.map(
      (k, v) => MapEntry(
        '$k',
        v == null ? '' : (v is String ? v : '$v'),
      ),
    );
  }

  static List<String> _stringList(dynamic raw) {
    if (raw == null || raw is! List) return [];
    return raw
        .map((e) => e == null ? '' : '$e')
        .where((e) => e.isNotEmpty)
        .toList();
  }

  factory Indicator.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final parsedId = rawId is int ? rawId : int.tryParse('$rawId') ?? 0;

    final rawSector = json['sector'];
    final rawSubSector = json['sub_sector'];

    String? sectorStr;
    String? subStr;
    IndicatorLevelIds? secLevels;
    IndicatorLevelIds? subLevels;

    if (rawSector is String) {
      sectorStr = rawSector;
    } else if (rawSector is Map) {
      secLevels = IndicatorLevelIds.fromJson(rawSector);
    }
    if (rawSubSector is String) {
      subStr = rawSubSector;
    } else if (rawSubSector is Map) {
      subLevels = IndicatorLevelIds.fromJson(rawSubSector);
    }

    return Indicator(
      id: parsedId,
      name: json['name']?.toString(),
      type: json['type']?.toString(),
      unit: json['unit']?.toString(),
      fdrsKpiCode: json['fdrs_kpi_code']?.toString(),
      sector: sectorStr,
      subSector: subStr,
      sectorLevels: secLevels,
      subSectorLevels: subLevels,
      nameTranslations: _stringMap(json['name_translations']),
      definitionTranslations: _stringMap(json['definition_translations']),
      translatableLanguages: _stringList(json['translatable_languages']),
      comments: json['comments']?.toString(),
      relatedPrograms: _relatedProgramsText(json['related_programs']),
      isEmergency: (json['is_emergency'] as bool?) ??
          (json['emergency'] as bool?) ??
          false,
      isArchived:
          (json['is_archived'] as bool?) ?? (json['archived'] as bool?) ?? false,
      canArchive: json['can_archive'] as bool? ?? true,
      description: json['description']?.toString() ?? json['definition']?.toString(),
    );
  }

  /// Detail payload sends a list; older rows and the edit form use a string.
  static String? _relatedProgramsText(dynamic raw) {
    if (raw == null) return null;
    if (raw is String) return raw;
    if (raw is List) {
      final parts = raw
          .map((item) => item?.toString().trim() ?? '')
          .where((item) => item.isNotEmpty)
          .toList();
      return parts.isEmpty ? null : parts.join(', ');
    }
    final text = raw.toString().trim();
    return text.isEmpty ? null : text;
  }
}
