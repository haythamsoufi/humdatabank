import 'dart:convert';

import 'storage_service.dart';
import '../utils/debug_logger.dart';

/// Manages secure storage of JWT access and refresh tokens.
///
/// Kept separate from [SessionService] intentionally: session cookies are still
/// needed for WebView-based flows (Azure SSO, in-app HTML views), while JWT
/// tokens are used for all REST API calls.
///
/// Tokens are persisted as a single JSON blob in secure storage so access,
/// refresh, and expiry can never drift apart after a partial write.
class JwtTokenService {
  static final JwtTokenService _instance = JwtTokenService._internal();
  factory JwtTokenService() => _instance;
  JwtTokenService._internal();

  final StorageService _storage = StorageService();

  static const String _accessTokenKey = 'jwt_access_token_v1';
  static const String _refreshTokenKey = 'jwt_refresh_token_v1';
  static const String _accessExpiresAtKey = 'jwt_access_expires_at_v2';
  static const String _tokenBundleKey = 'jwt_token_bundle_v1';

  // Legacy SharedPreferences key used before the move into secure storage.
  // Read once on startup and migrated forward; never written again.
  static const String _legacyAccessExpiresAtKey = 'jwt_access_expires_at_v1';

  // Expire the access token 60 s early to avoid races where the token expires
  // in-flight between header construction and server validation.
  static const int _expiryBufferMs = 60000;

  /// Save a full token pair received from the server.
  ///
  /// [expiresIn] is the access token lifetime in **seconds** as returned by
  /// the `expires_in` field of the token endpoint.
  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
    required int expiresIn,
  }) async {
    final expiresAt =
        DateTime.now().millisecondsSinceEpoch + (expiresIn * 1000);
    await _writeTokenState(
      accessToken: accessToken,
      refreshToken: refreshToken,
      expiresAtMs: expiresAt,
    );
    await _storage.remove(_legacyAccessExpiresAtKey);
    DebugLogger.logAuth('JWT tokens saved (access expires in ${expiresIn}s)');
  }

  /// Update only the access token (e.g. after a silent refresh that also
  /// returns a new refresh token — save both via [saveTokens] instead).
  Future<void> saveAccessToken({
    required String accessToken,
    required int expiresIn,
  }) async {
    final expiresAt =
        DateTime.now().millisecondsSinceEpoch + (expiresIn * 1000);
    final refresh = await getRefreshToken();
    if (refresh == null || refresh.isEmpty) {
      DebugLogger.logWarn(
          'AUTH', 'saveAccessToken called without a stored refresh token');
      await _storage.setSecure(_accessTokenKey, accessToken);
      await _storage.setSecure(_accessExpiresAtKey, expiresAt.toString());
      await _storage.remove(_legacyAccessExpiresAtKey);
      return;
    }
    await _writeTokenState(
      accessToken: accessToken,
      refreshToken: refresh,
      expiresAtMs: expiresAt,
    );
    await _storage.remove(_legacyAccessExpiresAtKey);
    DebugLogger.logAuth('JWT access token updated (expires in ${expiresIn}s)');
  }

  Future<String?> getAccessToken() async {
    final state = await _loadTokenState();
    return state?.accessToken;
  }

  Future<String?> getRefreshToken() async {
    final state = await _loadTokenState();
    return state?.refreshToken;
  }

  Future<int?> _readAccessExpiresAt() async {
    final state = await _loadTokenState();
    if (state != null) return state.expiresAtMs;

    final secure = await _storage.getSecure(_accessExpiresAtKey);
    final parsed = secure == null ? null : int.tryParse(secure);
    if (parsed != null) return parsed;

    // One-shot migration from the old SharedPreferences key.
    final legacy = await _storage.getInt(_legacyAccessExpiresAtKey);
    if (legacy != null) {
      try {
        await _storage.setSecure(_accessExpiresAtKey, legacy.toString());
        await _storage.remove(_legacyAccessExpiresAtKey);
      } catch (_) {
        // Even if migration write fails, we can still return the legacy value.
      }
      return legacy;
    }
    return null;
  }

  /// Milliseconds remaining until the access token is treated as expired
  /// (includes the [_expiryBufferMs] safety margin). Returns [Duration.zero]
  /// when expired/absent, or `null` when no expiry timestamp is stored.
  Future<Duration?> timeUntilAccessExpiry() async {
    final expiresAt = await _readAccessExpiresAt();
    if (expiresAt == null) return null;
    final remainingMs = expiresAt -
        _expiryBufferMs -
        DateTime.now().millisecondsSinceEpoch;
    if (remainingMs <= 0) return Duration.zero;
    return Duration(milliseconds: remainingMs);
  }

  /// Returns true if the stored access token is absent or within
  /// [_expiryBufferMs] of expiry.
  Future<bool> isAccessTokenExpired() async {
    final expiresAt = await _readAccessExpiresAt();
    if (expiresAt == null) return true;
    return DateTime.now().millisecondsSinceEpoch >=
        (expiresAt - _expiryBufferMs);
  }

  /// Returns true if at least an access **or** refresh token is stored.
  Future<bool> hasTokens() async {
    final state = await _loadTokenState();
    if (state == null) return false;
    return state.hasAnyToken;
  }

  /// Returns true if a refresh token is stored.
  Future<bool> hasRefreshToken() async {
    final token = await getRefreshToken();
    return token != null && token.isNotEmpty;
  }

  /// Delete all JWT tokens from secure storage.
  Future<void> clearTokens() async {
    await _storage.deleteSecure(_tokenBundleKey);
    await _storage.deleteSecure(_accessTokenKey);
    await _storage.deleteSecure(_refreshTokenKey);
    await _storage.deleteSecure(_accessExpiresAtKey);
    await _storage.remove(_legacyAccessExpiresAtKey);
    DebugLogger.logAuth('JWT tokens cleared');
  }

  Future<void> _writeTokenState({
    required String accessToken,
    required String refreshToken,
    required int expiresAtMs,
  }) async {
    final bundle = jsonEncode(<String, dynamic>{
      'access_token': accessToken,
      'refresh_token': refreshToken,
      'expires_at_ms': expiresAtMs,
    });
    // Single atomic write — the bundle is the source of truth.
    await _storage.setSecure(_tokenBundleKey, bundle);
    // Legacy individual keys kept in sync for in-flight upgrades; cleared on
    // [clearTokens] and never read when the bundle is present.
    await _storage.setSecure(_accessTokenKey, accessToken);
    await _storage.setSecure(_refreshTokenKey, refreshToken);
    await _storage.setSecure(_accessExpiresAtKey, expiresAtMs.toString());
  }

  Future<_TokenState?> _loadTokenState() async {
    final bundleRaw = await _storage.getSecure(_tokenBundleKey);
    if (bundleRaw != null && bundleRaw.isNotEmpty) {
      try {
        final map = jsonDecode(bundleRaw) as Map<String, dynamic>;
        return _TokenState.fromJson(map);
      } catch (e) {
        DebugLogger.logWarn('AUTH', 'Corrupt JWT bundle — clearing tokens: $e');
        await clearTokens();
        return null;
      }
    }

    // Migrate from legacy per-key storage into the bundle.
    final access = await _storage.getSecure(_accessTokenKey);
    final refresh = await _storage.getSecure(_refreshTokenKey);
    if ((access == null || access.isEmpty) &&
        (refresh == null || refresh.isEmpty)) {
      return null;
    }

    int? expiresAtMs;
    final secureExpiry = await _storage.getSecure(_accessExpiresAtKey);
    expiresAtMs = secureExpiry == null ? null : int.tryParse(secureExpiry);
    expiresAtMs ??= await _storage.getInt(_legacyAccessExpiresAtKey);

    if (access != null &&
        access.isNotEmpty &&
        refresh != null &&
        refresh.isNotEmpty &&
        expiresAtMs != null) {
      await _writeTokenState(
        accessToken: access,
        refreshToken: refresh,
        expiresAtMs: expiresAtMs,
      );
      await _storage.remove(_legacyAccessExpiresAtKey);
      return _TokenState(
        accessToken: access,
        refreshToken: refresh,
        expiresAtMs: expiresAtMs,
      );
    }

    return _TokenState(
      accessToken: access,
      refreshToken: refresh,
      expiresAtMs: expiresAtMs,
    );
  }
}

class _TokenState {
  final String? accessToken;
  final String? refreshToken;
  final int? expiresAtMs;

  const _TokenState({
    required this.accessToken,
    required this.refreshToken,
    this.expiresAtMs,
  });

  bool get hasAnyToken =>
      (accessToken != null && accessToken!.isNotEmpty) ||
      (refreshToken != null && refreshToken!.isNotEmpty);

  factory _TokenState.fromJson(Map<String, dynamic> json) {
    return _TokenState(
      accessToken: json['access_token']?.toString(),
      refreshToken: json['refresh_token']?.toString(),
      expiresAtMs: json['expires_at_ms'] is int
          ? json['expires_at_ms'] as int
          : int.tryParse(json['expires_at_ms']?.toString() ?? ''),
    );
  }
}
