import '../shared/user.dart';

class AdminUser extends User {
  final bool active;
  final List<CountryEntity>? countries;
  final Map<String, int>? entityCounts; // e.g., {'branches': 2, 'divisions': 1}

  AdminUser({
    required super.id,
    required super.email,
    super.name,
    super.title,
    required super.role,
    super.chatbotEnabled,
    super.profileColor,
    super.countryIds,
    required this.active,
    this.countries,
    this.entityCounts,
  });

  factory AdminUser.fromJson(Map<String, dynamic> json) {
    return AdminUser(
      id: json['id'] ?? 0,
      email: json['email'] ?? '',
      name: json['name'],
      title: json['title'],
      role: json['role'] ?? 'focal_point',
      chatbotEnabled: json['chatbot_enabled'] ?? false,
      profileColor: json['profile_color'],
      countryIds: json['country_ids'] != null
          ? List<int>.from(json['country_ids'])
          : null,
      active: json['active'] ?? true,
      countries: json['countries'] != null
          ? (json['countries'] as List)
              .map((c) => CountryEntity.fromJson(c))
              .toList()
          : null,
      entityCounts: json['entity_counts'] != null
          ? Map<String, int>.from(json['entity_counts'])
          : null,
    );
  }

  @override
  Map<String, dynamic> toJson() {
    final json = super.toJson();
    json['active'] = active;
    if (countries != null) {
      json['countries'] = countries!.map((c) => c.toJson()).toList();
    }
    if (entityCounts != null) {
      json['entity_counts'] = entityCounts;
    }
    return json;
  }

  String get roleDisplayName {
    switch (role) {
      case 'admin':
        return 'Admin';
      case 'focal_point':
        return 'Focal Point';
      case 'system_manager':
        return 'System Manager';
      default:
        return role
            .replaceAll('_', ' ')
            .split(' ')
            .map((w) => w.isEmpty ? '' : w[0].toUpperCase() + w.substring(1))
            .join(' ');
    }
  }

  String get entitiesSummary {
    if (role == 'system_manager') {
      return 'Global';
    }

    if (countries == null || countries!.isEmpty) {
      if (entityCounts == null || entityCounts!.isEmpty) {
        return '-';
      }
    }

    final parts = <String>[];

    if (countries != null && countries!.isNotEmpty) {
      if (countries!.length == 1) {
        parts.add(countries!.first.name);
      } else {
        parts.add('${countries!.length} countries');
      }
    }

    if (entityCounts != null) {
      entityCounts!.forEach((key, value) {
        if (value > 0) {
          parts.add('$value ${key.replaceAll('_', ' ')}');
        }
      });
    }

    return parts.isEmpty ? '-' : parts.join(', ');
  }
}

class CountryEntity {
  final int id;
  final String name;
  final String? code;

  CountryEntity({
    required this.id,
    required this.name,
    this.code,
  });

  factory CountryEntity.fromJson(Map<String, dynamic> json) {
    return CountryEntity(
      id: json['id'] ?? 0,
      name: json['name'] ?? '',
      code: json['code'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'code': code,
    };
  }
}
