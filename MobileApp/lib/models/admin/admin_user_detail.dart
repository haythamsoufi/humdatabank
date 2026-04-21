/// Full user profile from [GET /admin/api/users/:id] (admin.users.view).
class AdminUserPermission {
  final String code;
  final String name;

  const AdminUserPermission({required this.code, required this.name});

  factory AdminUserPermission.fromJson(Map<String, dynamic> json) {
    return AdminUserPermission(
      code: json['code']?.toString() ?? '',
      name: json['name']?.toString() ?? json['code']?.toString() ?? '',
    );
  }
}

class AdminRbacRoleDetail {
  final int id;
  final String code;
  final String name;
  final String? description;
  final List<AdminUserPermission> permissions;

  AdminRbacRoleDetail({
    required this.id,
    required this.code,
    required this.name,
    this.description,
    required this.permissions,
  });

  factory AdminRbacRoleDetail.fromJson(Map<String, dynamic> json) {
    final permsRaw = json['permissions'];
    final perms = <AdminUserPermission>[];
    if (permsRaw is List) {
      for (final e in permsRaw) {
        if (e is Map<String, dynamic>) {
          perms.add(AdminUserPermission.fromJson(e));
        }
      }
    }
    return AdminRbacRoleDetail(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}') ?? 0,
      code: json['code']?.toString() ?? '',
      name: json['name']?.toString() ?? json['code']?.toString() ?? '',
      description: json['description']?.toString(),
      permissions: perms,
    );
  }
}

class AdminEntityPermissionRow {
  final int permissionId;
  final String entityType;
  final int entityId;
  final String? entityName;
  /// IFRC / databank region label for [entityType] == `country` (from API `entity_region`).
  final String? entityRegion;

  AdminEntityPermissionRow({
    required this.permissionId,
    required this.entityType,
    required this.entityId,
    this.entityName,
    this.entityRegion,
  });

  factory AdminEntityPermissionRow.fromJson(Map<String, dynamic> json) {
    return AdminEntityPermissionRow(
      permissionId: json['permission_id'] is int
          ? json['permission_id'] as int
          : int.tryParse('${json['permission_id']}') ?? 0,
      entityType: json['entity_type']?.toString() ?? '',
      entityId:
          json['entity_id'] is int ? json['entity_id'] as int : int.tryParse('${json['entity_id']}') ?? 0,
      entityName: json['entity_name']?.toString(),
      entityRegion: json['entity_region']?.toString() ?? json['entityRegion']?.toString(),
    );
  }
}

class AdminUserDetail {
  final int id;
  final String email;
  final String? name;
  final String? title;
  final bool active;
  final bool chatbotEnabled;
  final String? profileColor;
  final List<AdminRbacRoleDetail> rbacRoles;
  final List<AdminUserPermission> effectivePermissions;
  final List<AdminEntityPermissionRow> entityPermissions;
  final String computedRoleType;
  final bool isSystemManager;

  AdminUserDetail({
    required this.id,
    required this.email,
    this.name,
    this.title,
    required this.active,
    required this.chatbotEnabled,
    this.profileColor,
    required this.rbacRoles,
    required this.effectivePermissions,
    required this.entityPermissions,
    required this.computedRoleType,
    required this.isSystemManager,
  });

  String get displayName {
    final n = name?.trim();
    if (n != null && n.isNotEmpty) return n;
    return email;
  }

  factory AdminUserDetail.fromJson(Map<String, dynamic> json) {
    final rolesRaw = json['rbac_roles'];
    final roles = <AdminRbacRoleDetail>[];
    if (rolesRaw is List) {
      for (final e in rolesRaw) {
        if (e is Map<String, dynamic>) {
          roles.add(AdminRbacRoleDetail.fromJson(e));
        }
      }
    }
    final effRaw = json['effective_permissions'];
    final effective = <AdminUserPermission>[];
    if (effRaw is List) {
      for (final e in effRaw) {
        if (e is Map<String, dynamic>) {
          effective.add(AdminUserPermission.fromJson(e));
        }
      }
    }
    final entRaw = json['entity_permissions'];
    final entities = <AdminEntityPermissionRow>[];
    if (entRaw is List) {
      for (final e in entRaw) {
        if (e is Map) {
          entities.add(AdminEntityPermissionRow.fromJson(Map<String, dynamic>.from(e)));
        }
      }
    }
    return AdminUserDetail(
      id: json['id'] is int ? json['id'] as int : int.tryParse('${json['id']}') ?? 0,
      email: json['email']?.toString() ?? '',
      name: json['name']?.toString(),
      title: json['title']?.toString(),
      active: json['active'] == true,
      chatbotEnabled: json['chatbot_enabled'] != false,
      profileColor: json['profile_color']?.toString(),
      rbacRoles: roles,
      effectivePermissions: effective,
      entityPermissions: entities,
      computedRoleType: json['computed_role_type']?.toString() ?? 'admin',
      isSystemManager: json['is_system_manager'] == true,
    );
  }
}
