class Indicator {
  final int id;
  final String? name;
  final String? type;
  final String? sector;
  final String? subSector;
  final bool isEmergency;
  final bool isArchived;
  final String? description;

  Indicator({
    required this.id,
    this.name,
    this.type,
    this.sector,
    this.subSector,
    this.isEmergency = false,
    this.isArchived = false,
    this.description,
  });

  factory Indicator.fromJson(Map<String, dynamic> json) {
    return Indicator(
      id: json['id'] as int,
      name: json['name'] as String?,
      type: json['type'] as String?,
      sector: json['sector'] as String?,
      subSector: json['sub_sector'] as String?,
      isEmergency: json['is_emergency'] as bool? ?? false,
      isArchived: json['is_archived'] as bool? ?? false,
      description: json['description'] as String?,
    );
  }
}
