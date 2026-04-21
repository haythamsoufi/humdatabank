class AdminUserCountryRef {
  final int id;
  final String? name;
  final String? code;

  AdminUserCountryRef({required this.id, this.name, this.code});

  factory AdminUserCountryRef.fromJson(Map<String, dynamic> json) {
    return AdminUserCountryRef(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}') ?? 0,
      name: json['name']?.toString(),
      code: json['code']?.toString(),
    );
  }
}

class AdminUserListItem {
  final int id;
  final String email;
  final String? name;
  final String? title;
  final bool active;
  final List<AdminUserRbacRole> rbacRoles;
  final String computedRoleType;
  final bool chatbotEnabled;
  final String? profileColor;
  final List<AdminUserCountryRef> countries;
  final Map<String, int> entityCounts;

  AdminUserListItem({
    required this.id,
    required this.email,
    this.name,
    this.title,
    required this.active,
    required this.rbacRoles,
    this.computedRoleType = 'admin',
    this.chatbotEnabled = true,
    this.profileColor,
    this.countries = const [],
    this.entityCounts = const {},
  });

  factory AdminUserListItem.fromJson(Map<String, dynamic> json) {
    final rolesRaw = json['rbac_roles'];
    final roles = <AdminUserRbacRole>[];
    if (rolesRaw is List) {
      for (final e in rolesRaw) {
        if (e is Map<String, dynamic>) {
          roles.add(AdminUserRbacRole.fromJson(e));
        }
      }
    }
    final countriesRaw = json['countries'];
    final countries = <AdminUserCountryRef>[];
    if (countriesRaw is List) {
      for (final e in countriesRaw) {
        if (e is Map<String, dynamic>) {
          countries.add(AdminUserCountryRef.fromJson(e));
        }
      }
    }
    final ecRaw = json['entity_counts'];
    final entityCounts = <String, int>{};
    if (ecRaw is Map) {
      ecRaw.forEach((k, v) {
        final key = k?.toString();
        if (key == null || key.isEmpty) return;
        if (v is int) {
          entityCounts[key] = v;
        } else {
          final n = int.tryParse('$v');
          if (n != null) entityCounts[key] = n;
        }
      });
    }
    return AdminUserListItem(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}') ?? 0,
      email: json['email']?.toString() ?? '',
      name: json['name']?.toString(),
      title: json['title']?.toString(),
      active: json['active'] == true,
      rbacRoles: roles,
      computedRoleType: json['computed_role_type']?.toString() ?? 'admin',
      chatbotEnabled: json['chatbot_enabled'] != false,
      profileColor: json['profile_color']?.toString(),
      countries: countries,
      entityCounts: entityCounts,
    );
  }

  String get displayName {
    final n = name?.trim();
    if (n != null && n.isNotEmpty) return n;
    return email;
  }

  bool get isSystemManager => rbacRoles.any((r) => r.code == 'system_manager');

  /// Mirrors backoffice `user_form.html` grouping (assignment / admin presets / other).
  List<AdminUserRbacRole> get assignmentRoles =>
      rbacRoles.where((r) => r.code.startsWith('assignment_')).toList();

  List<AdminUserRbacRole> get adminAndSystemRoles => rbacRoles
      .where((r) => r.code == 'system_manager' || r.code.startsWith('admin_'))
      .toList();

  List<AdminUserRbacRole> get otherRoles => rbacRoles
      .where(
        (r) =>
            r.code != 'system_manager' &&
            !r.code.startsWith('admin_') &&
            !r.code.startsWith('assignment_'),
      )
      .toList();

  String get rolesLabel {
    if (rbacRoles.isEmpty) return '—';
    return rbacRoles.map((r) => r.name ?? r.code).where((s) => s.isNotEmpty).join(', ');
  }
}

class AdminUserRbacRole {
  final int? id;
  final String code;
  final String? name;

  AdminUserRbacRole({this.id, required this.code, this.name});

  factory AdminUserRbacRole.fromJson(Map<String, dynamic> json) {
    return AdminUserRbacRole(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}'),
      code: json['code']?.toString() ?? '',
      name: json['name']?.toString(),
    );
  }
}
