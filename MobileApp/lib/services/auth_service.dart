import 'dart:convert';
import 'dart:async';
import 'dart:developer' as developer;
import 'package:flutter/foundation.dart' show kReleaseMode;
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import '../models/shared/user.dart';
import 'api_service.dart';
import 'storage_service.dart';
import 'session_service.dart';
import 'jwt_token_service.dart';
import 'user_profile_service.dart';
import 'connectivity_service.dart';
import 'error_handler.dart';
import '../utils/debug_logger.dart' show DebugLogger, LogLevel;
import '../utils/network_availability.dart';
import 'offline_cache_service.dart';
import 'offline_queue_service.dart';
import 'ai_chat_service.dart';
import 'ai_chat_persistence_service.dart';
import 'push_notification_service.dart';
import '../di/service_locator.dart';

/// Session state enum
enum SessionState {
  valid,
  expiringSoon,
  expired,
  refreshing,
}

/// Session state change event
class SessionStateEvent {
  final SessionState state;
  final Duration? timeUntilExpiration;
  final DateTime timestamp;

  SessionStateEvent({
    required this.state,
    this.timeUntilExpiration,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();
}

class AuthService {
  static final AuthService _instance = AuthService._internal();
  factory AuthService() => _instance;
  AuthService._internal();

  final ApiService _api = sl<ApiService>();
  final StorageService _storage = StorageService();
  final SessionService _session = SessionService();
  final JwtTokenService _jwtService = JwtTokenService();
  final UserProfileService _profileService = UserProfileService();
  final ConnectivityService _connectivity = ConnectivityService();

  User? _currentUser;
  User? get currentUser => _currentUser;

  // Enhanced refresh queue system
  bool _isRefreshing = false;
  Completer<bool>? _refreshCompleter;
  final List<Completer<bool>> _refreshQueue = []; // Queue for pending refresh requests

  // Rate limiting for session refresh
  DateTime? _lastRefreshAttempt;
  static const Duration _minRefreshInterval = Duration(minutes: 5);
  static const Duration _minRefreshIntervalWhenExpiring = Duration(minutes: 1); // More frequent when close to expiration

  // Periodic background refresh timer
  Timer? _periodicRefreshTimer;
  static const Duration _periodicRefreshInterval = Duration(minutes: 30);

  // Session state monitoring
  final _sessionStateController = StreamController<SessionStateEvent>.broadcast();
  Stream<SessionStateEvent> get sessionStateStream => _sessionStateController.stream;
  Timer? _sessionStateCheckTimer;

  // Flag raised while the Chrome Custom Tab OAuth flow is in progress.
  // Prevents refreshSession() from clearing auth state in the window between
  // AppLifecycleState.resumed firing (CCT closed) and the deep-link tokens
  // being delivered by app_links and saved by AzureLoginScreen.
  static bool _oauthFlowPending = false;

  /// Call from AzureLoginScreen.initState to prevent refreshSession() from
  /// clearing auth state during the OAuth browser flow.
  static set oauthFlowPending(bool pending) => _oauthFlowPending = pending;

  // Session metrics tracking
  int _refreshSuccessCount = 0;
  int _refreshFailureCount = 0;
  DateTime? _sessionStartTime;
  DateTime? _lastRefreshTime;
  final List<DateTime> _refreshAttempts = [];
  static const int _maxRefreshAttemptsHistory = 100; // Keep last 100 refresh attempts

  /// Coalesces concurrent [_loadUserProfile] calls (e.g. parallel auth checks).
  Future<void>? _userProfileLoadInFlight;

  // Login with email and password — issues JWT tokens via the mobile token endpoint.
  Future<AuthResult> loginWithEmailPassword({
    required String email,
    required String password,
    bool rememberMe = false,
  }) async {
    if (!AppConfig.isManualCredentialLoginEnabled) {
      DebugLogger.logWarn(
          'AUTH', 'Email/password login blocked for this backoffice host');
      return AuthResult.failure(
        'Email and password sign-in is only available when the app uses a Fly.io preview or local backoffice URL.',
      );
    }

    final normalizedEmail = email.trim().toLowerCase();
    DebugLogger.logAuth('Starting JWT login for email: $normalizedEmail');

    try {
      final response = await _api.post(
        AppConfig.mobileTokenEndpoint,
        body: {'email': normalizedEmail, 'password': password},
        includeAuth: false,
        contentType: ApiService.contentTypeJson,
      );

      DebugLogger.logAuth('JWT login response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        DebugLogger.logAuth('JWT login successful!');
        final data = jsonDecode(response.body) as Map<String, dynamic>;

        await _saveJwtTokensFromResponse(data);

        // Also save session cookie for WebView compatibility (if the server
        // sets one alongside the JWT response).
        final cookie = _api.extractSessionCookie(response);
        if (cookie != null) {
          await _session.saveSessionCookie(cookie);
          await _session.injectSessionIntoWebView();
        }

        if (rememberMe) {
          await _storage.setString(AppConfig.userEmailKey, normalizedEmail);
          await _storage.setBool(AppConfig.rememberMeKey, true);
        } else {
          await _storage.remove(AppConfig.userEmailKey);
          await _storage.setBool(AppConfig.rememberMeKey, false);
        }

        DebugLogger.logAuth('Loading user profile...');
        await _loadUserProfile();
        _updateSentryUserContext();

        ErrorHandler.addBreadcrumb(
          message: 'User logged in',
          category: 'auth',
          data: {'email': normalizedEmail, 'remember_me': rememberMe.toString()},
        );

        _registerRefreshCallback();
        _startPeriodicRefresh();
        _startSessionStateMonitoring();

        DebugLogger.logAuth('JWT login complete!');
        return AuthResult.success();
      }

      if (response.statusCode == 429) {
        return AuthResult.failure('Too many login attempts. Please try again later.');
      }

      String errorMessage = 'Invalid email or password.';
      try {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        errorMessage = data['error']?.toString() ?? errorMessage;
      } catch (_) {}

      DebugLogger.logError('JWT login failed: $errorMessage');
      return AuthResult.failure(errorMessage);
    } catch (e, stackTrace) {
      DebugLogger.logError('EXCEPTION during JWT login: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      developer.log(
        'JWT login failed',
        name: 'ngo.auth',
        error: e,
        stackTrace: stackTrace,
      );

      // Release: short user-facing copy. Debug/profile: keep exception text for
      // on-screen SnackBar (auth layer was replacing everything with generics).
      if (!kReleaseMode) {
        return AuthResult.failure('${e.runtimeType}: $e');
      }

      final errorMessage = e.toString().toLowerCase();
      if (errorMessage.contains('unable to connect') ||
          errorMessage.contains('failed host lookup') ||
          errorMessage.contains('network is unreachable') ||
          errorMessage.contains('connection refused')) {
        return AuthResult.failure(
            'Unable to connect to server. Please check your internet connection and try again.');
      }
      if (errorMessage.contains('timeout') || errorMessage.contains('timed out')) {
        return AuthResult.failure(
            'Connection timed out. Please check your internet connection and try again.');
      }
      if (errorMessage.contains('no internet connection')) {
        return AuthResult.failure(
            'No internet connection. Please check your network and try again.');
      }
      return AuthResult.failure(
          'Something went wrong. Please check your connection and try again.');
    }
  }

  /// Exchange an existing Flask session cookie (e.g. from Azure SSO) for JWT tokens.
  /// Called by [AzureLoginScreen] immediately after the WebView session is captured.
  Future<bool> exchangeSessionForJwtTokens() async {
    DebugLogger.logAuth('Exchanging session cookie for JWT tokens...');
    try {
      final response = await _api.post(
        AppConfig.mobileExchangeSessionEndpoint,
        body: {},
        includeAuth: true,
        contentType: ApiService.contentTypeJson,
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        await _saveJwtTokensFromResponse(data);
        DebugLogger.logAuth('Session exchanged for JWT tokens successfully');
        return true;
      }
      DebugLogger.logWarn('AUTH',
          'Session exchange failed with status ${response.statusCode}');
      return false;
    } catch (e) {
      DebugLogger.logError('Error exchanging session for JWT tokens: $e');
      return false;
    }
  }

  /// Parse and persist JWT tokens from a server response body.
  ///
  /// Supports the mobile envelope `{ "success": true, "data": { "access_token": ... } }`
  /// and a flat map for compatibility.
  Future<void> _saveJwtTokensFromResponse(Map<String, dynamic> data) async {
    final root = _unwrapMobileTokenPayload(data);
    final accessToken = root['access_token']?.toString();
    final refreshToken = root['refresh_token']?.toString();
    final expiresIn = _parseExpiresInSeconds(root['expires_in']);

    if (accessToken != null &&
        accessToken.isNotEmpty &&
        refreshToken != null &&
        refreshToken.isNotEmpty) {
      await _jwtService.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresIn: expiresIn,
      );
      // Keep session-level timestamps in sync so the pre-request
      // isSessionExpired() guard (which checks these timestamps)
      // does not reject follow-up authenticated requests.
      await _session.updateLastValidation();
    } else {
      DebugLogger.logWarn(
        'AUTH',
        'Token response missing access_token/refresh_token after unwrapping '
        '(keys: ${root.keys.join(", ")})',
      );
    }
  }

  /// Mobile routes return tokens inside `data`; unwrap when present.
  Map<String, dynamic> _unwrapMobileTokenPayload(Map<String, dynamic> body) {
    final inner = body['data'];
    if (inner is Map<String, dynamic>) {
      return inner;
    }
    return body;
  }

  int _parseExpiresInSeconds(dynamic raw) {
    if (raw is int) return raw;
    if (raw is double) return raw.round();
    if (raw is num) return raw.toInt();
    return 1800;
  }

  /// Quick login for testing purposes
  /// Security: debug builds against a local backoffice only
  Future<AuthResult> quickLogin(String email, String password) async {
    if (!AppConfig.isQuickLoginEnabled) {
      DebugLogger.logWarn('AUTH', 'Quick login blocked (requires debug + local backoffice)');
      return AuthResult.failure(
        'Quick login is only available in debug mode with a local backoffice URL',
      );
    }

    return await loginWithEmailPassword(
      email: email,
      password: password,
      rememberMe: true,
    );
  }

  // Update user role (can be called from dashboard provider)
  void updateUserRole(String role) {
    if (_currentUser != null) {
      _currentUser = _currentUser!.copyWith(role: role);
      DebugLogger.logAuth('Updated user role to: $role');

      // Update Sentry user context when role changes
      _updateSentryUserContext();
    }
  }

  // Load user profile using the new UserProfileService
  // This service attempts API first, then falls back to HTML parsing
  Future<void> _loadUserProfile() async {
    if (_userProfileLoadInFlight != null) {
      await _userProfileLoadInFlight;
      return;
    }
    final load = _loadUserProfileBody();
    _userProfileLoadInFlight = load;
    try {
      await load;
    } finally {
      if (identical(_userProfileLoadInFlight, load)) {
        _userProfileLoadInFlight = null;
      }
    }
  }

  Future<void> _loadUserProfileBody() async {
    try {
      DebugLogger.logAuth('Loading user profile...');

      // Use the new UserProfileService which handles API + HTML fallback
      final user = await _profileService.fetchUserProfile();

      if (user != null) {
        _currentUser = user;
        DebugLogger.logAuth(
            'User profile loaded: ${_currentUser?.email}, role: ${_currentUser?.role}, profile_color: ${_currentUser?.profileColor ?? "null"}');

        // Update Sentry user context when profile is loaded
        _updateSentryUserContext();
      } else {
        // If profile service returns null, create a minimal user from stored email
        DebugLogger.logAuth(
            'Profile service returned null, creating minimal user from stored email');
        final email = await _storage.getString(AppConfig.userEmailKey) ?? '';
        if (email.isNotEmpty) {
          _currentUser = User(
            id: 0,
            email: email,
            role: 'focal_point',
          );
        } else {
          DebugLogger.logAuth('No email found in storage, cannot create user');
          _currentUser = null;
        }
      }
    } on AuthenticationException {
      // Re-throw auth errors - they should be handled by caller
      DebugLogger.logAuth('Authentication error during profile load');
      rethrow;
    } catch (e, stackTrace) {
      DebugLogger.logAuth('Error loading user profile: $e');
      DebugLogger.logAuth('Stack trace: $stackTrace');

      // Create a basic user object as fallback if we have email
      final email = await _storage.getString(AppConfig.userEmailKey) ?? '';
      if (email.isNotEmpty) {
        _currentUser = User(
          id: 0,
          email: email,
          role: 'focal_point',
        );
        DebugLogger.logAuth('Created fallback user from email: $email');
      } else {
        _currentUser = null;
        DebugLogger.logAuth('No email available for fallback user');
      }
    }
  }

  /// Update Sentry user context with current user info
  void _updateSentryUserContext() {
    if (_currentUser == null) {
      ErrorHandler.clearUserContext();
      return;
    }

    ErrorHandler.setUserContext(
      userId: _currentUser!.id.toString(),
      email: _currentUser!.email,
      username: _currentUser!.name ?? _currentUser!.email,
      additionalData: {
        'role': _currentUser!.role,
        if (_currentUser!.title != null) 'title': _currentUser!.title!,
        'chatbot_enabled': _currentUser!.chatbotEnabled.toString(),
        if (_currentUser!.countryIds != null && _currentUser!.countryIds!.isNotEmpty)
          'country_ids': _currentUser!.countryIds!.join(','),
      },
    );
  }

  // Logout
  Future<void> logout() async {
    // Unregister device BEFORE the logout API call because logout blacklists
    // the JWT — any authenticated request after that would get 401.
    try {
      await PushNotificationService().unregisterDevice();
    } catch (_) {}

    try {
      ErrorHandler.addBreadcrumb(
        message: 'User logging out',
        category: 'auth',
        data: {'email': _currentUser?.email ?? 'unknown'},
      );

      // skipExpiredGuard: bypass _guardSessionExpiry so the HTTP request is
      // always sent even when the access token has just expired.  The backend
      // logout endpoint accepts expired-but-signed tokens and blacklists the
      // session using the sid claim.
      // queueOnOffline: false — do not queue logout for replay; by the time it
      // would run the tokens will already have been wiped locally.
      await _api.post(
        AppConfig.logoutEndpoint,
        skipExpiredGuard: true,
        queueOnOffline: false,
      );
    } catch (e) {
      DebugLogger.logError('Error during logout API call: $e');
    } finally {
      await _jwtService.clearTokens();
      await AiChatService().clearToken();
      await _session.clearSession();

      // Preserve the device install ID so the same physical device reuses the
      // same token on next login (prevents duplicate device rows).
      // Wrapped in try-catch so a Keychain/platform error doesn't abort the
      // rest of the logout cleanup (setting _currentUser = null, stopping
      // timers, etc.).
      String? deviceInstallId;
      try {
        deviceInstallId =
            await _storage.getSecure(AppConfig.persistentDeviceInstallIdKey);
      } catch (_) {}

      await _storage.clearSecure();
      await _storage.clear();

      // Restore the device install ID after wiping secure storage.
      try {
        if (deviceInstallId != null && deviceInstallId.isNotEmpty) {
          await _storage.setSecure(
              AppConfig.persistentDeviceInstallIdKey, deviceInstallId);
        }
      } catch (_) {}
      await OfflineCacheService().clearAll();
      await OfflineQueueService().clearAll();
      await AiChatPersistenceService().clearAllConversations();

      // Clear Sentry user context on logout
      ErrorHandler.clearUserContext();

      _currentUser = null;

      // Add breadcrumb after logout
      ErrorHandler.addBreadcrumb(
        message: 'User logged out',
        category: 'auth',
      );

      // Stop periodic refresh timer on logout
      _stopPeriodicRefresh();

      // Stop session state monitoring
      _stopSessionStateMonitoring();

      // Log final session metrics
      _logSessionMetrics('session_ended');

      // Emit expired state
      _emitSessionState(SessionState.expired);

      // Reset metrics and rate limiter state
      _sessionStartTime = null;
      _lastRefreshTime = null;
      _lastRefreshAttempt = null;
      _refreshSuccessCount = 0;
      _refreshFailureCount = 0;
      _refreshAttempts.clear();
    }
  }

  /// Register this service's refresh method as the callback for ApiService's
  /// 401 auto-retry handler.  This breaks the circular import — ApiService
  /// never imports AuthService directly.
  void _registerRefreshCallback() {
    ApiService.tokenRefreshCallback =
        () => refreshSession(forceRefresh: true);
  }

  // Start periodic background refresh timer
  // This ensures sessions stay alive during active use
  void _startPeriodicRefresh() {
    // Cancel existing timer if any
    _stopPeriodicRefresh();

    DebugLogger.logAuth('Starting periodic session refresh timer (every ${_periodicRefreshInterval.inMinutes} minutes)');

    _periodicRefreshTimer = Timer.periodic(_periodicRefreshInterval, (_) async {
      // Only refresh if we have a valid session
      final hasSession = await _session.hasSession();
      if (!hasSession) {
        DebugLogger.logAuth('No session found - stopping periodic refresh');
        _stopPeriodicRefresh();
        return;
      }

      // Check if session is expired
      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        DebugLogger.logAuth('Session expired - stopping periodic refresh');
        _stopPeriodicRefresh();
        return;
      }

      // Refresh session in background (non-blocking)
      DebugLogger.logAuth('Periodic session refresh triggered');
      refreshSession().then((success) {
        if (success) {
          DebugLogger.logAuth('Periodic session refresh completed successfully');
        } else {
          DebugLogger.logWarn('AUTH', 'Periodic session refresh failed');
        }
      }).catchError((e) {
        DebugLogger.logWarn('AUTH', 'Periodic session refresh error: $e');
      });
    });
  }

  // Stop periodic background refresh timer
  void _stopPeriodicRefresh() {
    if (_periodicRefreshTimer != null) {
      DebugLogger.logAuth('Stopping periodic session refresh timer');
      _periodicRefreshTimer!.cancel();
      _periodicRefreshTimer = null;
    }
  }

  // Start session state monitoring
  void _startSessionStateMonitoring() {
    // Cancel existing timer if any
    _stopSessionStateMonitoring();

    DebugLogger.logAuth('Starting session state monitoring');

    // Check session state every minute
    _sessionStateCheckTimer = Timer.periodic(const Duration(minutes: 1), (_) async {
      await _checkAndEmitSessionState();
    });

    // Also check immediately
    _checkAndEmitSessionState();
  }

  // Stop session state monitoring
  void _stopSessionStateMonitoring() {
    if (_sessionStateCheckTimer != null) {
      DebugLogger.logAuth('Stopping session state monitoring');
      _sessionStateCheckTimer!.cancel();
      _sessionStateCheckTimer = null;
    }
  }

  // Check session state and emit event if changed
  Future<void> _checkAndEmitSessionState() async {
    try {
      final hasSession = await _session.hasSession();
      if (!hasSession) {
        _emitSessionState(SessionState.expired);
        return;
      }

      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        _emitSessionState(SessionState.expired);
        return;
      }

      if (_isRefreshing) {
        _emitSessionState(SessionState.refreshing);
        return;
      }

      final timeUntilExpiration = await _getTimeUntilExpiration();
      if (timeUntilExpiration != null && timeUntilExpiration <= const Duration(minutes: 15)) {
        _emitSessionState(SessionState.expiringSoon, timeUntilExpiration: timeUntilExpiration);
        return;
      }

      _emitSessionState(SessionState.valid, timeUntilExpiration: timeUntilExpiration);
    } catch (e) {
      DebugLogger.logWarn('AUTH', 'Error checking session state: $e');
    }
  }

  // Emit session state event
  void _emitSessionState(SessionState state, {Duration? timeUntilExpiration}) {
    final event = SessionStateEvent(
      state: state,
      timeUntilExpiration: timeUntilExpiration,
    );
    _sessionStateController.add(event);
    DebugLogger.logAuth('Session state changed: $state${timeUntilExpiration != null ? " (expires in ${timeUntilExpiration.inMinutes} min)" : ""}');
  }

  // Log session metrics for debugging and monitoring
  void _logSessionMetrics(String event) {
    final now = DateTime.now();
    final sessionDuration = _sessionStartTime != null
        ? now.difference(_sessionStartTime!)
        : null;

    final totalRefreshAttempts = _refreshSuccessCount + _refreshFailureCount;
    final successRate = totalRefreshAttempts > 0
        ? (_refreshSuccessCount / totalRefreshAttempts * 100).toStringAsFixed(1)
        : '0.0';

    final timeSinceLastRefresh = _lastRefreshTime != null
        ? now.difference(_lastRefreshTime!)
        : null;

    DebugLogger.logAuth('Session Metrics - Event: $event | '
        'Session Duration: ${sessionDuration != null ? "${sessionDuration.inMinutes} min" : "N/A"} | '
        'Refresh Success: $_refreshSuccessCount | '
        'Refresh Failures: $_refreshFailureCount | '
        'Success Rate: $successRate% | '
        'Time Since Last Refresh: ${timeSinceLastRefresh != null ? "${timeSinceLastRefresh.inMinutes} min" : "N/A"} | '
        'Total Refresh Attempts: ${_refreshAttempts.length}');
  }

  // Get session metrics summary
  Map<String, dynamic> getSessionMetrics() {
    final now = DateTime.now();
    final sessionDuration = _sessionStartTime != null
        ? now.difference(_sessionStartTime!)
        : null;

    final totalRefreshAttempts = _refreshSuccessCount + _refreshFailureCount;
    final successRate = totalRefreshAttempts > 0
        ? _refreshSuccessCount / totalRefreshAttempts
        : 0.0;

    final timeSinceLastRefresh = _lastRefreshTime != null
        ? now.difference(_lastRefreshTime!)
        : null;

    // Calculate average time between refreshes
    Duration? avgRefreshInterval;
    if (_refreshAttempts.length > 1) {
      final intervals = <Duration>[];
      for (int i = 1; i < _refreshAttempts.length; i++) {
        intervals.add(_refreshAttempts[i].difference(_refreshAttempts[i - 1]));
      }
      if (intervals.isNotEmpty) {
        final totalMs = intervals.fold<int>(0, (sum, d) => sum + d.inMilliseconds);
        avgRefreshInterval = Duration(milliseconds: totalMs ~/ intervals.length);
      }
    }

    return {
      'sessionDuration': sessionDuration?.inMinutes,
      'refreshSuccessCount': _refreshSuccessCount,
      'refreshFailureCount': _refreshFailureCount,
      'successRate': successRate,
      'timeSinceLastRefresh': timeSinceLastRefresh?.inMinutes,
      'avgRefreshInterval': avgRefreshInterval?.inMinutes,
      'totalRefreshAttempts': _refreshAttempts.length,
    };
  }

  // Refresh session by making a lightweight API call
  // This extends the session lifetime on the backend
  // IMPROVED: Added retry logic, enhanced queue system, and rate limiting
  Future<bool> refreshSession({int retryCount = 0, bool forceRefresh = false}) async {
    // If already refreshing, queue this request
    if (_isRefreshing && _refreshCompleter != null) {
      DebugLogger.logAuth('Session refresh already in progress, queuing request...');
      final queuedCompleter = Completer<bool>();
      _refreshQueue.add(queuedCompleter);

      // Wait for the current refresh to complete, then process queue
      try {
        final result = await _refreshCompleter!.future;
        // Process queue after current refresh completes
        _processRefreshQueue(result);
        return result;
      } catch (e) {
        // If current refresh failed, process queue with failure
        _processRefreshQueue(false);
        rethrow;
      }
    }

    // Context-aware rate limiting: allow more frequent refreshes when session is close to expiration
    final now = DateTime.now();
    if (!forceRefresh && _lastRefreshAttempt != null) {
      // Check if session is close to expiration (within 1 hour)
      final needsRefresh = await _session.needsRefresh();
      final timeUntilExpiration = await _getTimeUntilExpiration();

      // Use shorter interval if session is expiring soon (within 1 hour)
      final minInterval = (needsRefresh && timeUntilExpiration != null &&
                          timeUntilExpiration <= const Duration(hours: 1))
          ? _minRefreshIntervalWhenExpiring
          : _minRefreshInterval;

      if (now.difference(_lastRefreshAttempt!) < minInterval) {
        DebugLogger.logAuth('Refresh rate limited - too soon since last refresh (${now.difference(_lastRefreshAttempt!).inMinutes} minutes ago, min interval: ${minInterval.inMinutes} min)');
        return true; // Assume still valid
      }
    }

    // Set refresh lock
    _isRefreshing = true;
    _refreshCompleter = Completer<bool>();
    _lastRefreshAttempt = now;

    // Emit refreshing state
    _emitSessionState(SessionState.refreshing);

    try {
      final result = await _doRefreshSession(retryCount: retryCount);
      _refreshCompleter!.complete(result);

      // Process any queued refresh requests
      _processRefreshQueue(result);

      // Update session state after refresh
      await _checkAndEmitSessionState();

      return result;
    } catch (e) {
      _refreshCompleter!.completeError(e);

      // Process queue with failure
      _processRefreshQueue(false);

      rethrow;
    } finally {
      _isRefreshing = false;
      _refreshCompleter = null;
    }
  }

  // Process queued refresh requests sequentially
  void _processRefreshQueue(bool lastResult) {
    if (_refreshQueue.isEmpty) return;

    DebugLogger.logAuth('Processing ${_refreshQueue.length} queued refresh request(s)');

    // Complete all queued requests with the last result
    // Since they're all waiting for the same refresh, they can share the result
    while (_refreshQueue.isNotEmpty) {
      final completer = _refreshQueue.removeAt(0);
      if (!completer.isCompleted) {
        completer.complete(lastResult);
      }
    }
  }

  // Internal method that performs the actual token refresh via JWT refresh token.
  Future<bool> _doRefreshSession({int retryCount = 0}) async {
    const maxRetries = 2;
    try {
      DebugLogger.logAuth('Refreshing JWT tokens... (attempt ${retryCount + 1}/${maxRetries + 1})');

      final refreshToken = await _jwtService.getRefreshToken();
      if (refreshToken == null) {
        if (_oauthFlowPending) {
          // The Chrome Custom Tab OAuth flow is still in progress. The deep-link
          // tokens have not been saved yet — do NOT wipe auth state here, because
          // AzureLoginScreen is about to save fresh tokens and load the user.
          DebugLogger.logWarn('AUTH',
              'No refresh token — OAuth flow pending, skipping auth-state clear');
          return false;
        }
        DebugLogger.logWarn('AUTH', 'No refresh token available — clearing auth state');
        await _jwtService.clearTokens();
        await _session.clearSession();
        _currentUser = null;
        return false;
      }

      final response = await _api.post(
        AppConfig.mobileRefreshEndpoint,
        body: {'refresh_token': refreshToken},
        includeAuth: false,
        contentType: ApiService.contentTypeJson,
      );

      if (response.statusCode == 200) {
        DebugLogger.logAuth('JWT tokens refreshed successfully');
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        await _saveJwtTokensFromResponse(data);

        _refreshSuccessCount++;
        _lastRefreshTime = DateTime.now();
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }
        _logSessionMetrics('refresh_success');
        return true;
      } else if (response.statusCode == 401 || response.statusCode == 403) {
        DebugLogger.logWarn('AUTH',
            'Refresh token rejected (status: ${response.statusCode}) — clearing auth state');
        _refreshFailureCount++;
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }
        _logSessionMetrics('refresh_failure_expired');

        await _jwtService.clearTokens();
        await _session.clearSession();
        _currentUser = null;
        return false;
      } else {
        if (retryCount < maxRetries) {
          DebugLogger.logWarn('AUTH',
              'JWT refresh failed with status ${response.statusCode}, retrying...');
          await Future.delayed(Duration(seconds: 1 * (retryCount + 1)));
          return await _doRefreshSession(retryCount: retryCount + 1);
        }
        DebugLogger.logError(
            'JWT refresh failed with status ${response.statusCode} after ${maxRetries + 1} attempts');
        _refreshFailureCount++;
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }
        _logSessionMetrics('refresh_failure_error');
        // Do not return false here: [ApiService] treats false as "refresh
        // definitively failed" and clears JWT + session. HTTP 5xx / edge
        // responses are often transient (especially on iOS right after resume).
        throw Exception(
            'JWT refresh failed with HTTP ${response.statusCode} after ${maxRetries + 1} attempts');
      }
    } on TimeoutException catch (e, st) {
      if (retryCount < maxRetries) {
        DebugLogger.logWarn('AUTH', 'JWT refresh timeout, retrying...');
        await Future.delayed(Duration(seconds: 1 * (retryCount + 1)));
        return await _doRefreshSession(retryCount: retryCount + 1);
      }
      DebugLogger.logError('JWT refresh timeout after ${maxRetries + 1} attempts');
      _refreshFailureCount++;
      _refreshAttempts.add(DateTime.now());
      if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
        _refreshAttempts.removeAt(0);
      }
      _logSessionMetrics('refresh_failure_timeout');
      // Rethrow so [ApiService] does not clear tokens (see 401 handler). User
      // stays logged in; the next API call or resume can refresh again.
      Error.throwWithStackTrace(e, st);
    } on AuthenticationException {
      DebugLogger.logWarn('AUTH', 'Authentication error during JWT refresh');
      await _jwtService.clearTokens();
      await _session.clearSession();
      _currentUser = null;
      return false;
    } catch (e) {
      if (retryCount < maxRetries) {
        DebugLogger.logWarn('AUTH', 'Error during JWT refresh: $e, retrying...');
        await Future.delayed(Duration(seconds: 1 * (retryCount + 1)));
        return await _doRefreshSession(retryCount: retryCount + 1);
      }
      DebugLogger.logError('JWT refresh error after ${maxRetries + 1} attempts: $e');
      _refreshFailureCount++;
      _refreshAttempts.add(DateTime.now());
      if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
        _refreshAttempts.removeAt(0);
      }
      _logSessionMetrics('refresh_failure_exception');
      // Rethrow transient errors — do not collapse to false or [ApiService]
      // will wipe auth state (common on iOS when the network is not ready yet).
      rethrow;
    }
  }

  /// Restore [currentUser] from [AppConfig.cachedUserProfileKey] after process
  /// restart (AuthProvider already reads this; AuthService must mirror it for
  /// [isLoggedIn] before any network validation).
  Future<void> _hydrateCurrentUserFromAuthCache() async {
    if (_currentUser != null) return;
    try {
      final cached = await _storage.getString(AppConfig.cachedUserProfileKey);
      if (cached == null || cached.isEmpty) return;
      final data = jsonDecode(cached) as Map<String, dynamic>;
      _currentUser = User.fromJson(data);
      DebugLogger.logAuth(
          'Hydrated current user from disk cache (${_currentUser!.email})');
      _updateSentryUserContext();
    } catch (e, stackTrace) {
      DebugLogger.logWarn(
          'AUTH', 'Hydrate user from auth cache failed: $e\n$stackTrace');
    }
  }

  // Check if user is logged in
  // forceRevalidate: if true, always validate session even if user is cached
  Future<bool> isLoggedIn({bool forceRevalidate = false}) async {
    DebugLogger.logAuth(
        'isLoggedIn called (forceRevalidate: $forceRevalidate, '
        'cachedUser: ${_currentUser != null}, '
        'connectivity: ${_connectivity.currentStatus})');
    // Primary gate: JWT access token (preferred) or legacy session cookie.
    final hasJwt = await _jwtService.hasTokens();
    final hasSession = await _session.hasSession();
    if (!hasJwt && !hasSession) {
      DebugLogger.logAuth('No JWT tokens or session cookie found');
      _currentUser = null;
      return false;
    }

    await _hydrateCurrentUserFromAuthCache();

    // If we have a JWT and access is expired, refresh only when we can reach
    // the server. Offline (or backend marked unreachable), a failed refresh
    // must NOT log the user out — keep credentials and fall through to offline
    // / defer rules below.
    if (hasJwt) {
      final accessExpired = await _jwtService.isAccessTokenExpired();
      if (accessExpired) {
        final offlineOrUnreachable =
            _connectivity.isOffline || shouldDeferRemoteFetch;
        if (offlineOrUnreachable) {
          DebugLogger.logAuth(
              'Access token expired but no reliable path to refresh '
              '(offline or backend deferred) — keeping local session for '
              'offline use; will refresh when online');
        } else {
          DebugLogger.logAuth('Access token expired — attempting silent JWT refresh');
          final refreshed = await refreshSession(forceRefresh: true);
          if (!refreshed) {
            DebugLogger.logWarn('AUTH', 'Silent JWT refresh failed — user must re-login');
            _currentUser = null;
            return false;
          }
        }
      }
    }

    // Client-side staleness check — used only to decide how aggressively to
    // validate with the server.  Do NOT clear the cookie here: the server is
    // the authoritative source (session cookie may still be valid for days even
    // if the local "last validated" timestamp is old, e.g. after the phone was
    // off overnight).  We force a server round-trip and only evict on a real
    // 401/403 response.
    final isExpiredClientSide = await _session.isSessionExpired();
    if (isExpiredClientSide) {
      DebugLogger.logWarn('AUTH',
          'Session appears stale (client-side) — forcing server validation');
      forceRevalidate = true;
    }

    // IMPROVED: Proactive session refresh
    // Check if session needs refresh (within threshold of expiration)
    final needsRefresh = await _session.needsRefresh();
    if (needsRefresh && !forceRevalidate) {
      DebugLogger.logAuth('Session needs refresh, refreshing proactively...');
      // Refresh proactively - this ensures session stays alive during active use
      // Don't await - let it happen in background, but log failures
      refreshSession().then((success) {
        if (success) {
          DebugLogger.logAuth('Proactive session refresh completed successfully');
        } else {
          DebugLogger.logWarn('AUTH', 'Proactive session refresh failed - session may expire soon');
        }
      }).catchError((e) {
        DebugLogger.logWarn('AUTH', 'Background session refresh error: $e');
      });
    }

    // IMPROVED: Also refresh if session is getting old but not yet expired
    // This prevents expiration during active use
    final lastValidated = await _session.getSessionLastValidated();
    if (lastValidated != null && !needsRefresh && !forceRevalidate) {
      final now = DateTime.now();
      final timeSinceLastActivity = now.difference(lastValidated);
      // Refresh if session is more than 4 hours old (halfway through 8-hour timeout)
      // This keeps sessions alive during long active sessions
      if (timeSinceLastActivity >= const Duration(hours: 4) &&
          timeSinceLastActivity < AppConfig.sessionTimeout - const Duration(minutes: 30)) {
        DebugLogger.logAuth('Session is ${timeSinceLastActivity.inHours}h old, refreshing proactively...');
        refreshSession().catchError((e) {
          DebugLogger.logWarn('AUTH', 'Proactive refresh error: $e');
          return false;
        });
      }
    }

    // If we already have a user loaded and not forcing revalidation,
    // still validate but use cached user as fallback
    // This prevents unnecessary network calls on every check while still validating
    if (_currentUser != null && !forceRevalidate) {
      DebugLogger.logAuth(
          'User already loaded, validating session in background...');
      // Still validate in background, but return cached state immediately
      // This allows UI to render while validation happens
      _validateSessionInBackground();
      return true;
    }

    // IMPROVED: Handle offline scenario - check if session is valid for offline operations
    if (_connectivity.isOffline) {
      DebugLogger.logAuth(
          'Device is offline (connectivity: ${_connectivity.currentStatus}) '
          '— checking offline session validity...');
      final isValidForOffline = await _session.isSessionValidForOffline();
      final hasJwt = await _jwtService.hasTokens();
      final jwtExpired = hasJwt ? await _jwtService.isAccessTokenExpired() : null;
      if (isValidForOffline) {
        final hasUser = _currentUser != null;
        DebugLogger.logAuth(
            'Offline session valid — '
            'cachedUser: $hasUser${hasUser ? " (${_currentUser!.email})" : ""}, '
            'hasJwt: $hasJwt, jwtExpired: $jwtExpired, '
            'returning: $hasUser');
        return hasUser;
      } else {
        DebugLogger.logWarn('AUTH',
            'Offline session NOT valid — '
            'hasJwt: $hasJwt, jwtExpired: $jwtExpired, '
            'returning: false');
        return false;
      }
    }

    // Radio can show "connected" while the backoffice is unreachable. After
    // [BackendReachabilityService] marks defer, skip the live session probe so
    // pull‑to‑refresh returns immediately when a cached user exists.
    if (shouldDeferRemoteFetch) {
      final isValidForOffline = await _session.isSessionValidForOffline();
      if (isValidForOffline) {
        if (_currentUser != null) {
          DebugLogger.logAuth(
              'Backend defer active — skipping live session check (cached user)');
          _registerRefreshCallback();
          if (_periodicRefreshTimer == null) {
            _startPeriodicRefresh();
          }
          if (_sessionStateCheckTimer == null) {
            _startSessionStateMonitoring();
          }
          return true;
        }
        DebugLogger.logAuth(
            'Backend defer active — loading profile without live session probe');
        await _loadUserProfile();
        _registerRefreshCallback();
        if (_periodicRefreshTimer == null) {
          _startPeriodicRefresh();
        }
        if (_sessionStateCheckTimer == null) {
          _startSessionStateMonitoring();
        }
        return _currentUser != null;
      }
    }

    // Validate session with backend using the JWT-aware mobile session endpoint.
    // We must NOT use /account-settings here — that route uses @login_required
    // (cookie-based) and ignores the JWT Bearer token.  Flask redirects the JWT
    // request to /login; http.Client follows the redirect and returns 200 (login
    // page HTML), which previously made the app think the session was still valid
    // even after an admin force-logout.  The mobile session endpoint is protected
    // by @mobile_auth_required, validates the JWT (including the blacklist), and
    // returns a proper JSON 401 when the session has been revoked.
    try {
      DebugLogger.logAuth('Validating session with backend (mobile session check)...');
      final response = await _api.get(
        AppConfig.mobileSessionCheckEndpoint,
        timeout: const Duration(seconds: 5),
      );

      if (response.statusCode == 200) {
        // Session is valid, always reload user profile to get latest role
        await _loadUserProfile();
        DebugLogger.logAuth('Session is valid');
        // Restart background timers and refresh callback if they stopped
        // (e.g. after the app was killed and relaunched).
        _registerRefreshCallback();
        if (_periodicRefreshTimer == null) {
          _startPeriodicRefresh();
        }
        if (_sessionStateCheckTimer == null) {
          _startSessionStateMonitoring();
        }
        return true;
      } else if (response.statusCode == 401 || response.statusCode == 403) {
        // Session expired or invalid
        DebugLogger.logWarn('AUTH',
            'Session expired or invalid (status: ${response.statusCode})');
        await _session.clearSession();
        _currentUser = null;
        return false;
      } else {
        // Other error - assume session is still valid but log it
        DebugLogger.logWarn('AUTH',
            'Session validation returned status ${response.statusCode}, assuming valid');
        // Only load profile if we don't have one
        if (_currentUser == null) {
          await _loadUserProfile();
        }
        return true;
      }
    } on AuthenticationException {
      DebugLogger.logWarn('AUTH', 'Authentication exception during validation');
      await _session.clearSession();
      _currentUser = null;
      return false;
    } on TimeoutException {
      DebugLogger.logWarn(
          'AUTH', 'Session validation timeout - checking offline validity');
      // On timeout, check if session is valid for offline operations
      final isValidForOffline = await _session.isSessionValidForOffline();
      if (isValidForOffline && _currentUser != null) {
        DebugLogger.logAuth('Using cached session for offline operations');
        return true;
      }
      // Try to load profile even on timeout if we don't have one
      if (_currentUser == null) {
        try {
          await _loadUserProfile();
        } catch (e) {
          DebugLogger.logWarn('AUTH', 'Failed to load profile on timeout: $e');
        }
      }
      return hasSession && _currentUser != null;
    } catch (e) {
      final transient = isTransientBackendFailure(e);
      if (transient) {
        DebugLogger.logAuth(
          'Session validation: transient transport error ($e)',
          level: LogLevel.debug,
        );
      } else {
        DebugLogger.logError('Error validating session: $e');
      }
      // On error, check if we're offline (or backend recently unreachable) and
      // session is valid for offline-style use.
      if (_connectivity.isOffline || transient || shouldDeferRemoteFetch) {
        final isValidForOffline = await _session.isSessionValidForOffline();
        if (isValidForOffline && _currentUser != null) {
          DebugLogger.logAuth('Using cached session for offline operations (error occurred)');
          return true;
        }
      }
      // On error, check if we have a cached user
      if (_currentUser != null) {
        DebugLogger.logAuth(
          transient
              ? 'Using cached user after transient network error during validation'
              : 'Using cached user due to validation error',
          level: transient ? LogLevel.debug : LogLevel.warn,
        );
        return true;
      }
      // No cached user and validation failed
      return false;
    }
  }

  // Helper method to get time until session expiration
  Future<Duration?> _getTimeUntilExpiration() async {
    final lastValidated = await _session.getSessionLastValidated();
    if (lastValidated == null) {
      final createdAt = await _session.getSessionCreatedAt();
      if (createdAt == null) return null;
      final now = DateTime.now();
      final age = now.difference(createdAt);
      return AppConfig.sessionTimeout - age;
    }

    final now = DateTime.now();
    final timeSinceLastActivity = now.difference(lastValidated);
    return AppConfig.sessionTimeout - timeSinceLastActivity;
  }

  // Validate session in background without blocking.
  // Uses the JWT-aware mobile session endpoint so that admin force-logouts
  // (which blacklist the JWT session_id) are detected immediately.
  void _validateSessionInBackground() {
    _api
        .get(
      AppConfig.mobileSessionCheckEndpoint,
      timeout: const Duration(seconds: 5),
      useCache: false,
    )
        .then((response) {
      if (response.statusCode == 200) {
        // Session is still valid; refresh user profile to pick up role changes.
        _loadUserProfile();
      } else if (response.statusCode == 401 || response.statusCode == 403) {
        DebugLogger.logWarn('AUTH', 'Background validation: Session revoked or expired');
        _jwtService.clearTokens();
        _session.clearSession();
        _currentUser = null;
      }
    }).catchError((e) {
      // ApiService throws AuthenticationException when a 401 triggers a failed
      // token refresh (e.g. refresh token is also blacklisted).  Treat this
      // the same as an explicit 401 — clear auth state so the next isLoggedIn()
      // call returns false and the UI redirects to the login screen.
      if (e is AuthenticationException) {
        DebugLogger.logWarn('AUTH', 'Background validation: AuthenticationException — clearing auth state');
        _jwtService.clearTokens();
        _session.clearSession();
        _currentUser = null;
      } else {
        // Network errors, timeouts, etc. — log but keep the cached user.
        DebugLogger.logWarn('AUTH', 'Background validation error (network/transient, ignored): $e');
      }
    });
  }

  // Get saved email for remember me
  Future<String?> getSavedEmail() async {
    final rememberMe = await _storage.getBool(AppConfig.rememberMeKey);
    if (rememberMe == true) {
      return await _storage.getString(AppConfig.userEmailKey);
    }
    return null;
  }

  String _extractErrorMessage(http.Response response) {
    DebugLogger.logAuth('Extracting error message from response...');
    try {
      final body = jsonDecode(response.body);
      final error = body['error'] ?? body['message'] ?? 'Login failed';
      DebugLogger.logAuth('Extracted JSON error: $error');
      return error;
    } catch (e) {
      DebugLogger.logAuth(
          'Response is not JSON, trying to extract from HTML...');
      // Try to extract error from HTML if JSON parsing fails
      final html = response.body;

      // First, try to find the error in <p> tags (Flask error pages use this)
      final pErrorPattern = RegExp(r'<p[^>]*>([^<]+)', caseSensitive: false);
      final pMatch = pErrorPattern.firstMatch(html);
      if (pMatch != null && pMatch.groupCount >= 1) {
        final error = pMatch.group(1)?.trim();
        if (error != null &&
            error.isNotEmpty &&
            !error.toLowerCase().contains('html')) {
          DebugLogger.logAuth('Extracted HTML error from <p> tag: $error');
          return error;
        }
      }

      // Fallback: Look for flash messages or error messages in HTML
      final errorPattern = RegExp(
        r'<[^>]*class=[\x22\x27][^\x22\x27]*alert[^\x22\x27]*[^>]*>([^<]+)',
        caseSensitive: false,
      );
      final match = errorPattern.firstMatch(html);
      if (match != null && match.groupCount >= 1) {
        final error = match.group(1)?.trim() ?? 'Invalid email or password';
        DebugLogger.logAuth('Extracted HTML error: $error');
        return error;
      }
      DebugLogger.logWarn(
          'AUTH', 'Could not extract error message, using default');
      return 'Invalid email or password';
    }
  }

  // Update profile color via JSON API
  Future<bool> updateProfileColor(String color) async {
    try {
      DebugLogger.logAuth('Updating profile color to: $color');

      final response = await _api.put(
        AppConfig.profileEndpoint,
        body: {'profile_color': color},
        includeAuth: true,
      );

      DebugLogger.logAuth(
          'Profile color update response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        final currentUser = _currentUser;
        if (currentUser != null) {
          _currentUser = currentUser.copyWith(profileColor: color);
        }
        _updateSentryUserContext();
        DebugLogger.logAuth('Profile color updated successfully');
        return true;
      } else {
        DebugLogger.logError(
            'Profile color update failed with status ${response.statusCode}');
        return false;
      }
    } catch (e, stackTrace) {
      DebugLogger.logError('EXCEPTION updating profile color: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return false;
    }
  }

  // Validate session before critical operations
  Future<bool> _validateSessionBeforeCriticalOperation() async {
    final isValid = await isLoggedIn(forceRevalidate: true);
    if (!isValid) {
      DebugLogger.logWarn('AUTH', 'Session validation failed before critical operation');
      throw AuthenticationException('Session expired. Please log in again.');
    }
    return true;
  }

  // Change password via JSON API
  Future<AuthResult> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    try {
      DebugLogger.logAuth('Changing password via JSON API...');

      await _validateSessionBeforeCriticalOperation();

      final response = await _api.post(
        AppConfig.changePasswordEndpoint,
        body: {
          'current_password': currentPassword,
          'new_password': newPassword,
        },
        includeAuth: true,
        contentType: ApiService.contentTypeJson,
      );

      DebugLogger.logAuth(
          'Password change response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        DebugLogger.logAuth('Password changed successfully - invalidating session for security');
        await _session.clearSession();
        _currentUser = null;
        return AuthResult.success(requiresReauth: true);
      } else {
        DebugLogger.logError(
            'Password change failed with status ${response.statusCode}');
        final errorMessage = _extractErrorMessage(response);
        return AuthResult.failure(errorMessage);
      }
    } on AuthenticationException {
      // Re-throw authentication errors
      rethrow;
    } catch (e, stackTrace) {
      DebugLogger.logError('EXCEPTION changing password: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return AuthResult.failure(
          'Could not change your password. Please check your connection and try again.');
    }
  }
}

class AuthResult {
  final bool success;
  final String? error;
  final bool requiresReauth;

  AuthResult.success({this.requiresReauth = false})
      : success = true,
        error = null;
  AuthResult.failure(this.error, {this.requiresReauth = false}) : success = false;
}
