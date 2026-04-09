import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../config/app_config.dart';
import '../../models/admin/admin_user_detail.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';

/// Loads the admin user directory via [GET /api/mobile/v1/admin/users] (JWT auth, `admin.users.view`).
/// Updates: [PUT /api/mobile/v1/admin/users/:id] (`admin.users.edit`; optional RBAC via `admin.users.roles.assign`).
class ManageUsersProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<AdminUserListItem> _users = [];
  bool _isLoading = false;
  String? _error;

  /// From GET /api/mobile/v1/data/countrymap; fills missing `entity_region` on user detail.
  Map<int, String>? _countryIdToRegionCache;
  String? _countryRegionCacheLocale;

  /// Clears cached country id → region map (e.g. after locale change). Optional; cache is per-locale.
  void clearCountryRegionCache() {
    _countryIdToRegionCache = null;
    _countryRegionCacheLocale = null;
  }

  static String _uiLocaleTag() {
    final l = PlatformDispatcher.instance.locale;
    final c = l.languageCode;
    if (c.length == 2) return c;
    return 'en';
  }

  List<AdminUserListItem> get users => List.unmodifiable(_users);
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadUsers() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            AppConfig.mobileAdminUsersEndpoint,
            useCache: false,
          ),
      context: 'Manage Users',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load users. Please try again.';
      _users = [];
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to view users. This requires admin user access on the server.';
      _users = [];
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic> &&
            decoded['success'] == true &&
            decoded['data'] is List) {
          final list = decoded['data'] as List<dynamic>;
          _users = list
              .whereType<Map<String, dynamic>>()
              .map(AdminUserListItem.fromJson)
              .toList();
          _error = null;
        } else {
          _error = 'Unexpected response from server.';
          _users = [];
        }
      } catch (e, stackTrace) {
        final err = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse users list',
        );
        _error = err.getUserMessage();
        _users = [];
      }
    } else {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Manage Users',
      );
      _error = err.getUserMessage();
      _users = [];
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Single-user profile (roles, RBAC permissions, entity grants). Does not mutate the list cache.
  Future<AdminUserDetail?> fetchUserDetail(int userId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            '${AppConfig.mobileAdminUsersEndpoint}/$userId',
            useCache: false,
          ),
      context: 'User detail',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null || response.statusCode != 200) {
      return null;
    }

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) return null;
      final raw = decoded['data'];
      final Map<String, dynamic> userMap;
      if (raw is Map<String, dynamic> && raw.containsKey('user') && raw['user'] is Map<String, dynamic>) {
        userMap = raw['user'] as Map<String, dynamic>;
      } else if (raw is Map<String, dynamic>) {
        userMap = raw;
      } else if (decoded['id'] != null && decoded['email'] != null) {
        userMap = decoded;
      } else {
        return null;
      }
      final success = decoded['success'];
      if (success != null && success != true) return null;

      var detail = AdminUserDetail.fromJson(userMap);
      if (detail.entityPermissions.any(
            (e) =>
                e.entityType.trim().toLowerCase() == 'country' &&
                (e.entityRegion == null || e.entityRegion!.trim().isEmpty),
          )) {
        final lookup = await _loadCountryRegionLookup();
        detail = _mergeCountryRegionsFromLookup(detail, lookup);
      }
      return detail;
    } catch (e, stackTrace) {
      _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Parse user detail',
      );
      return null;
    }
  }

  /// Loads id → region from [GET /api/mobile/v1/data/countrymap]. Cached per UI locale.
  Future<Map<int, String>> _loadCountryRegionLookup() async {
    final localeTag = _uiLocaleTag();
    if (_countryIdToRegionCache != null &&
        _countryRegionCacheLocale == localeTag) {
      return _countryIdToRegionCache!;
    }
    try {
      final resp = await _api.get(
        AppConfig.mobileCountryMapEndpoint,
        useCache: true,
        queryParams: {'locale': localeTag},
      );
      if (resp.statusCode != 200) {
        return {};
      }
      final decoded = jsonDecode(resp.body);
      final List<dynamic> list;
      if (decoded is List) {
        list = decoded;
      } else if (decoded is Map<String, dynamic>) {
        final rawData = decoded['data'];
        if (rawData is Map<String, dynamic> && rawData['countries'] is List) {
          list = rawData['countries'] as List<dynamic>;
        } else if (decoded['countries'] is List) {
          list = decoded['countries'] as List<dynamic>;
        } else {
          return {};
        }
      } else {
        return {};
      }
      final map = <int, String>{};
      for (final e in list) {
        if (e is! Map) continue;
        final m = Map<String, dynamic>.from(e);
        final id = m['id'];
        final cid = id is int ? id : int.tryParse('$id');
        if (cid == null) continue;
        final rawReg = m['region_localized'] ?? m['region'];
        final reg = rawReg?.toString().trim();
        if (reg != null && reg.isNotEmpty) {
          map[cid] = reg;
        }
      }
      _countryIdToRegionCache = map;
      _countryRegionCacheLocale = localeTag;
      return map;
    } catch (_) {
      return {};
    }
  }

  AdminUserDetail _mergeCountryRegionsFromLookup(
    AdminUserDetail detail,
    Map<int, String> idToRegion,
  ) {
    if (idToRegion.isEmpty) return detail;
    var changed = false;
    final enriched = detail.entityPermissions.map((e) {
      if (e.entityType.trim().toLowerCase() != 'country') return e;
      final er = e.entityRegion?.trim();
      if (er != null && er.isNotEmpty) return e;
      final r = idToRegion[e.entityId];
      if (r == null || r.isEmpty) return e;
      changed = true;
      return AdminEntityPermissionRow(
        permissionId: e.permissionId,
        entityType: e.entityType,
        entityId: e.entityId,
        entityName: e.entityName,
        entityRegion: r,
      );
    }).toList();
    if (!changed) return detail;
    return AdminUserDetail(
      id: detail.id,
      email: detail.email,
      name: detail.name,
      title: detail.title,
      active: detail.active,
      chatbotEnabled: detail.chatbotEnabled,
      profileColor: detail.profileColor,
      rbacRoles: detail.rbacRoles,
      effectivePermissions: detail.effectivePermissions,
      entityPermissions: enriched,
      computedRoleType: detail.computedRoleType,
      isSystemManager: detail.isSystemManager,
    );
  }

  /// Code → role id for [GET /admin/api/rbac/roles] (`admin.users.roles.assign`). `null` if forbidden or error.
  Future<Map<String, int>?> fetchRbacRoleCatalog() async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            AppConfig.mobileRbacRolesEndpoint,
            useCache: false,
          ),
      context: 'RBAC roles',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null || response.statusCode != 200) {
      return null;
    }

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) return null;
      final raw = decoded['data'];
      final List<dynamic>? list = raw is List<dynamic>
          ? raw
          : (raw is Map<String, dynamic> && raw['roles'] is List
              ? raw['roles'] as List<dynamic>
              : null);
      if (list == null) return null;
      final map = <String, int>{};
      for (final e in list) {
        if (e is! Map) continue;
        final m = Map<String, dynamic>.from(e);
        final code = m['code']?.toString() ?? '';
        final id = m['id'];
        final rid = id is int ? id : int.tryParse('$id');
        if (code.isEmpty || rid == null) continue;
        map[code] = rid;
      }
      return map;
    } catch (e, stackTrace) {
      _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Parse RBAC catalog',
      );
      return null;
    }
  }

  /// Updates profile and/or RBAC. Pass only fields that should be sent. Returns `null` on success.
  Future<String?> updateUserProfile(
    int userId, {
    String? name,
    String? title,
    bool? active,
    bool? chatbotEnabled,
    String? profileColor,
    List<int>? rbacRoleIds,
  }) async {
    final body = <String, dynamic>{};
    // When updating profile, always send `title` with `name` so clearing the field
    // is persisted as JSON null; title-only patches still send `title` alone.
    if (name != null) {
      body['name'] = name;
      body['title'] = title;
    } else if (title != null) {
      body['title'] = title;
    }
    if (active != null) body['active'] = active;
    if (chatbotEnabled != null) body['chatbot_enabled'] = chatbotEnabled;
    if (profileColor != null) body['profile_color'] = profileColor;
    if (rbacRoleIds != null) body['rbac_role_ids'] = rbacRoleIds;

    if (body.isEmpty) {
      return 'Nothing to save';
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.put(
            '${AppConfig.mobileAdminUsersEndpoint}/$userId',
            body: body,
            queueOnOffline: false,
          ),
      context: 'Update user',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      return 'Unable to save changes. Please try again.';
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return null;
    }

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        final err = decoded['error'];
        if (err is String && err.trim().isNotEmpty) {
          return err.trim();
        }
        final msg = decoded['message'];
        if (msg is String && msg.trim().isNotEmpty) {
          return msg.trim();
        }
      }
    } catch (_) {
      // fall through
    }

    final err = _errorHandler.parseError(
      error: Exception('HTTP ${response.statusCode}'),
      response: response,
      context: 'Update user',
    );
    return err.getUserMessage();
  }
}
