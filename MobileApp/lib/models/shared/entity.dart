class Entity {
  final String entityType;
  final int entityId;
  final String name;
  final String? displayName;
  final int? countryId;
  final String? countryName;

  Entity({
    required this.entityType,
    required this.entityId,
    required this.name,
    this.displayName,
    this.countryId,
    this.countryName,
  });

  factory Entity.fromJson(Map<String, dynamic> json) {
    return Entity(
      entityType: json['entity_type'] ?? 'country',
      entityId: json['entity_id'] ?? 0,
      name: json['name'] ?? '',
      displayName: json['display_name'],
      countryId: json['country_id'],
      countryName: json['country_name'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'entity_type': entityType,
      'entity_id': entityId,
      'name': name,
      'display_name': displayName,
      'country_id': countryId,
      'country_name': countryName,
    };
  }

  String get displayLabel => displayName ?? name;

  String get selectionKey => '$entityType:$entityId';

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Entity &&
        other.entityType == entityType &&
        other.entityId == entityId;
  }

  @override
  int get hashCode => Object.hash(entityType, entityId);
}
