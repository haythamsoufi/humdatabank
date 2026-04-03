class Indicator {
  final int id;
  final String name;
  final String? localizedName;
  final String? definition;
  final String? localizedDefinition;
  final String? type;
  final String? localizedType;
  final String? unit;
  final String? localizedUnit;
  final dynamic sector; // Can be String or Map
  final dynamic subSector; // Can be String or Map
  final bool? emergency;
  final List<String>? relatedPrograms;
  final bool archived;

  Indicator({
    required this.id,
    required this.name,
    this.localizedName,
    this.definition,
    this.localizedDefinition,
    this.type,
    this.localizedType,
    this.unit,
    this.localizedUnit,
    this.sector,
    this.subSector,
    this.emergency,
    this.relatedPrograms,
    this.archived = false,
  });

  factory Indicator.fromJson(Map<String, dynamic> json) {
    return Indicator(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      localizedName: json['localized_name'] as String?,
      definition: json['definition'] as String?,
      localizedDefinition: json['localized_definition'] as String?,
      type: json['type'] as String?,
      localizedType: json['localized_type'] as String?,
      unit: json['unit'] as String?,
      localizedUnit: json['localized_unit'] as String?,
      sector: json['sector'],
      subSector: json['sub_sector'],
      emergency: json['emergency'] as bool?,
      relatedPrograms: json['related_programs'] != null
          ? List<String>.from(json['related_programs'] as List)
          : null,
      archived: json['archived'] as bool? ?? false,
    );
  }

  String get displayName => localizedName ?? name;
  String get displayType => localizedType ?? type ?? '';
  String get displayUnit => localizedUnit ?? unit ?? '';
  String get displayDefinition => localizedDefinition ?? definition ?? '';

  String get displaySector {
    if (sector == null) return '';
    if (sector is String) return sector as String;
    if (sector is Map) {
      final sectorMap = sector as Map<String, dynamic>;
      return sectorMap['localized_name'] as String? ??
          sectorMap['primary'] as String? ??
          sectorMap['name'] as String? ??
          sector.toString();
    }
    return sector.toString();
  }

  String get displaySubSector {
    if (subSector == null) return '';
    if (subSector is String) return subSector as String;
    if (subSector is Map) {
      final subSectorMap = subSector as Map<String, dynamic>;
      return subSectorMap['localized_name'] as String? ??
          subSectorMap['primary'] as String? ??
          subSectorMap['name'] as String? ??
          subSector.toString();
    }
    return subSector.toString();
  }
}
