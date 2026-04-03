import 'dart:convert';
import '../config/app_config.dart';
import '../models/shared/user.dart';
import 'api_service.dart';
import '../utils/debug_logger.dart';

/// Service for fetching user profile data.
///
/// This service fetches user profile from the JSON API endpoint `/api/v1/user/profile`.
/// The backend API endpoint must be available for this service to work.
class UserProfileService {
  static final UserProfileService _instance = UserProfileService._internal();
  factory UserProfileService() => _instance;
  UserProfileService._internal();

  final ApiService _api = ApiService();

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
        AppConfig.userProfileApiEndpoint,
        timeout: const Duration(seconds: 5),
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;

          // Validate required fields
          if (!jsonData.containsKey('email') || !jsonData.containsKey('role')) {
            DebugLogger.logAuth('API response missing required fields');
            return null;
          }

          // Map API response to User model
          // Handle different possible field names from backend
          final user = User(
            id: jsonData['id'] as int? ?? 0,
            email: jsonData['email'] as String,
            name: jsonData['name'] as String?,
            title: jsonData['title'] as String?,
            role: _normalizeRole(jsonData['role'] as String? ?? 'focal_point'),
            chatbotEnabled: jsonData['chatbot_enabled'] as bool? ?? false,
            profileColor: jsonData['profile_color'] as String?,
            countryIds: _extractCountryIds(jsonData),
            aiBetaTester: jsonData['ai_beta_tester'] == true,
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
            'API endpoint ${AppConfig.userProfileApiEndpoint} not found (404)');
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
        AppConfig.userProfileUpdateApiEndpoint,
        body: requestBody,
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;

          // Validate required fields
          if (!jsonData.containsKey('email') || !jsonData.containsKey('role')) {
            DebugLogger.logAuth('API response missing required fields');
            return null;
          }

          // Map API response to User model
          final user = User(
            id: jsonData['id'] as int? ?? 0,
            email: jsonData['email'] as String,
            name: jsonData['name'] as String?,
            title: jsonData['title'] as String?,
            role: _normalizeRole(jsonData['role'] as String? ?? 'focal_point'),
            chatbotEnabled: jsonData['chatbot_enabled'] as bool? ?? false,
            profileColor: jsonData['profile_color'] as String?,
            countryIds: _extractCountryIds(jsonData),
            aiBetaTester: jsonData['ai_beta_tester'] == true,
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
