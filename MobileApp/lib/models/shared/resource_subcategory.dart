class ResourceSubcategory {
  final int id;
  final String name;
  final int displayOrder;

  const ResourceSubcategory({
    required this.id,
    required this.name,
    this.displayOrder = 0,
  });

  factory ResourceSubcategory.fromJson(Map<String, dynamic> json) {
    return ResourceSubcategory(
      id: json['id'] as int,
      name: json['name'] as String? ?? '',
      displayOrder: json['display_order'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'display_order': displayOrder,
      };
}
