import 'dart:convert';
import 'dart:async';
import 'package:flutter/foundation.dart';
import '../config/app_config.dart';
import '../models/shared/user.dart';
import 'api_service.dart';
import 'storage_service.dart';
import 'session_service.dart';
import 'user_profile_service.dart';
import 'connectivity_service.dart';
import 'error_handler.dart';
import '../utils/debug_logger.dart';
import 'offline_cache_service.dart';
import 'offline_queue_service.dart';

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

  final ApiService _api = ApiService();
  final StorageService _storage = StorageService();
  final SessionService _session = SessionService();
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

  // Session metrics tracking
  int _refreshSuccessCount = 0;
  int _refreshFailureCount = 0;
  DateTime? _sessionStartTime;
  DateTime? _lastRefreshTime;
  final List<DateTime> _refreshAttempts = [];
  static const int _maxRefreshAttemptsHistory = 100; // Keep last 100 refresh attempts

  // Login with email and password
  Future<AuthResult> loginWithEmailPassword({
    required String email,
    required String password,
    bool rememberMe = false,
  }) async {
    DebugLogger.logAuth(
        'Starting login for email: ${email.trim().toLowerCase()}');

    try {
      // First, get the CSRF token from the login page
      // This also establishes a session cookie needed for CSRF validation
      DebugLogger.logAuth('Step 1: Fetching CSRF token from login page...');
      final csrfResult = await _getCsrfToken();
      if (csrfResult == null || csrfResult['token'] == null) {
        DebugLogger.logError('Failed to get CSRF token');
        return AuthResult.failure(
            'Failed to get CSRF token. Please check your internet connection and try again.');
      }

      final csrfToken = csrfResult['token'] as String;
      final sessionCookie = csrfResult['cookie'];

      DebugLogger.logAuth(
          'CSRF token obtained: ${csrfToken.substring(0, 20)}...');
      if (sessionCookie != null) {
        DebugLogger.logAuth(
            'Session cookie obtained: ${sessionCookie.substring(0, 30)}...');
      } else {
        DebugLogger.logWarn('AUTH', 'No session cookie from CSRF request');
      }

      // Create form data for login with CSRF token
      // Include the session cookie from CSRF token request if available
      // Build headers with Referer for CSRF protection
      // Flask-WTF requires Referer header to match the origin
      final loginUrl = '${AppConfig.baseApiUrl}${AppConfig.loginEndpoint}';
      final Map<String, String> requestHeaders = {
        'Referer': loginUrl, // Required for Flask-WTF CSRF protection
        'Origin': AppConfig.baseApiUrl, // Also set Origin header
      };

      if (sessionCookie != null) {
        requestHeaders['Cookie'] = sessionCookie;
      }

      DebugLogger.logAuth('Step 2: Sending login POST request...');

      final response = await _api.post(
        AppConfig.loginEndpoint,
        body: {
          'csrf_token': csrfToken,
          'email': email.trim().toLowerCase(),
          'password': password,
        },
        includeAuth: false,
        contentType: ApiService.contentTypeFormUrlEncoded,
        additionalHeaders: requestHeaders,
      );

      DebugLogger.logAuth('Login response status: ${response.statusCode}');

      // Extract error message if login failed
      if (response.statusCode != 200 && response.statusCode != 302) {
        final responseBody = response.body;
        final errorPattern = RegExp(r'<p[^>]*>([^<]+)', caseSensitive: false);
        final errorMatch = errorPattern.firstMatch(responseBody);
        if (errorMatch != null && errorMatch.groupCount >= 1) {
          final errorMsg = errorMatch.group(1)?.trim();
          if (errorMsg != null && errorMsg.isNotEmpty) {
            DebugLogger.logError('Error from server: $errorMsg');
          }
        }
      }

      // Handle different response codes
      if (response.statusCode == 500) {
        DebugLogger.logError('Login failed with 500 Internal Server Error');
        // 500 usually means backend issue, but could also mean invalid credentials
        // Check if response body gives more info
        final errorMessage = _extractErrorMessage(response);
        return AuthResult.failure(
            'Server error: $errorMessage. Please try again or contact support.');
      }

      if (response.statusCode == 200 || response.statusCode == 302) {
        DebugLogger.logAuth('Login successful! Extracting session cookie...');
        // Extract session cookie
        final cookie = _api.extractSessionCookie(response);
        if (cookie != null) {
          DebugLogger.logAuth('Session cookie extracted, saving...');
          await _session.saveSessionCookie(cookie);
          await _session.injectSessionIntoWebView();
          DebugLogger.logAuth('Session cookie saved and injected into WebView');
        } else {
          DebugLogger.logWarn('AUTH', 'No session cookie in response');
        }

        // Store email if remember me is checked
        if (rememberMe) {
          DebugLogger.logAuth('Saving email for remember me');
          await _storage.setString(AppConfig.userEmailKey, email);
          await _storage.setBool(AppConfig.rememberMeKey, true);
        } else {
          await _storage.remove(AppConfig.userEmailKey);
          await _storage.setBool(AppConfig.rememberMeKey, false);
        }

        // Fetch user profile
        DebugLogger.logAuth('Step 3: Loading user profile...');
        await _loadUserProfile();

        // Set Sentry user context after successful login
        _updateSentryUserContext();

        // Add breadcrumb for login
        ErrorHandler.addBreadcrumb(
          message: 'User logged in',
          category: 'auth',
          data: {
            'email': email.trim().toLowerCase(),
            'remember_me': rememberMe.toString(),
          },
        );

        // Start periodic refresh timer after successful login
        _startPeriodicRefresh();

        // Start session state monitoring
        _startSessionStateMonitoring();

        DebugLogger.logAuth('Login complete!');

        return AuthResult.success();
      } else {
        DebugLogger.logError('Login failed with status ${response.statusCode}');
        final errorMessage = _extractErrorMessage(response);
        DebugLogger.logError('Error message: $errorMessage');
        return AuthResult.failure(errorMessage);
      }
    } catch (e, stackTrace) {
      DebugLogger.logError('EXCEPTION during login: $e');
      DebugLogger.logError('Stack trace: $stackTrace');

      // Provide user-friendly error messages based on error type
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

      return AuthResult.failure('Network error: ${e.toString()}');
    }
  }

  /// Quick login for testing purposes
  /// Security: Available only when DEVELOPMENT flag is enabled
  Future<AuthResult> quickLogin(String email, String password) async {
    // Security check: Allow quick login only for explicit development builds
    if (!AppConfig.isDevelopment) {
      DebugLogger.logWarn('AUTH', 'Quick login blocked outside development environment');
      return AuthResult.failure(
        'Quick login is only available in development builds',
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
    try {
      // Add breadcrumb before logout
      ErrorHandler.addBreadcrumb(
        message: 'User logging out',
        category: 'auth',
        data: {
          'email': _currentUser?.email ?? 'unknown',
        },
      );

      await _api.post(AppConfig.logoutEndpoint);
    } catch (e) {
      DebugLogger.logError('Error during logout API call: $e');
    } finally {
      await _session.clearSession();
      await _storage.clear();
      await OfflineCacheService().clearAll();
      await OfflineQueueService().clearAll();

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

      // Reset metrics
      _sessionStartTime = null;
      _lastRefreshTime = null;
      _refreshSuccessCount = 0;
      _refreshFailureCount = 0;
      _refreshAttempts.clear();
    }
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

  // Internal method that performs the actual refresh
  Future<bool> _doRefreshSession({int retryCount = 0}) async {
    const maxRetries = 2;
    try {
      DebugLogger.logAuth('Refreshing session... (attempt ${retryCount + 1}/${maxRetries + 1})');

      // Use a lightweight endpoint to refresh session
      // The backend will update the session cookie expiration
      final response = await _api.get(
        AppConfig.userProfileApiEndpoint,
        timeout: const Duration(seconds: 10), // Increased timeout for reliability
      );

      if (response.statusCode == 200) {
        DebugLogger.logAuth('Session refreshed successfully');

        // Track successful refresh
        _refreshSuccessCount++;
        _lastRefreshTime = DateTime.now();
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }

        // Log metrics
        _logSessionMetrics('refresh_success');

        // Session cookie rotation is handled by ApiService
        // Last validation time is updated by ApiService on successful response
        return true;
      } else if (response.statusCode == 401 || response.statusCode == 403) {
        // Session expired on backend - don't retry
        DebugLogger.logWarn('AUTH', 'Session expired during refresh (status: ${response.statusCode})');

        // Track failed refresh
        _refreshFailureCount++;
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }
        _logSessionMetrics('refresh_failure_expired');

        await _session.clearSession();
        _currentUser = null;
        return false;
      } else {
        // Retry on other errors
        if (retryCount < maxRetries) {
          DebugLogger.logWarn('AUTH',
              'Session refresh failed with status ${response.statusCode}, retrying...');
          await Future.delayed(Duration(seconds: 1 * (retryCount + 1))); // Exponential backoff
          return await _doRefreshSession(retryCount: retryCount + 1);
        }
        DebugLogger.logError(
            'Session refresh failed with status ${response.statusCode} after ${maxRetries + 1} attempts');

        // Track failed refresh
        _refreshFailureCount++;
        _refreshAttempts.add(DateTime.now());
        if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
          _refreshAttempts.removeAt(0);
        }
        _logSessionMetrics('refresh_failure_error');

        return false;
      }
    } on TimeoutException {
      // Retry on timeout
      if (retryCount < maxRetries) {
        DebugLogger.logWarn('AUTH', 'Session refresh timeout, retrying...');
        await Future.delayed(Duration(seconds: 1 * (retryCount + 1)));
        return await _doRefreshSession(retryCount: retryCount + 1);
      }
      DebugLogger.logError('Session refresh timeout after ${maxRetries + 1} attempts');

      // Track failed refresh
      _refreshFailureCount++;
      _refreshAttempts.add(DateTime.now());
      if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
        _refreshAttempts.removeAt(0);
      }
      _logSessionMetrics('refresh_failure_timeout');

      return false;
    } on AuthenticationException {
      // Don't retry auth errors
      DebugLogger.logWarn('AUTH', 'Authentication error during refresh - session expired');
      await _session.clearSession();
      _currentUser = null;
      return false;
    } catch (e) {
      // Retry on other errors
      if (retryCount < maxRetries) {
        DebugLogger.logWarn('AUTH', 'Error refreshing session: $e, retrying...');
        await Future.delayed(Duration(seconds: 1 * (retryCount + 1)));
        return await _doRefreshSession(retryCount: retryCount + 1);
      }
      DebugLogger.logError('Error refreshing session after ${maxRetries + 1} attempts: $e');

      // Track failed refresh
      _refreshFailureCount++;
      _refreshAttempts.add(DateTime.now());
      if (_refreshAttempts.length > _maxRefreshAttemptsHistory) {
        _refreshAttempts.removeAt(0);
      }
      _logSessionMetrics('refresh_failure_exception');

      return false;
    }
  }

  // Check if user is logged in
  // forceRevalidate: if true, always validate session even if user is cached
  Future<bool> isLoggedIn({bool forceRevalidate = false}) async {
    // First check if we have a session cookie
    final hasSession = await _session.hasSession();
    if (!hasSession) {
      DebugLogger.logAuth('No session cookie found');
      _currentUser = null; // Clear cached user if no session
      return false;
    }

    // Check if session is expired (client-side check)
    final isExpired = await _session.isSessionExpired();
    if (isExpired) {
      DebugLogger.logWarn('AUTH', 'Session expired (client-side check)');
      await _session.clearSession();
      _currentUser = null;
      return false;
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
      DebugLogger.logAuth('Device is offline - checking offline session validity...');
      final isValidForOffline = await _session.isSessionValidForOffline();
      if (isValidForOffline) {
        DebugLogger.logAuth('Session is valid for offline operations');
        // Return true if we have cached user, allowing offline operations
        return _currentUser != null;
      } else {
        DebugLogger.logWarn('AUTH', 'Session not valid for offline operations');
        return false;
      }
    }

    // Validate session with backend by checking account-settings
    // This ensures the session is still valid
    // Use a shorter timeout for session validation to prevent blocking
    try {
      DebugLogger.logAuth('Validating session with backend...');
      final response = await _api.get(
        AppConfig.accountSettingsEndpoint,
        timeout: const Duration(seconds: 5),
      );

      if (response.statusCode == 200) {
        // Session is valid, always reload user profile to get latest role
        await _loadUserProfile();
        DebugLogger.logAuth('Session is valid');
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
      DebugLogger.logError('Error validating session: $e');
      // On error, check if we're offline and session is valid for offline
      if (_connectivity.isOffline) {
        final isValidForOffline = await _session.isSessionValidForOffline();
        if (isValidForOffline && _currentUser != null) {
          DebugLogger.logAuth('Using cached session for offline operations (error occurred)');
          return true;
        }
      }
      // On error, check if we have a cached user
      if (_currentUser != null) {
        // Return true with cached user, but log the error
        DebugLogger.logWarn(
            'AUTH', 'Using cached user due to validation error');
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

  // Validate session in background without blocking
  void _validateSessionInBackground() {
    // Don't await - let it run in background
    _api
        .get(
      AppConfig.accountSettingsEndpoint,
      timeout: const Duration(seconds: 5),
    )
        .then((response) {
      if (response.statusCode == 200) {
        // Session is still valid, refresh user profile to get latest role
        _loadUserProfile();
      } else if (response.statusCode == 401 || response.statusCode == 403) {
        // Session expired - clear it
        DebugLogger.logWarn('AUTH', 'Background validation: Session expired');
        _session.clearSession();
        _currentUser = null;
      }
    }).catchError((e) {
      // Ignore background validation errors
      DebugLogger.logWarn('AUTH', 'Background validation error (ignored): $e');
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

  // Get CSRF token from login page
  // Returns a map with 'token' and 'cookie' keys
  Future<Map<String, String?>?> _getCsrfToken() async {
    try {
      DebugLogger.logAuth('Fetching login page to get CSRF token...');
      final response = await _api.get(
        AppConfig.loginEndpoint,
        includeAuth: false,
      );

      DebugLogger.logAuth('Login page response status: ${response.statusCode}');
      DebugLogger.logAuth('Response headers: ${response.headers}');

      if (response.statusCode == 200) {
        // Extract CSRF token from HTML
        // Look for: <input type="hidden" name="csrf_token" value="...">
        // or: <input id="login_csrf_token" name="csrf_token" type="hidden" value="...">
        final html = response.body;
        DebugLogger.logAuth('HTML response length: ${html.length} chars');

        String? csrfToken;

        // Try to find CSRF token in hidden input
        DebugLogger.logAuth('Searching for CSRF token in HTML...');

        // Use character class [\x22\x27] to match either double or single quote
        final csrfPattern = RegExp(
          r'<input[^>]*name=[\x22\x27]csrf_token[\x22\x27][^>]*value=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
          caseSensitive: false,
        );
        final match = csrfPattern.firstMatch(html);
        if (match != null && match.groupCount >= 1) {
          csrfToken = match.group(1);
          // Decode HTML entities (e.g., &quot; -> ", &#x27; -> ', etc.)
          if (csrfToken != null) {
            // Only decode HTML entities - Flask-WTF tokens should be used as-is from HTML
            csrfToken = _decodeHtmlEntities(csrfToken);
            // Do NOT URL decode or base64 decode - the token should be used exactly as extracted
            DebugLogger.logAuth('Found CSRF token using name pattern');
          }
        } else {
          // Alternative pattern: id="login_csrf_token"
          DebugLogger.logAuth(
              'Trying alternative pattern with id="login_csrf_token"...');
          final csrfPattern2 = RegExp(
            r'<input[^>]*id=[\x22\x27]login_csrf_token[\x22\x27][^>]*value=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
            caseSensitive: false,
          );
          final match2 = csrfPattern2.firstMatch(html);
          if (match2 != null && match2.groupCount >= 1) {
            csrfToken = match2.group(1);
            // Decode HTML entities
            if (csrfToken != null) {
              // Only decode HTML entities - Flask-WTF tokens should be used as-is from HTML
              csrfToken = _decodeHtmlEntities(csrfToken);
              // Do NOT URL decode or base64 decode - the token should be used exactly as extracted
              DebugLogger.logAuth('Found CSRF token using id pattern');
            }
          } else {
            DebugLogger.logWarn('AUTH', 'Could not find CSRF token in HTML');
            // Debug: show a snippet of HTML that might contain the token
            final tokenSnippet = html.contains('csrf')
                ? html.substring(
                    html.indexOf('csrf') - 50, html.indexOf('csrf') + 200)
                : 'No "csrf" found in HTML';
            DebugLogger.logAuth('HTML snippet around "csrf": $tokenSnippet');
          }
        }

        if (csrfToken != null) {
          // Extract session cookie from response headers
          // Flask sets a session cookie that's needed for CSRF validation
          final setCookie = response.headers['set-cookie'];
          String? sessionCookie;

          DebugLogger.logAuth(
              'Extracting session cookie from Set-Cookie header...');
          if (setCookie != null) {
            DebugLogger.logAuth('Set-Cookie header: $setCookie');
            // Handle multiple Set-Cookie headers (they might be comma-separated or in a list)
            String cookieString = setCookie;
            // If it's a list (from http package), join them
            if (setCookie.contains(',')) {
              // Split by comma and find the session cookie
              final cookies = setCookie.split(',');
              for (final cookie in cookies) {
                final trimmed = cookie.trim();
                if (trimmed.startsWith('session=')) {
                  // Extract just the session=value part (before any semicolon)
                  final sessionMatch =
                      RegExp(r'(session=[^;]+)').firstMatch(trimmed);
                  if (sessionMatch != null) {
                    sessionCookie = sessionMatch.group(1);
                    DebugLogger.logAuth(
                        'Extracted session cookie from comma-separated list');
                    break;
                  }
                }
              }
            }

            // If not found yet, try direct pattern matching
            if (sessionCookie == null) {
              final sessionMatch =
                  RegExp(r'(session=[^;,\s]+)').firstMatch(cookieString);
              if (sessionMatch != null) {
                sessionCookie = sessionMatch.group(1);
                DebugLogger.logAuth('Extracted session cookie using pattern');
              } else {
                // Fallback: use the first cookie that starts with 'session='
                final allCookies = cookieString.split(',').map((c) => c.trim());
                for (final cookie in allCookies) {
                  if (cookie.startsWith('session=')) {
                    final sessionMatch =
                        RegExp(r'(session=[^;]+)').firstMatch(cookie);
                    if (sessionMatch != null) {
                      sessionCookie = sessionMatch.group(1);
                      DebugLogger.logAuth(
                          'Extracted session cookie using fallback');
                      break;
                    }
                  }
                }
              }
            }

            if (sessionCookie == null) {
              DebugLogger.logWarn('AUTH',
                  'Could not extract session cookie from Set-Cookie header');
            }
          } else {
            DebugLogger.logWarn('AUTH', 'No Set-Cookie header in response');
          }

          return {
            'token': csrfToken,
            'cookie': sessionCookie,
          };
        }
      } else {
        DebugLogger.logError(
            'Login page returned status ${response.statusCode}');
      }
      return null;
    } catch (e, stackTrace) {
      final errorMessage = e.toString().toLowerCase();
      if (errorMessage.contains('no internet connection') ||
          errorMessage.contains('no cached data available')) {
        DebugLogger.logError('EXCEPTION getting CSRF token: Device is offline');
      } else {
        DebugLogger.logError('EXCEPTION getting CSRF token: $e');
      }
      DebugLogger.logError('Stack trace: $stackTrace');
      return null;
    }
  }

  String _extractErrorMessage(response) {
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

  // Decode HTML entities in CSRF token
  String _decodeHtmlEntities(String text) {
    return text
        .replaceAll('&quot;', '"')
        .replaceAll('&#39;', "'")
        .replaceAll('&apos;', "'")
        .replaceAll('&lt;', '<')
        .replaceAll('&gt;', '>')
        .replaceAll('&amp;', '&');
  }

  // Update profile color
  Future<bool> updateProfileColor(String color) async {
    try {
      DebugLogger.logAuth('Updating profile color to: $color');

      // Get CSRF token from account-settings page
      final csrfResult = await _getCsrfTokenFromAccountSettings();
      if (csrfResult == null || csrfResult['token'] == null) {
        DebugLogger.logError('Failed to get CSRF token');
        return false;
      }

      final csrfToken = csrfResult['token'] as String;
      final sessionCookie = csrfResult['cookie'];

      // Get current user data to preserve other fields
      final currentUser = _currentUser;
      if (currentUser == null) {
        DebugLogger.logError('No current user');
        return false;
      }

      // Build form data
      final formData = {
        'csrf_token': csrfToken,
        'name': currentUser.name ?? '',
        'title': currentUser.title ?? '',
        'chatbot_enabled': currentUser.chatbotEnabled ? 'y' : '',
        'profile_color': color,
      };

      // Build headers with Referer for CSRF protection
      final accountSettingsUrl =
          '${AppConfig.baseApiUrl}${AppConfig.accountSettingsEndpoint}';
      final Map<String, String> requestHeaders = {
        'Referer': accountSettingsUrl,
        'Origin': AppConfig.baseApiUrl,
      };

      if (sessionCookie != null) {
        requestHeaders['Cookie'] = sessionCookie;
      }

      DebugLogger.logAuth('Sending profile color update request...');
      final response = await _api.post(
        AppConfig.accountSettingsEndpoint,
        body: formData,
        includeAuth: true,
        contentType: ApiService.contentTypeFormUrlEncoded,
        additionalHeaders: requestHeaders,
      );

      DebugLogger.logAuth(
          'Profile color update response status: ${response.statusCode}');

      if (response.statusCode == 200 || response.statusCode == 302) {
        // Update local user object
        _currentUser = currentUser.copyWith(profileColor: color);

        // Update Sentry user context when profile color changes
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

  // Get CSRF token from account-settings page
  Future<Map<String, String?>?> _getCsrfTokenFromAccountSettings() async {
    try {
      DebugLogger.logAuth(
          'Fetching account-settings page to get CSRF token...');
      final response = await _api.get(AppConfig.accountSettingsEndpoint);

      DebugLogger.logAuth(
          'Account-settings page response status: ${response.statusCode}');

      if (response.statusCode == 200) {
        final html = response.body;
        DebugLogger.logAuth('HTML response length: ${html.length} chars');

        String? csrfToken;

        // Try to find CSRF token in hidden input
        DebugLogger.logAuth('Searching for CSRF token in HTML...');

        final csrfPattern = RegExp(
          r'<input[^>]*name=[\x22\x27]csrf_token[\x22\x27][^>]*value=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
          caseSensitive: false,
        );
        final match = csrfPattern.firstMatch(html);
        if (match != null && match.groupCount >= 1) {
          csrfToken = match.group(1);
          if (csrfToken != null) {
            csrfToken = _decodeHtmlEntities(csrfToken);
            DebugLogger.logAuth('Found CSRF token using name pattern');
          }
        } else {
          DebugLogger.logWarn('AUTH', 'Could not find CSRF token in HTML');
        }

        if (csrfToken != null) {
          // Extract session cookie from response headers
          final setCookie = response.headers['set-cookie'];
          String? sessionCookie;

          if (setCookie != null) {
            final sessionMatch =
                RegExp(r'(session=[^;]+)').firstMatch(setCookie);
            if (sessionMatch != null) {
              sessionCookie = sessionMatch.group(1);
            }
          }

          return {
            'token': csrfToken,
            'cookie': sessionCookie,
          };
        }
      } else {
        DebugLogger.logError(
            'Account-settings page returned status ${response.statusCode}');
      }
      return null;
    } catch (e, stackTrace) {
      DebugLogger.logError(
          'EXCEPTION getting CSRF token from account-settings: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return null;
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

  // Change password
  Future<AuthResult> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    try {
      DebugLogger.logAuth('Changing password...');

      // Validate session before critical operation
      await _validateSessionBeforeCriticalOperation();

      // Get CSRF token from account-settings page
      final csrfResult = await _getCsrfTokenFromAccountSettings();
      if (csrfResult == null || csrfResult['token'] == null) {
        DebugLogger.logError('Failed to get CSRF token');
        return AuthResult.failure(
            'Failed to get security token. Please try again.');
      }

      final csrfToken = csrfResult['token'] as String;
      final sessionCookie = csrfResult['cookie'];

      // Build form data
      final formData = {
        'csrf_token': csrfToken,
        'current_password': currentPassword,
        'new_password': newPassword,
        'confirm_password': newPassword,
      };

      // Build headers with Referer for CSRF protection
      final accountSettingsUrl =
          '${AppConfig.baseApiUrl}${AppConfig.accountSettingsEndpoint}';
      final Map<String, String> requestHeaders = {
        'Referer': accountSettingsUrl,
        'Origin': AppConfig.baseApiUrl,
      };

      if (sessionCookie != null) {
        requestHeaders['Cookie'] = sessionCookie;
      }

      DebugLogger.logAuth('Sending password change request...');
      final response = await _api.post(
        AppConfig.changePasswordEndpoint,
        body: formData,
        includeAuth: true,
        contentType: ApiService.contentTypeFormUrlEncoded,
        additionalHeaders: requestHeaders,
      );

      DebugLogger.logAuth(
          'Password change response status: ${response.statusCode}');

      if (response.statusCode == 200 || response.statusCode == 302) {
        DebugLogger.logAuth('Password changed successfully - invalidating session for security');
        // Clear session and force re-login after password change
        // This ensures all sessions are invalidated for security
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
      return AuthResult.failure('Network error: ${e.toString()}');
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
