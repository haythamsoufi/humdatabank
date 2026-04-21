class Indicator {
  final int id;
  final String? name;
  final String? type;
  final String? unit;
  final String? sector;
  final String? subSector;
  final bool isEmergency;
  final bool isArchived;
  final String? description;

  Indicator({
    required this.id,
    this.name,
    this.type,
    this.unit,
    this.sector,
    this.subSector,
    this.isEmergency = false,
    this.isArchived = false,
    this.description,
  });

  factory Indicator.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final parsedId = rawId is int ? rawId : int.tryParse('$rawId') ?? 0;

    final rawSector = json['sector'];
    final rawSubSector = json['sub_sector'];

    return Indicator(
      id: parsedId,
      name: json['name'] as String?,
      type: json['type'] as String?,
      unit: json['unit'] as String?,
      sector: rawSector is String ? rawSector : null,
      subSector: rawSubSector is String ? rawSubSector : null,
      isEmergency: (json['is_emergency'] as bool?) ??
          (json['emergency'] as bool?) ??
          false,
      isArchived:
          (json['is_archived'] as bool?) ?? (json['archived'] as bool?) ?? false,
      description: (json['description'] as String?) ?? (json['definition'] as String?),
    );
  }
}
