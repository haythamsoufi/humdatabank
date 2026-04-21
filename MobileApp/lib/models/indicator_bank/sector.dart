class Sector {
  final int id;
  final String name;
  final String? localizedName;
  final String? description;
  final String? localizedDescription;
  final String? logoUrl;
  final int displayOrder;
  final List<SubSector> subsectors;

  Sector({
    required this.id,
    required this.name,
    this.localizedName,
    this.description,
    this.localizedDescription,
    this.logoUrl,
    this.displayOrder = 0,
    this.subsectors = const [],
  });

  factory Sector.fromJson(Map<String, dynamic> json) {
    return Sector(
      id: json['id'] as int,
      name: json['name'] as String,
      localizedName: json['localized_name'] as String?,
      description: json['description'] as String?,
      localizedDescription: json['localized_description'] as String?,
      logoUrl: json['logo_url'] as String?,
      displayOrder: json['display_order'] as int? ?? 0,
      subsectors: (json['subsectors'] as List<dynamic>?)
              ?.map((s) => SubSector.fromJson(s))
              .toList() ??
          [],
    );
  }

  String get displayName => localizedName ?? name;
  String get displayDescription => localizedDescription ?? description ?? '';
}

class SubSector {
  final int id;
  final String name;
  final String? localizedName;
  final String? description;
  final String? localizedDescription;
  final String? logoUrl;
  final int displayOrder;
  final int? sectorId;

  SubSector({
    required this.id,
    required this.name,
    this.localizedName,
    this.description,
    this.localizedDescription,
    this.logoUrl,
    this.displayOrder = 0,
    this.sectorId,
  });

  factory SubSector.fromJson(Map<String, dynamic> json) {
    return SubSector(
      id: json['id'] as int,
      name: json['name'] as String,
      localizedName: json['localized_name'] as String?,
      description: json['description'] as String?,
      localizedDescription: json['localized_description'] as String?,
      logoUrl: json['logo_url'] as String?,
      displayOrder: json['display_order'] as int? ?? 0,
      sectorId: json['sector_id'] as int?,
    );
  }

  String get displayName => localizedName ?? name;
  String get displayDescription => localizedDescription ?? description ?? '';
}
