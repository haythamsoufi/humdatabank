import 'dart:convert';
import '../config/app_config.dart';
import '../models/shared/user.dart';
import 'api_service.dart';
import '../utils/debug_logger.dart';
import '../di/service_locator.dart';

/// Service for fetching and updating the authenticated user's profile.
///
/// Uses the mobile API endpoint (`/api/mobile/v1/auth/profile`) with JWT Bearer auth.
class UserProfileService {
  static final UserProfileService _instance = UserProfileService._internal();
  factory UserProfileService() => _instance;
  UserProfileService._internal();

  final ApiService _api = sl<ApiService>();

  /// Mobile routes wrap payloads in `{ "success": true, "data": { ... } }`.
  Map<String, dynamic> _unwrapMobileEnvelope(Map<String, dynamic> body) {
    final data = body['data'];
    if (data is Map<String, dynamic>) {
      return data;
    }
    return body;
  }

  /// Fetch user profile from the JSON API endpoint.
  ///
  /// Returns a User object if successful, null if the API returns invalid data.
  /// Throws exceptions for network errors (caller should handle).
  Future<User?> fetchUserProfile() async {
    try {
      final user = await _fetchFromApi();
      if (user != null) {
        DebugLogger.logAuth('User profile loaded from API');
        return user;
      }
      DebugLogger.logAuth('API returned null user');
      return null;
    } catch (e) {
      DebugLogger.logAuth('API fetch failed: $e');
      rethrow;
    }
  }

  /// Fetch user profile from JSON API endpoint.
  ///
  /// Returns null if endpoint doesn't exist (404) or returns invalid data.
  Future<User?> _fetchFromApi() async {
    try {
      DebugLogger.logAuth('Attempting to fetch user profile from API...');

      // Try the new API endpoint first
      final response = await _api.get(
        AppConfig.profileEndpoint,
        timeout: const Duration(seconds: 5),
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;

          // Mobile: { "success": true, "data": { "user": { "email": "...", ... } } }
          // Legacy / flat: { "user": { ... } } or user fields at top level.
          final payload = _unwrapMobileEnvelope(jsonData);
          final userData = (payload['user'] is Map<String, dynamic>
                  ? payload['user']
                  : payload)
              as Map<String, dynamic>;

          final email = userData['email'];
          if (email is! String || email.isEmpty) {
            DebugLogger.logAuth('API response missing email');
            return null;
          }

          // Backoffice returns rbac_roles, not always a top-level role string — derive coarse role.
          final derivedRole = _deriveRoleFromJson(userData);

          // Map API response to User model
          // Handle different possible field names from backend
          final user = User(
            id: _parseUserId(userData['id']),
            email: email,
            name: userData['name'] as String?,
            title: userData['title'] as String?,
            role: derivedRole,
            chatbotEnabled: userData['chatbot_enabled'] as bool? ?? false,
            profileColor: userData['profile_color'] as String?,
            countryIds: _extractCountryIds(userData),
            aiBetaTester: userData['ai_beta_tester'] == true,
          );

          DebugLogger.logAuth(
              'Successfully parsed user from API: ${user.email}, role: ${user.role}');
          return user;
        } catch (e) {
          DebugLogger.logAuth('Failed to parse API response: $e');
          return null;
        }
      } else if (response.statusCode == 404) {
        // Endpoint doesn't exist - this should not happen if backend is properly deployed
        DebugLogger.logAuth(
            'API endpoint ${AppConfig.profileEndpoint} not found (404)');
        return null;
      } else {
        DebugLogger.logAuth('API returned status ${response.statusCode}');
        return null;
      }
    } on AuthenticationException {
      // Re-throw auth errors - they should be handled by caller
      rethrow;
    } catch (e) {
      // For other errors, return null to allow fallback
      DebugLogger.logAuth('API fetch error (non-auth): $e');
      return null;
    }
  }

  int _parseUserId(dynamic raw) {
    if (raw is int) return raw;
    if (raw is num) return raw.toInt();
    return int.tryParse('$raw') ?? 0;
  }

  /// Coarse role for navigation: [system_manager|admin|focal_point].
  /// Prefer legacy `role` when present; else map from Backoffice `rbac_roles`.
  String _deriveRoleFromJson(Map<String, dynamic> json) {
    final direct = json['role'];
    if (direct is String && direct.trim().isNotEmpty) {
      return _normalizeRole(direct);
    }
    final rbac = json['rbac_roles'];
    if (rbac is List) {
      final codes = <String>[];
      for (final item in rbac) {
        if (item is Map<String, dynamic>) {
          final c = item['code'];
          if (c is String && c.isNotEmpty) {
            codes.add(c.toLowerCase().trim());
          }
        } else if (item is Map) {
          final c = item['code'];
          if (c != null && '$c'.isNotEmpty) {
            codes.add('$c'.toLowerCase().trim());
          }
        }
      }
      if (codes.any((c) => c == 'system_manager')) {
        return 'system_manager';
      }
      if (codes.any((c) =>
          c == 'admin_core' ||
          c == 'admin_full' ||
          c.startsWith('admin_'))) {
        return 'admin';
      }
    }
    return 'focal_point';
  }

  /// Normalize role string to standard format.
  String _normalizeRole(String role) {
    final normalized = role.toLowerCase().trim();
    switch (normalized) {
      case 'system_manager':
      case 'system manager':
        return 'system_manager';
      case 'admin':
        return 'admin';
      case 'focal_point':
      case 'focal point':
        return 'focal_point';
      // Backoffice [AuthorizationService.access_level] for authenticated
      // non-admin / non-focal users.
      case 'user':
        return 'user';
      default:
        DebugLogger.logAuth(
            'Unknown role format: "$role", defaulting to focal_point');
        return 'focal_point';
    }
  }

  /// Extract country IDs from API response.
  /// Handles different possible field names: 'country_ids', 'countries', 'assigned_countries'
  List<int>? _extractCountryIds(Map<String, dynamic> json) {
    // Try different possible field names
    if (json.containsKey('country_ids') && json['country_ids'] is List) {
      return (json['country_ids'] as List).map((e) => e as int).toList();
    }

    if (json.containsKey('countries') && json['countries'] is List) {
      return (json['countries'] as List)
          .whereType<Map>()
          .map((c) => c['id'] as int?)
          .whereType<int>()
          .toList();
    }

    if (json.containsKey('assigned_countries') &&
        json['assigned_countries'] is List) {
      return (json['assigned_countries'] as List)
          .whereType<Map>()
          .map((c) => c['id'] as int?)
          .whereType<int>()
          .toList();
    }

    return null;
  }

  /// Update user profile fields.
  ///
  /// Accepts a map with updatable fields:
  /// - name: String? (optional)
  /// - title: String? (optional)
  /// - chatbotEnabled: bool? (optional)
  /// - profileColor: String? (optional)
  ///
  /// Returns updated User object if successful, null if the API returns invalid data.
  /// Throws exceptions for network/authentication errors (caller should handle).
  Future<User?> updateProfile({
    String? name,
    String? title,
    bool? chatbotEnabled,
    String? profileColor,
  }) async {
    try {
      DebugLogger.logAuth('Attempting to update user profile...');

      // Build request body with only provided fields
      final requestBody = <String, dynamic>{};
      if (name != null) requestBody['name'] = name;
      if (title != null) requestBody['title'] = title;
      if (chatbotEnabled != null) {
        requestBody['chatbot_enabled'] = chatbotEnabled;
      }
      if (profileColor != null) requestBody['profile_color'] = profileColor;

      // Check if there's anything to update
      if (requestBody.isEmpty) {
        DebugLogger.logAuth('No fields provided for update');
        return null;
      }

      // Make PUT request to update profile
      final response = await _api.put(
        AppConfig.profileEndpoint,
        body: requestBody,
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          final payload = _unwrapMobileEnvelope(jsonData);

          Map<String, dynamic>? userMap;
          if (payload['user'] is Map<String, dynamic>) {
            userMap = payload['user'] as Map<String, dynamic>;
          } else if (payload.containsKey('email')) {
            userMap = payload;
          }

          if (userMap == null) {
            DebugLogger.logAuth(
              'Profile update returned no user payload — refetching profile',
            );
            return await fetchUserProfile();
          }

          final email = userMap['email'];
          if (email is! String || email.isEmpty) {
            DebugLogger.logAuth('API response missing email');
            return await fetchUserProfile();
          }

          final derivedRole = _deriveRoleFromJson(userMap);

          final user = User(
            id: _parseUserId(userMap['id']),
            email: email,
            name: userMap['name'] as String?,
            title: userMap['title'] as String?,
            role: derivedRole,
            chatbotEnabled: userMap['chatbot_enabled'] as bool? ?? false,
            profileColor: userMap['profile_color'] as String?,
            countryIds: _extractCountryIds(userMap),
            aiBetaTester: userMap['ai_beta_tester'] == true,
          );

          DebugLogger.logAuth(
              'Successfully updated user profile: ${user.email}');
          return user;
        } catch (e) {
          DebugLogger.logAuth('Failed to parse API response: $e');
          return null;
        }
      } else if (response.statusCode == 400) {
        DebugLogger.logAuth('Invalid request (400): ${response.body}');
        return null;
      } else {
        DebugLogger.logAuth('API returned status ${response.statusCode}');
        return null;
      }
    } on AuthenticationException {
      // Re-throw auth errors - they should be handled by caller
      rethrow;
    } catch (e) {
      DebugLogger.logAuth('API update error: $e');
      rethrow;
    }
  }
}
