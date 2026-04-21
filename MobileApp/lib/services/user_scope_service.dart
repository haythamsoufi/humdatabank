import 'dart:convert';

import '../config/app_config.dart';
import 'storage_service.dart';

/// Provides a consistent scope identifier for user-specific persistence layers
/// such as offline caches and queued requests.
class UserScopeService {
  static final UserScopeService _instance = UserScopeService._internal();
  factory UserScopeService() => _instance;
  UserScopeService._internal();

  final StorageService _storage = StorageService();

  /// Returns a stable scope string to isolate cached content per user/session.
  Future<String> getScope({required bool includeAuth}) async {
    if (!includeAuth) {
      return 'public';
    }

    // Prefer explicit user id from cached profile.
    final cachedUserJson =
        await _storage.getString(AppConfig.cachedUserProfileKey);
    if (cachedUserJson != null) {
      try {
        final decoded = jsonDecode(cachedUserJson) as Map<String, dynamic>;
        final userId = decoded['id'];
        if (userId != null) {
          return 'user_$userId';
        }
        final email = decoded['email'];
        if (email is String && email.isNotEmpty) {
          return 'user_${email.toLowerCase()}';
        }
      } catch (_) {
        // Ignore malformed cache entries and fall back to session hash.
      }
    }

    final sessionCookie =
        await _storage.getSecure(AppConfig.sessionCookieKey) ?? '';
    if (sessionCookie.isNotEmpty) {
      return 'session_${_simpleHash(sessionCookie)}';
    }

    return 'anonymous';
  }

  String _simpleHash(String value) {
    var hash = 17;
    for (final codeUnit in value.codeUnits) {
      hash = 37 * hash + codeUnit;
    }
    return hash.abs().toRadixString(16);
  }
}
