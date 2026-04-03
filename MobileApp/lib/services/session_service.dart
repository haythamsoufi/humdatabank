import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../config/app_config.dart';
import 'storage_service.dart';
import '../utils/debug_logger.dart';

class SessionService {
  static final SessionService _instance = SessionService._internal();
  factory SessionService() => _instance;
  SessionService._internal();

  final StorageService _storage = StorageService();
  final CookieManager _cookieManager = CookieManager.instance();

  // Storage keys for session metadata
  static const String _sessionCreatedAtKey = 'session_created_at';
  static const String _sessionLastValidatedKey = 'session_last_validated';
  static const String _sessionLastValidatedOnlineKey = 'session_last_validated_online';

  // Refresh session if it expires within this duration
  static const Duration _sessionRefreshThreshold = Duration(hours: 1);

  // Offline validity duration - allow operations if offline and session was validated within this time
  static const Duration _offlineValidityDuration = Duration(minutes: 30);

  // Save session cookie after login
  Future<void> saveSessionCookie(String cookie) async {
    await _storage.setSecure(AppConfig.sessionCookieKey, cookie);
    // Track when session was created
    final now = DateTime.now().millisecondsSinceEpoch;
    await _storage.setInt(_sessionCreatedAtKey, now);
    await _storage.setInt(_sessionLastValidatedKey, now);
  }

  // Get session cookie
  Future<String?> getSessionCookie() async {
    return await _storage.getSecure(AppConfig.sessionCookieKey);
  }

  // Get session creation time
  Future<DateTime?> getSessionCreatedAt() async {
    final timestamp = await _storage.getInt(_sessionCreatedAtKey);
    if (timestamp == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(timestamp);
  }

  // Get last validation time
  Future<DateTime?> getSessionLastValidated() async {
    final timestamp = await _storage.getInt(_sessionLastValidatedKey);
    if (timestamp == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(timestamp);
  }

  // Update last validation time
  Future<void> updateLastValidation({bool isOnline = true}) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    await _storage.setInt(_sessionLastValidatedKey, now);
    if (isOnline) {
      // Track when we last validated while online
      await _storage.setInt(_sessionLastValidatedOnlineKey, now);
    }
  }

  // Get last online validation time
  Future<DateTime?> getSessionLastValidatedOnline() async {
    final timestamp = await _storage.getInt(_sessionLastValidatedOnlineKey);
    if (timestamp == null) return null;
    return DateTime.fromMillisecondsSinceEpoch(timestamp);
  }

  // Check if session is valid for offline operations
  Future<bool> isSessionValidForOffline() async {
    final lastValidatedOnline = await getSessionLastValidatedOnline();
    if (lastValidatedOnline == null) return false;

    final now = DateTime.now();
    final timeSinceLastOnlineValidation = now.difference(lastValidatedOnline);

    // Session is valid for offline operations if validated online within last 30 minutes
    return timeSinceLastOnlineValidation < _offlineValidityDuration;
  }

  // Check if session is expired
  // IMPROVED: Uses last activity time instead of creation time
  // This ensures sessions stay alive during active use
  Future<bool> isSessionExpired() async {
    final lastValidated = await getSessionLastValidated();
    if (lastValidated == null) {
      // Fallback to creation time if no validation timestamp exists
      final createdAt = await getSessionCreatedAt();
      if (createdAt == null) return true;
      final now = DateTime.now();
      final age = now.difference(createdAt);
      return age >= AppConfig.sessionTimeout;
    }

    // Check expiration based on last activity (not creation time)
    final now = DateTime.now();
    final timeSinceLastActivity = now.difference(lastValidated);

    // Session expires if no activity for the timeout duration
    // This allows sessions to stay alive during active use
    return timeSinceLastActivity >= AppConfig.sessionTimeout;
  }

  // Check if session needs refresh (within threshold of expiration)
  // IMPROVED: Uses last activity time for more accurate refresh timing
  Future<bool> needsRefresh() async {
    final lastValidated = await getSessionLastValidated();
    if (lastValidated == null) {
      // Fallback to creation time if no validation timestamp exists
      final createdAt = await getSessionCreatedAt();
      if (createdAt == null) return false;
      final now = DateTime.now();
      final age = now.difference(createdAt);
      final timeUntilExpiration = AppConfig.sessionTimeout - age;
      return timeUntilExpiration <= _sessionRefreshThreshold;
    }

    // Check refresh need based on last activity
    final now = DateTime.now();
    final timeSinceLastActivity = now.difference(lastValidated);
    final timeUntilExpiration = AppConfig.sessionTimeout - timeSinceLastActivity;

    // Refresh if within threshold of expiration based on last activity
    return timeUntilExpiration <= _sessionRefreshThreshold;
  }

  // Check if session is valid (exists and not expired)
  Future<bool> isSessionValid() async {
    final cookie = await getSessionCookie();
    if (cookie == null || cookie.isEmpty) return false;

    return !(await isSessionExpired());
  }

  // Inject session cookie into WebView
  Future<void> injectSessionIntoWebView() async {
    final cookie = await getSessionCookie();
    if (cookie == null) return;

    try {
      // Parse cookie string (format: "session=value" or "session=value; path=/")
      final cookieParts = cookie.split(';').first.split('=');
      if (cookieParts.length != 2) return;

      final cookieName = cookieParts[0].trim();
      final cookieValue = cookieParts[1].trim();

      // Create cookie for the backend domain
      final backendUri = Uri.parse(AppConfig.backendUrl);
      final domain = backendUri.host;

      await _cookieManager.setCookie(
        url: WebUri(AppConfig.backendUrl),
        name: cookieName,
        value: cookieValue,
        domain: domain,
        path: '/',
        expiresDate:
            DateTime.now().add(AppConfig.sessionTimeout).millisecondsSinceEpoch,
        isSecure: backendUri.scheme == 'https',
        isHttpOnly: true,
      );
    } catch (e) {
      DebugLogger.logWarn('SESSION', 'Error injecting session cookie: $e');
    }
  }

  // Clear session
  Future<void> clearSession() async {
    await _storage.deleteSecure(AppConfig.sessionCookieKey);
    await _storage.remove(_sessionCreatedAtKey);
    await _storage.remove(_sessionLastValidatedKey);
    await _storage.remove(_sessionLastValidatedOnlineKey);

    try {
      final backendUri = Uri.parse(AppConfig.backendUrl);
      await _cookieManager.deleteCookies(
        url: WebUri(AppConfig.backendUrl),
      );
    } catch (e) {
      DebugLogger.logWarn('SESSION', 'Error clearing cookies: $e');
    }
  }

  // Check if session exists
  Future<bool> hasSession() async {
    final cookie = await getSessionCookie();
    return cookie != null && cookie.isNotEmpty;
  }

  // Rotate session (update cookie and reset timestamps)
  // Called when session is refreshed from backend
  // IMPROVED: Preserves last validation time to maintain activity-based expiration
  Future<void> rotateSession(String newCookie, {bool isOnline = true}) async {
    // Save new cookie
    await _storage.setSecure(AppConfig.sessionCookieKey, newCookie);

    // Update last validation time (this extends the session based on activity)
    // Don't reset creation time - we want to track total session age
    final now = DateTime.now().millisecondsSinceEpoch;
    await _storage.setInt(_sessionLastValidatedKey, now);

    // Track online validation if this is an online request
    if (isOnline) {
      await _storage.setInt(_sessionLastValidatedOnlineKey, now);
    }

    // Only update creation time if it doesn't exist (for backward compatibility)
    final createdAt = await _storage.getInt(_sessionCreatedAtKey);
    if (createdAt == null) {
      await _storage.setInt(_sessionCreatedAtKey, now);
    }

    DebugLogger.logAuth('Session rotated - cookie updated, last validation reset');
  }
}
