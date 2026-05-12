class Template {
  final int id;
  final String name;
  final String? localizedName;
  final bool addToSelfReport;
  final int? ownedByUserId;
  final String? ownedByUserName;
  final DateTime createdAt;
  final int? dataCount;

  Template({
    required this.id,
    required this.name,
    this.localizedName,
    required this.addToSelfReport,
    this.ownedByUserId,
    this.ownedByUserName,
    required this.createdAt,
    this.dataCount,
  });

  factory Template.fromJson(Map<String, dynamic> json) {
    return Template(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      localizedName: json['localized_name'],
      addToSelfReport: json['add_to_self_report'] ?? false,
      ownedByUserId: json['owned_by_user_id'],
      ownedByUserName: json['owned_by_user_name'],
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'])
          : DateTime.now(),
      dataCount: json['data_count'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'localized_name': localizedName,
      'add_to_self_report': addToSelfReport,
      'owned_by_user_id': ownedByUserId,
      'owned_by_user_name': ownedByUserName,
      'created_at': createdAt.toIso8601String(),
      'data_count': dataCount,
    };
  }

  String get displayName => localizedName ?? name;
}
