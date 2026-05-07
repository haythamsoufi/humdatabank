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

      // Wipe auth-scoped state from secure storage and SharedPreferences,
      // but preserve user UI/UX preferences (theme, language, Arabic font,
      // chatbot AI policy acknowledgement) and the persistent device-install
      // ID.  Previously this called `_storage.clearSecure()` + `_storage.clear()`
      // which nuked **every** SharedPreferences entry — including the user's
      // selected theme and language — every time we logged out, even when the
      // logout was triggered automatically by a transient 401.  The "lost
      // theme after a day" symptom was caused by that broad wipe combined
      // with the over-eager auth-error path; both are fixed here.
      await _storage.clearSecureExcept(<String>[
        AppConfig.persistentDeviceInstallIdKey,
      ]);
      await _storage.clearPrefsExcept(<String>[
        AppConfig.themeModeKey,
        AppConfig.selectedLanguageKey,
        AppConfig.arabicTextFontKey,
        AppConfig.chatbotAiPolicyAcknowledgedKey,
      ]);

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
      // Stop if we no longer have any auth credentials at all.  Previously
      // this gated solely on `_session.hasSession()` (the Flask cookie),
      // which meant JWT-only logins (the typical mobile path when the
      // server doesn't set a session cookie alongside the token response)
      // killed the periodic refresh on the very first tick — leaving the
      // app to discover token expiry only when the user next interacted.
      final hasJwt = await _jwtService.hasTokens();
      final hasSession = await _session.hasSession();
      if (!hasJwt && !hasSession) {
        DebugLogger.logAuth('No JWT or session cookie — stopping periodic refresh');
        _stopPeriodicRefresh();
        return;
      }

      // Skip if access token is still comfortably valid: refreshing while
      // the token is fresh just consumes a refresh-rotation slot for no gain.
      // The 60 s expiry buffer in JwtTokenService still applies, so the
      // first periodic tick after the token enters the buffer will refresh.
      final accessExpired = await _jwtService.isAccessTokenExpired();
      if (!accessExpired) {
        DebugLogger.logAuth('Periodic refresh tick — JWT still fresh, skipping');
        return;
      }

      DebugLogger.logAuth('Periodic JWT refresh triggered (access token aging out)');
      refreshSession().then((success) {
        if (success) {
          DebugLogger.logAuth('Periodic JWT refresh completed successfully');
        } else {
          DebugLogger.logWarn('AUTH', 'Periodic JWT refresh definitively rejected');
        }
      }).catchError((e) {
        // Transient failure — keep tokens, will retry next tick.
        DebugLogger.logWarn('AUTH', 'Periodic JWT refresh transient error (ignored): $e');
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

  /// Refresh JWT tokens via the mobile refresh endpoint.
  ///
  /// Concurrent calls are coalesced (in-process single-flight): the first
  /// call performs the network round-trip; subsequent callers wait for the
  /// same result and avoid a token-rotation reuse storm.
  ///
  /// Rate limiting: when not [forceRefresh], a recently-attempted refresh
  /// short-circuits and returns the *current* JWT validity rather than
  /// blindly returning `true` (which previously masked an expired token
  /// and caused the next API call to 401).
  Future<bool> refreshSession({bool forceRefresh = false}) async {
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
        // Don't blindly return `true` — that previously caused the next API
        // call to 401 (and trigger another refresh) when the access token
        // had aged out *during* the rate-limit window.  Report the actual
        // JWT validity instead so the caller can plan accordingly.
        final accessExpired = await _jwtService.isAccessTokenExpired();
        DebugLogger.logAuth(
            'Refresh rate limited (last attempt ${now.difference(_lastRefreshAttempt!).inMinutes}m ago, '
            'min interval ${minInterval.inMinutes}m) — '
            'reporting current JWT validity: accessExpired=$accessExpired');
        return !accessExpired;
      }
    }

    // Set refresh lock
    _isRefreshing = true;
    _refreshCompleter = Completer<bool>();
    _lastRefreshAttempt = now;

    // Emit refreshing state
    _emitSessionState(SessionState.refreshing);

    try {
      final result = await _doRefreshSession();
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
  //
  // Contract:
  //   - Returns `true` on success (new tokens saved).
  //   - Returns `false` only when the server *definitively* rejected the
  //     refresh token (HTTP 401/403): the refresh token is no longer
  //     usable, so JWT + session state is cleared and the user must
  //     re-authenticate.
  //   - Throws on every other failure (timeout, network, 5xx, parse error).
  //     Tokens are **not** cleared on a throw; the caller must treat it as
  //     a transient failure and try again later.  Callers downstream of
  //     [ApiService] then surface a NetworkError instead of an AuthError,
  //     so [AuthErrorHandler] does not trigger a destructive logout.
  //
  // The request is sent exactly once.  Refresh tokens are one-time-use on
  // the server (see Backoffice/app/utils/mobile_jwt.py + auth.py "Refresh
  // token reuse detected"): the first time the server processes our request
  // it consumes the JTI and blacklists the JWT session.  If we then re-send
  // the same refresh token (e.g. after a TLS reset on the response, a 504
  // from a flaky proxy, or a TimeoutException), the second attempt will
  // come back as 401 *and* the server-side session blacklist will have
  // killed any future refresh — forcing the user to log in again with a
  // perfectly valid refresh token still in their pocket.  This was the
  // primary cause of the "I left the app for a day and now I have to log
  // in again" symptom.
  Future<bool> _doRefreshSession() async {
    DebugLogger.logAuth('Refreshing JWT tokens (single-shot, non-retryable)...');

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

    http.Response response;
    try {
      response = await _api.post(
        AppConfig.mobileRefreshEndpoint,
        body: {'refresh_token': refreshToken},
        includeAuth: false,
        contentType: ApiService.contentTypeJson,
        // Critical: refresh tokens rotate one-time-use server-side.  Re-sending
        // the same token after a transient failure causes a "reuse detected"
        // 401 and a server-side session blacklist.
        retryable: false,
      );
    } on AuthenticationException {
      // Refresh endpoint is unauthenticated, so this should never come from
      // the refresh response itself.  If it does (e.g. an interceptor
      // surfaces an auth error), treat it as transient — do NOT clear
      // tokens here.  The next refresh attempt may succeed.
      DebugLogger.logWarn(
          'AUTH', 'Unexpected AuthenticationException from refresh transport — treating as transient');
      _recordRefreshFailure('refresh_failure_unexpected_auth_exception');
      rethrow;
    } catch (e) {
      // TimeoutException, http.ClientException, SocketException, etc. — any
      // transport-level failure.  The server may or may not have processed
      // our request: from our point of view it could go either way, so we
      // must not assume the refresh token has been consumed and we must not
      // clear tokens.  The user stays logged in; the next foreground or
      // API call can attempt another refresh.
      DebugLogger.logWarn('AUTH', 'Transient JWT refresh failure: $e — keeping tokens');
      _recordRefreshFailure('refresh_failure_transient');
      rethrow;
    }

    if (response.statusCode == 200) {
      try {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        await _saveJwtTokensFromResponse(data);
      } catch (e) {
        // 200 with an unparseable body is a server bug; treat as transient
        // (don't clear tokens). The current refresh token is technically now
        // consumed server-side, so a follow-up refresh will fail — but at
        // worst we lose this one session, not the user's UI prefs.
        DebugLogger.logError('Failed to parse refresh response body: $e');
        _recordRefreshFailure('refresh_failure_parse_error');
        rethrow;
      }
      DebugLogger.logAuth('JWT tokens refreshed successfully');
      _refreshSuccessCount++;
      _lastRefreshTime = DateTime.now();
      _recordRefreshAttempt();
      _logSessionMetrics('refresh_success');
      return true;
    }

    if (response.statusCode == 401 || response.statusCode == 403) {
      // Server explicitly rejected the refresh token (expired, revoked,
      // already consumed, or session blacklisted).  This is the only case
      // where we KNOW the refresh token is unusable — clear and force
      // re-authentication.
      DebugLogger.logWarn('AUTH',
          'Refresh token definitively rejected (status: ${response.statusCode}) — clearing auth state');
      _recordRefreshFailure('refresh_failure_rejected');
      await _jwtService.clearTokens();
      await _session.clearSession();
      _currentUser = null;
      return false;
    }

    // Anything else (5xx, redirect, etc.) is treated as transient: do not
    // clear tokens, do not collapse to `false` (which callers interpret as
    // "definitive failure, force logout").  Throw and let upstream layers
    // deal with it as a network error.
    DebugLogger.logError(
        'JWT refresh failed with HTTP ${response.statusCode} (treated as transient — tokens preserved)');
    _recordRefreshFailure('refresh_failure_http_${response.statusCode}');
    throw Exception('JWT refresh failed with HTTP ${response.statusCode}');
  }

  void _recordRefreshAttempt() {
    _refreshAttempts.add(DateTime.now());
    if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
      _refreshAttempts.removeAt(0);
    }
  }

  void _recordRefreshFailure(String label) {
    _refreshFailureCount++;
    _recordRefreshAttempt();
    _logSessionMetrics(label);
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
          bool refreshed;
          try {
            refreshed = await refreshSession(forceRefresh: true);
          } catch (e) {
            // Transient failure (timeout, network drop, 5xx).  We do NOT
            // know if the user is still authenticated, so do not log them
            // out.  Treat as offline — let the cached user stay logged in,
            // and allow the next foreground / API call to retry the refresh.
            DebugLogger.logWarn('AUTH',
                'Silent JWT refresh threw transient error ($e) — preserving cached auth; '
                'will retry on next API call or app resume');
            return _currentUser != null;
          }
          if (!refreshed) {
            // Definitive rejection (server returned 401/403 on the refresh
            // token itself, or no refresh token was available).
            DebugLogger.logWarn('AUTH',
                'Silent JWT refresh definitively rejected — user must re-login');
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
  //
  // Uses the JWT-aware mobile session endpoint so that admin force-logouts
  // (which blacklist the JWT session_id) are detected immediately.
  //
  // Auth state is cleared here only when the server **explicitly** told us
  // the session is invalid:
  //   - HTTP 401/403 directly on the session check, or
  //   - AuthenticationException bubbling up from ApiService (which only
  //     throws after a refresh attempt was definitively rejected by the
  //     server, not on transport errors).
  // Any other failure (timeout, 5xx, socket reset, refresh request
  // throwing transiently) is treated as a network blip — we keep the
  // cached user logged in and let the next foreground / API call retry.
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
        DebugLogger.logWarn('AUTH',
            'Background validation: server returned ${response.statusCode} — clearing auth state');
        _jwtService.clearTokens();
        _session.clearSession();
        _currentUser = null;
        _emitSessionState(SessionState.expired);
      }
      // 5xx / other non-401 responses: do nothing.  The server probably
      // hiccupped; we'll re-check on the next periodic tick or interaction.
    }).catchError((e) {
      if (e is AuthenticationException) {
        // ApiService already cleared tokens in its own 401 handler before
        // throwing this; we just sync our in-memory state.
        DebugLogger.logWarn('AUTH',
            'Background validation: AuthenticationException — auth state already cleared by ApiService');
        _currentUser = null;
        _emitSessionState(SessionState.expired);
      } else {
        // TimeoutException, http.ClientException, SocketException,
        // refresh-threw, etc. — keep the cached user logged in.
        DebugLogger.logWarn('AUTH',
            'Background validation transient error (preserving cached auth): $e');
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
