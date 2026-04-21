import 'storage_service.dart';
import '../utils/debug_logger.dart';

/// Manages secure storage of JWT access and refresh tokens.
///
/// Kept separate from [SessionService] intentionally: session cookies are still
/// needed for WebView-based flows (Azure SSO, in-app HTML views), while JWT
/// tokens are used for all REST API calls.
class JwtTokenService {
  static final JwtTokenService _instance = JwtTokenService._internal();
  factory JwtTokenService() => _instance;
  JwtTokenService._internal();

  final StorageService _storage = StorageService();

  static const String _accessTokenKey = 'jwt_access_token_v1';
  static const String _refreshTokenKey = 'jwt_refresh_token_v1';
  // Stores milliseconds-since-epoch of access token expiry.
  static const String _accessExpiresAtKey = 'jwt_access_expires_at_v1';

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
    final expiresAt = DateTime.now().millisecondsSinceEpoch + (expiresIn * 1000);
    await _storage.setSecure(_accessTokenKey, accessToken);
    await _storage.setSecure(_refreshTokenKey, refreshToken);
    await _storage.setInt(_accessExpiresAtKey, expiresAt);
    DebugLogger.logAuth('JWT tokens saved (access expires in ${expiresIn}s)');
  }

  /// Update only the access token (e.g. after a silent refresh that also
  /// returns a new refresh token — save both via [saveTokens] instead).
  Future<void> saveAccessToken({
    required String accessToken,
    required int expiresIn,
  }) async {
    final expiresAt = DateTime.now().millisecondsSinceEpoch + (expiresIn * 1000);
    await _storage.setSecure(_accessTokenKey, accessToken);
    await _storage.setInt(_accessExpiresAtKey, expiresAt);
    DebugLogger.logAuth('JWT access token updated (expires in ${expiresIn}s)');
  }

  Future<String?> getAccessToken() async {
    return await _storage.getSecure(_accessTokenKey);
  }

  Future<String?> getRefreshToken() async {
    return await _storage.getSecure(_refreshTokenKey);
  }

  /// Returns true if the stored access token is absent or within
  /// [_expiryBufferMs] of expiry.
  Future<bool> isAccessTokenExpired() async {
    final expiresAt = await _storage.getInt(_accessExpiresAtKey);
    if (expiresAt == null) return true;
    return DateTime.now().millisecondsSinceEpoch >= (expiresAt - _expiryBufferMs);
  }

  /// Returns true if at least an access token is stored (regardless of expiry).
  Future<bool> hasTokens() async {
    final token = await _storage.getSecure(_accessTokenKey);
    return token != null && token.isNotEmpty;
  }

  /// Returns true if a refresh token is stored.
  Future<bool> hasRefreshToken() async {
    final token = await _storage.getSecure(_refreshTokenKey);
    return token != null && token.isNotEmpty;
  }

  /// Delete all JWT tokens from secure storage.
  Future<void> clearTokens() async {
    await _storage.deleteSecure(_accessTokenKey);
    await _storage.deleteSecure(_refreshTokenKey);
    await _storage.remove(_accessExpiresAtKey);
    DebugLogger.logAuth('JWT tokens cleared');
  }
}
