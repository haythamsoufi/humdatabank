import 'dart:convert';
import 'dart:async';
import 'dart:math' show pow;
import 'package:http/http.dart' as http;
import '../config/api_timeouts.dart';
import '../config/app_config.dart';
import 'app_build_metadata.dart';
import 'mobile_platform_headers.dart';
import 'storage_service.dart';
import 'session_service.dart';
import 'jwt_token_service.dart';
import 'mobile_app_update_handler.dart';
import 'push_notification_service.dart';
import 'connectivity_service.dart';
import 'offline_queue_service.dart';
import 'offline_cache_service.dart';
import 'backend_reachability_service.dart';
import '../utils/debug_logger.dart';
import '../utils/network_availability.dart';
import 'user_scope_service.dart';

// Custom exception for authentication errors
class AuthenticationException implements Exception {
  final String message;
  AuthenticationException(this.message);

  @override
  String toString() => message;
}

/// Request interceptor callback type
typedef RequestInterceptor = Future<Map<String, String>> Function(
    Map<String, String> headers, String endpoint);

/// Response interceptor callback type
typedef ResponseInterceptor = Future<void> Function(
    http.Response response, String endpoint);

/// Retry configuration
class RetryConfig {
  final int maxRetries;
  final Duration initialDelay;
  final double backoffMultiplier;
  final Duration maxDelay;

  const RetryConfig({
    this.maxRetries = 3,
    this.initialDelay = const Duration(seconds: 1),
    this.backoffMultiplier = 2.0,
    this.maxDelay = const Duration(seconds: 10),
  });
}

class ApiService {
  static const String contentTypeJson = 'application/json';
  static const String contentTypeFormUrlEncoded =
      'application/x-www-form-urlencoded';

  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  // Registered by AuthService to break the circular import dependency.
  // Called on 401 responses to attempt a silent JWT token refresh.
  static Future<bool> Function()? _tokenRefreshCallback;

  /// Register the JWT refresh callback.  Call this once from [AuthService]
  /// after the first successful login (or on app start when tokens exist).
  static Future<bool> Function()? get tokenRefreshCallback => _tokenRefreshCallback;

  static set tokenRefreshCallback(Future<bool> Function() callback) {
    _tokenRefreshCallback = callback;
  }

  final StorageService _storage = StorageService();
  final SessionService _session = SessionService();
  final JwtTokenService _jwtService = JwtTokenService();
  final ConnectivityService _connectivity = ConnectivityService();
  final OfflineQueueService _queueService = OfflineQueueService();
  final OfflineCacheService _cacheService = OfflineCacheService();
  final UserScopeService _scopeService = UserScopeService();

  // Legacy secure storage key for CSRF tokens. Mobile uses JWT Bearer auth only;
  // CSRF is not needed when requests are authenticated with JWT (no session-cookie form posts).
  static const String _csrfTokenStorageKey = 'csrf_token_v1';

  Future<String?> _getCachedCsrfToken() async {
    return _storage.getSecure(_csrfTokenStorageKey);
  }

  Future<void> _cacheCsrfToken(String token) async {
    await _storage.setSecure(_csrfTokenStorageKey, token);
  }


  Future<String?> refreshCsrfToken() async {
    return null;
  }

  /// Cache a CSRF token obtained from a JSON API response (e.g. login).
  Future<void> refreshCsrfTokenFromValue(String token) async {
    await _cacheCsrfToken(token);
  }

  bool _isUnsafeMethod(String method) {
    final m = method.toUpperCase().trim();
    return m == 'POST' || m == 'PUT' || m == 'PATCH' || m == 'DELETE';
  }

  // Request interceptors - called before each request
  final List<RequestInterceptor> _requestInterceptors = [];

  // Response interceptors - called after each successful response
  final List<ResponseInterceptor> _responseInterceptors = [];

  /// Add a request interceptor
  void addRequestInterceptor(RequestInterceptor interceptor) {
    _requestInterceptors.add(interceptor);
  }

  /// Add a response interceptor
  void addResponseInterceptor(ResponseInterceptor interceptor) {
    _responseInterceptors.add(interceptor);
  }

  /// Remove a request interceptor
  void removeRequestInterceptor(RequestInterceptor interceptor) {
    _requestInterceptors.remove(interceptor);
  }

  /// Remove a response interceptor
  void removeResponseInterceptor(ResponseInterceptor interceptor) {
    _responseInterceptors.remove(interceptor);
  }

  /// Apply all request interceptors
  Future<Map<String, String>> _applyRequestInterceptors(
      Map<String, String> headers, String endpoint) async {
    var modifiedHeaders = Map<String, String>.from(headers);
    for (final interceptor in _requestInterceptors) {
      modifiedHeaders = await interceptor(modifiedHeaders, endpoint);
    }
    return modifiedHeaders;
  }

  /// Apply all response interceptors
  Future<void> _applyResponseInterceptors(
      http.Response response, String endpoint) async {
    MobileAppUpdateHandler.instance.tryHandleHttpResponse(response);
    for (final interceptor in _responseInterceptors) {
      await interceptor(response, endpoint);
    }
  }

  /// Throws [AuthenticationException] when the auth context has fully expired
  /// (no valid session timestamps AND no usable JWT access token AND no
  /// refresh token available to silently recover).
  Future<void> _guardSessionExpiry() async {
    final isExpired = await _session.isSessionExpired();
    if (!isExpired) return;
    // Session timestamps say expired — but if we still hold a non-expired
    // JWT access token, treat the session as alive (the JWT will be attached
    // by _getHeaders and the server will accept it).
    final jwtExpired = await _jwtService.isAccessTokenExpired();
    if (!jwtExpired) return;
    // Both the session timestamps and the JWT access token are expired.
    // Before giving up, attempt a proactive silent refresh if we have a
    // refresh token. This prevents the user being forced to log in again
    // when the access token simply aged out (e.g. app in background) but a
    // valid refresh token is still available.
    final hasRefresh = await _jwtService.hasRefreshToken();
    if (hasRefresh && _tokenRefreshCallback != null) {
      DebugLogger.logApi(
          'Session/JWT expired — attempting proactive silent token refresh');
      final refreshed = await _tokenRefreshCallback!();
      if (refreshed) {
        DebugLogger.logApi('Proactive refresh succeeded — proceeding with request');
        return;
      }
      // Refresh failed (refresh token itself is expired or server rejected it).
      DebugLogger.logApi('Proactive refresh failed — clearing auth state');
      await _jwtService.clearTokens();
      await _session.clearSession();
    } else {
      DebugLogger.logApi(
          'Session expired and no valid JWT or refresh token — throwing AuthenticationException');
    }
    throw AuthenticationException('Session expired. Please log in again.');
  }

  Future<Map<String, String>> _getHeaders({
    bool includeAuth = true,
    String contentType = contentTypeJson,
    Map<String, String>? additionalHeaders,
    String? httpMethod,
    String? endpoint,
  }) async {
    await MobilePlatformHeaders.ensureInitialized();
    await AppBuildMetadata.ensureInitialized();

    final headers = <String, String>{
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest', // Helps backend identify API requests
      ...MobilePlatformHeaders.map,
    };

    final semver = AppBuildMetadata.appVersionSemver;
    if (semver.isNotEmpty) {
      headers['X-App-Version'] = semver;
    }

    // Only set Content-Type for requests with a body (POST, PUT, PATCH)
    // GET requests shouldn't have Content-Type header
    if (contentType.isNotEmpty) {
      headers['Content-Type'] = contentType;
    }

    // Handle cookies - merge if both exist
    String? cookieValue;
    if (includeAuth) {
      final cookie = await _storage.getSecure(AppConfig.sessionCookieKey);
      if (cookie != null) {
        cookieValue = cookie;
      }
    }

    // If additional headers include a Cookie, merge them
    if (additionalHeaders != null && additionalHeaders.containsKey('Cookie')) {
      final additionalCookie = additionalHeaders['Cookie'];
      if (cookieValue != null && additionalCookie != null) {
        // Merge cookies: existing cookie + additional cookie
        headers['Cookie'] = '$cookieValue; $additionalCookie';
      } else if (additionalCookie != null) {
        headers['Cookie'] = additionalCookie;
      } else if (cookieValue != null) {
        headers['Cookie'] = cookieValue;
      }
    } else if (cookieValue != null) {
      headers['Cookie'] = cookieValue;
    }

    // Add device token header if available (for device activity tracking)
    try {
      final pushService = PushNotificationService();
      final deviceToken = pushService.currentToken;
      if (deviceToken != null) {
        headers['X-Device-Token'] = deviceToken;
      }
    } catch (e) {
      // Silently ignore - device token is optional
    }

    // JWT Bearer token for all authenticated mobile API requests.
    // All mobile endpoints use @mobile_auth_required which accepts this token.
    bool jwtAttached = false;
    if (includeAuth &&
        (additionalHeaders == null ||
            !additionalHeaders.containsKey('Authorization'))) {
      final accessToken = await _jwtService.getAccessToken();
      if (accessToken != null && accessToken.isNotEmpty) {
        headers['Authorization'] = 'Bearer $accessToken';
        jwtAttached = true;
      }
    }

    // CSRF token for session-authenticated unsafe requests (legacy / WebView flows
    // where no JWT is present).
    if (includeAuth &&
        !jwtAttached &&
        endpoint != null &&
        httpMethod != null &&
        _isUnsafeMethod(httpMethod)) {
      final token = await _getCachedCsrfToken();
      if (token != null && token.isNotEmpty) {
        headers['X-CSRFToken'] = token;
      }
    }

    // Add any other additional headers (excluding Cookie which we handled above)
    if (additionalHeaders != null) {
      additionalHeaders.forEach((key, value) {
        if (key.toLowerCase() != 'cookie') {
          headers[key] = value;
        }
      });
    }

    return headers;
  }

  void _notePrimaryBackendTransportSuccess(Uri uri, {required bool usedLiveNetwork}) {
    if (!usedLiveNetwork) return;
    if (!BackendReachabilityService().matchesPrimaryBackend(uri)) return;
    BackendReachabilityService().recordPrimaryBackendSuccess();
  }

  void _notePrimaryBackendTransportFailure(Uri uri, {required bool usedLiveNetwork}) {
    if (!usedLiveNetwork) return;
    if (!BackendReachabilityService().matchesPrimaryBackend(uri)) return;
    BackendReachabilityService().recordPrimaryBackendTransportFailure();
  }

  Future<http.Response> get(
    String endpoint, {
    Map<String, String>? queryParams,
    bool includeAuth = true,
    Duration? timeout,
    bool useCache = true,
    Duration? cacheTtl,
    Map<String, String>? additionalHeaders,
  }) async {
    if (includeAuth) await _guardSessionExpiry();

    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint')
        .replace(queryParameters: queryParams);

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final cacheKey = OfflineCacheService.generateCacheKey(
      endpoint,
      queryParams,
      scope: requestScope,
    );

    // Check cache first if we're confident we're offline
    // But don't block the request if connectivity service isn't sure
    final isOnline = _connectivity.isOnline;
    final isOffline = _connectivity.isOffline;

    // Only use cache preemptively if we're definitely offline
    // Otherwise, try the network request first and fall back to cache on failure
    if (isOffline && useCache) {
      final cached = await _cacheService.getCachedResponse(cacheKey);
      if (cached != null) {
        DebugLogger.logApi('Returning cached response for: $endpoint');
        // Create a response from cached data
        return http.Response(
          cached.data,
          200,
          headers: cached.headers ?? {},
        );
      }
      DebugLogger.logApi('No cached data available for: $endpoint');
      // Don't throw here - let the network request attempt happen below
      // We'll handle the error in the catch block
    }

    // Wi‑Fi can stay "online" while the backoffice is down. After a transport
    // failure we defer non‑critical work — serve cache immediately when
    // available so pull‑to‑refresh does not wait through live timeouts/retries.
    if (useCache && shouldDeferRemoteFetch) {
      final cached = await _cacheService.getCachedResponse(cacheKey);
      if (cached != null) {
        DebugLogger.logApi(
            'Backend defer active — returning cached response for: $endpoint');
        return http.Response(
          cached.data,
          200,
          headers: cached.headers ?? {},
        );
      }
    }

    // GET requests shouldn't have Content-Type header
    var headers = await _getHeaders(
      includeAuth: includeAuth,
      contentType: '', // Empty for GET requests
      additionalHeaders: additionalHeaders,
      httpMethod: 'GET',
      endpoint: endpoint,
    );

    // Apply request interceptors
    headers = await _applyRequestInterceptors(headers, endpoint);

    DebugLogger.logApi('GET ${uri.toString()}');
    DebugLogger.logApi('Headers: ${_maskSensitiveHeaders(headers)}');
    if (queryParams != null && queryParams.isNotEmpty) {
      DebugLogger.logApi('Query params: $queryParams');
    }

    final requestTimeout = timeout ?? ApiTimeouts.defaultGet;

    // For cacheable GETs, a single live attempt then cache fallback keeps the
    // UI responsive when the server is stopped but the radio still shows online.
    final retryConfig = RetryConfig(
      maxRetries: useCache ? 0 : 3,
      initialDelay: const Duration(seconds: 1),
      backoffMultiplier: 2.0,
    );

    var usedLiveNetwork = false;

    // Create a client that doesn't follow redirects automatically
    // This prevents redirect loops when backend redirects to /login
    final client = http.Client();
    usedLiveNetwork = true;
    try {
      http.Response? response;
      Exception? lastException;

      // Retry logic for transient failures
      for (int attempt = 0; attempt <= retryConfig.maxRetries; attempt++) {
        try {
          response = await client
              .get(
            uri,
            headers: headers,
          )
              .timeout(
            requestTimeout,
            onTimeout: () {
              DebugLogger.logApi(
                  'Request timeout after ${requestTimeout.inSeconds}s (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
              throw TimeoutException(
                  'Request timed out after ${requestTimeout.inSeconds} seconds');
            },
          );

          // Check if response indicates a retryable error
          if (_isRetryableError(response.statusCode) && attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Retryable error ${response.statusCode}, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1})');
            await Future.delayed(delay);
            continue;
          }

          // Success or non-retryable error - break retry loop
          break;
        } on TimeoutException catch (e) {
          lastException = e;
          if (attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Timeout error, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
            await Future.delayed(delay);
            continue;
          }
          // Max retries reached - rethrow
          rethrow;
        } on http.ClientException catch (e) {
          lastException = e;
          // Connection closed / refused / reset will not recover with backoff;
          // retrying only adds multi‑second delays before cache fallback.
          DebugLogger.logApi(
              'Client error (no retry): $e — URL: ${uri.toString()}');
          break;
        }
      }

      // If response is null, all retries failed
      if (response == null) {
        if (lastException != null) {
          throw lastException;
        }
        throw Exception('Request failed after ${retryConfig.maxRetries + 1} attempts');
      }

      _notePrimaryBackendTransportSuccess(uri, usedLiveNetwork: usedLiveNetwork);

      // Check for redirect to login page - treat as auth error
      if (response.statusCode >= 300 && response.statusCode < 400) {
        final location = response.headers['location'];
        if (location != null && location.contains('/login')) {
          DebugLogger.logApi(
              'Redirect to /login detected - throwing AuthenticationException');
          // Clear expired session
          if (includeAuth) {
            await _session.clearSession();
          }
          throw AuthenticationException(
              'Session expired. Please log in again.');
        }
      }

      // Check for 401 Unauthorized — attempt a silent JWT refresh then retry once.
      // The refresh callback is registered by AuthService to avoid a circular import.
      if (response.statusCode == 401 && includeAuth) {
        DebugLogger.logApi('401 Unauthorized — attempting JWT refresh');
        final hasRefresh = await _jwtService.hasRefreshToken();
        if (hasRefresh && _tokenRefreshCallback != null) {
          final refreshed = await _tokenRefreshCallback!();
          if (refreshed) {
            DebugLogger.logApi('JWT refresh succeeded — retrying original request');
            final retryHeaders = await _getHeaders(
              includeAuth: includeAuth,
              contentType: '',
              additionalHeaders: additionalHeaders,
              httpMethod: 'GET',
              endpoint: endpoint,
            );
            http.Response? retryResponse;
            try {
              retryResponse = await client
                  .get(uri, headers: retryHeaders)
                  .timeout(requestTimeout);
            } on http.ClientException {
              rethrow; // Network failure during retry — not an auth error
            } on TimeoutException {
              rethrow;
            } catch (_) {}
            if (retryResponse != null && retryResponse.statusCode != 401) {
              response = retryResponse;
              // Fall through to normal response handling with the retry response.
            } else {
              await _jwtService.clearTokens();
              await _session.clearSession();
              throw AuthenticationException('Authentication required. Please log in.');
            }
          } else {
            DebugLogger.logApi('JWT refresh failed — clearing auth state');
            await _jwtService.clearTokens();
            await _session.clearSession();
            throw AuthenticationException('Session expired. Please log in again.');
          }
        } else {
          DebugLogger.logApi('No refresh token or callback — clearing session');
          await _session.clearSession();
          throw AuthenticationException('Authentication required. Please log in.');
        }
      }

      // Cache successful responses
      if (useCache && response.statusCode == 200) {
        await _cacheService.cacheResponse(
          cacheKey,
          response.body,
          ttl: cacheTtl ?? const Duration(hours: 1),
          headers: response.headers,
        );
      }

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);

        // Check if session cookie was refreshed (new Set-Cookie header)
        if (response.headers.containsKey('set-cookie')) {
          final newCookie = extractSessionCookie(response);
          if (newCookie != null) {
            DebugLogger.logApi('Session cookie refreshed - rotating session');
            await _session.rotateSession(newCookie, isOnline: isOnline);
          }
        }
      }

      DebugLogger.logApi('Response Status: ${response.statusCode}');
      DebugLogger.logApi('Response Headers: ${response.headers}');
      if (response.headers.containsKey('set-cookie')) {
        DebugLogger.logApi('Set-Cookie: ${response.headers['set-cookie']}');
      }
      if (response.body.length < 500) {
        DebugLogger.logApi('Response Body (first 500 chars): ${response.body}');
      } else {
        DebugLogger.logApi(
            'Response Body length: ${response.body.length} chars');
        DebugLogger.logApi(
            'Response Body preview: ${response.body.substring(0, 200)}...');
      }

      // Apply response interceptors
      await _applyResponseInterceptors(response, endpoint);

      return response;
    } on http.ClientException catch (e) {
      _notePrimaryBackendTransportFailure(uri, usedLiveNetwork: usedLiveNetwork);
      // Handle redirect loops and other client errors
      final errorMsg = e.toString().toLowerCase();
      if (errorMsg.contains('redirect loop') ||
          errorMsg.contains('too many redirects')) {
        DebugLogger.logApi(
            'Redirect loop detected - treating as auth error: $e');
        throw AuthenticationException('Session expired. Please log in again.');
      }

      // Try cache as fallback if network request failed
      if (useCache) {
        final cached = await _cacheService.getCachedResponse(cacheKey);
        if (cached != null) {
          DebugLogger.logApi('Network request failed, returning cached response for: $endpoint');
          return http.Response(
            cached.data,
            200,
            headers: cached.headers ?? {},
          );
        }
      }

      // Queue request if offline
      if (!isOnline) {
        await _queueGetRequest(
          endpoint,
          queryParams: queryParams,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }

      // Provide better error message
      if (errorMsg.contains('failed host lookup') ||
          errorMsg.contains('network is unreachable') ||
          errorMsg.contains('connection refused')) {
        throw Exception('Unable to connect to server. Please check your internet connection.');
      }

      // Re-throw other client exceptions
      rethrow;
    } catch (e) {
      _notePrimaryBackendTransportFailure(uri, usedLiveNetwork: usedLiveNetwork);
      // Try cache as fallback if network request failed
      if (useCache) {
        final cached = await _cacheService.getCachedResponse(cacheKey);
        if (cached != null) {
          DebugLogger.logApi('Network request failed, returning cached response for: $endpoint');
          return http.Response(
            cached.data,
            200,
            headers: cached.headers ?? {},
          );
        }
      }

      // Queue request if offline
      if (!isOnline) {
        await _queueGetRequest(
          endpoint,
          queryParams: queryParams,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }

      // Provide better error message for common network issues
      final errorMsg = e.toString().toLowerCase();
      if (errorMsg.contains('timeout') || errorMsg.contains('timed out')) {
        throw Exception('Request timed out. Please check your internet connection and try again.');
      }
      if (errorMsg.contains('no internet connection') && !useCache) {
        throw Exception('Unable to connect. Please check your internet connection.');
      }

      rethrow;
    } finally {
      client.close();
    }
  }

  /// Queue a GET request for later retry
  Future<void> _queueGetRequest(
    String endpoint, {
    Map<String, String>? queryParams,
    bool includeAuth = true,
    required String ownerKey,
  }) async {
    try {
      final request = QueuedRequest(
        method: 'GET',
        endpoint: endpoint,
        queryParams: queryParams,
        includeAuth: includeAuth,
        ownerKey: ownerKey,
      );
      await _queueService.queueRequest(request);
      DebugLogger.logApi('Queued GET request for later: $endpoint');
    } catch (e) {
      DebugLogger.logError('Failed to queue GET request: $e');
    }
  }

  Future<http.Response> post(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    bool skipExpiredGuard = false,
    String contentType = contentTypeJson,
    Map<String, String>? additionalHeaders,
    bool queueOnOffline = true,
  }) async {
    if (includeAuth && !skipExpiredGuard) await _guardSessionExpiry();

    final isOnline = _connectivity.isOnline;

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint');

    Object? encodedBody;
    if (body != null) {
      if (contentType == contentTypeJson) {
        encodedBody = jsonEncode(body);
      } else if (contentType == contentTypeFormUrlEncoded) {
        // Properly encode form-urlencoded data
        // Build URL-encoded string manually to ensure proper encoding
        final pairs = body.entries.map((entry) {
          final key = Uri.encodeComponent(entry.key);
          final value = Uri.encodeComponent(entry.value?.toString() ?? '');
          return '$key=$value';
        });
        encodedBody = pairs.join('&');
      } else {
        encodedBody = body;
      }
    }

    var headers = await _getHeaders(
      includeAuth: includeAuth,
      contentType: contentType,
      additionalHeaders: additionalHeaders,
      httpMethod: 'POST',
      endpoint: endpoint,
    );

    // Apply request interceptors
    headers = await _applyRequestInterceptors(headers, endpoint);

    DebugLogger.logApi('POST ${uri.toString()}');
    DebugLogger.logApi('Content-Type: $contentType');
    DebugLogger.logApi('Headers: ${_maskSensitiveHeaders(headers)}');
    if (encodedBody != null) {
      DebugLogger.logApi('Body: ${_maskSensitiveBody(encodedBody.toString())}');
    }

    // Retry configuration
    const retryConfig = RetryConfig(
      maxRetries: 2, // Fewer retries for POST (modify operations)
      initialDelay: Duration(seconds: 1),
      backoffMultiplier: 2.0,
    );

    final requestTimeout = ApiTimeouts.receive;
    var usedLiveNetwork = false;
    final client = http.Client();
    usedLiveNetwork = true;
    try {
      http.Response? response;
      Exception? lastException;

      // Retry logic for transient failures
      for (int attempt = 0; attempt <= retryConfig.maxRetries; attempt++) {
        try {
          response = await client
              .post(
            uri,
            headers: headers,
            body: encodedBody,
          )
              .timeout(
            requestTimeout,
            onTimeout: () {
              DebugLogger.logApi(
                  'POST timeout after ${requestTimeout.inSeconds}s (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
              throw TimeoutException(
                  'Request timed out after ${requestTimeout.inSeconds} seconds');
            },
          );

          // Check if response indicates a retryable error
          if (_isRetryableError(response.statusCode) && attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Retryable error ${response.statusCode}, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1})');
            await Future.delayed(delay);
            continue;
          }

          // Success or non-retryable error - break retry loop
          break;
        } on TimeoutException catch (e) {
          lastException = e;
          if (attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Timeout error, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
            await Future.delayed(delay);
            continue;
          }
          rethrow;
        } on http.ClientException catch (e) {
          lastException = e;
          DebugLogger.logApi(
              'POST client error (no retry): $e — URL: ${uri.toString()}');
          break;
        }
      }

      // If response is null, all retries failed
      if (response == null) {
        if (lastException != null) {
          throw lastException;
        }
        throw Exception('Request failed after ${retryConfig.maxRetries + 1} attempts');
      }

      _notePrimaryBackendTransportSuccess(uri, usedLiveNetwork: usedLiveNetwork);

      DebugLogger.logApi('Response Status: ${response.statusCode}');
      DebugLogger.logApi('Response Headers: ${response.headers}');
      if (response.headers.containsKey('set-cookie')) {
        DebugLogger.logApi('Set-Cookie: ${response.headers['set-cookie']}');
      }
      if (response.body.length < 500) {
        DebugLogger.logApi('Response Body (first 500 chars): ${response.body}');
      } else {
        DebugLogger.logApi(
            'Response Body length: ${response.body.length} chars');
        DebugLogger.logApi(
            'Response Body preview: ${response.body.substring(0, 200)}...');
      }

      // Apply response interceptors
      await _applyResponseInterceptors(response, endpoint);

      // Handle authentication errors — but only for authenticated requests.
      // Unauthenticated endpoints (e.g. login / token issuance) legitimately
      // return 401 for bad credentials; the caller handles the status code.
      //
      // When the backend returns 401 on a POST it most likely means the JWT
      // access token has expired (the backend now returns 401 immediately when
      // a Bearer token is presented but invalid, rather than falling through to
      // a confusing CSRF 400).  Attempt a silent token refresh before giving up.
      if (response.statusCode == 401 && includeAuth) {
        DebugLogger.logApi('401 Unauthorized — attempting JWT refresh');
        final hasRefresh = await _jwtService.hasRefreshToken();
        if (hasRefresh && _tokenRefreshCallback != null) {
          final refreshed = await _tokenRefreshCallback!();
          if (refreshed) {
            DebugLogger.logApi('JWT refresh succeeded — retrying POST');
            final retryHeaders = await _getHeaders(
              includeAuth: includeAuth,
              contentType: contentType,
              additionalHeaders: additionalHeaders,
              httpMethod: 'POST',
              endpoint: endpoint,
            );
            http.Response? retryResponse;
            try {
              retryResponse = await client
                  .post(uri, headers: retryHeaders, body: encodedBody)
                  .timeout(requestTimeout);
            } on http.ClientException {
              rethrow; // Network failure during retry — not an auth error
            } on TimeoutException {
              rethrow;
            } catch (_) {}
            if (retryResponse != null && retryResponse.statusCode != 401) {
              response = retryResponse;
              // Fall through to normal response handling below.
            } else {
              await _jwtService.clearTokens();
              await _session.clearSession();
              throw AuthenticationException(
                  'Authentication required. Please log in.');
            }
          } else {
            DebugLogger.logApi('JWT refresh failed — clearing auth state');
            await _jwtService.clearTokens();
            await _session.clearSession();
            throw AuthenticationException('Session expired. Please log in again.');
          }
        } else {
          DebugLogger.logApi('No refresh token or callback — clearing session');
          await _session.clearSession();
          throw AuthenticationException('Authentication required. Please log in.');
        }
      }

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);

        // Check if session cookie was refreshed (new Set-Cookie header)
        if (response.headers.containsKey('set-cookie')) {
          final newCookie = extractSessionCookie(response);
          if (newCookie != null) {
            DebugLogger.logApi('Session cookie refreshed - rotating session');
            await _session.rotateSession(newCookie, isOnline: isOnline);
          }
        }
      }

      return response;
    } on http.ClientException catch (_) {
      _notePrimaryBackendTransportFailure(uri, usedLiveNetwork: usedLiveNetwork);
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queuePostRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          contentType: contentType,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } catch (_) {
      _notePrimaryBackendTransportFailure(uri, usedLiveNetwork: usedLiveNetwork);
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queuePostRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          contentType: contentType,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } finally {
      client.close();
    }
  }

  /// Queue a POST request for later retry
  Future<void> _queuePostRequest(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    String? contentType,
    required String ownerKey,
  }) async {
    try {
      final request = QueuedRequest(
        method: 'POST',
        endpoint: endpoint,
        body: body,
        includeAuth: includeAuth,
        contentType: contentType,
        ownerKey: ownerKey,
      );
      await _queueService.queueRequest(request);
      DebugLogger.logApi('Queued POST request for later: $endpoint');
    } catch (e) {
      DebugLogger.logError('Failed to queue POST request: $e');
    }
  }

  Future<http.Response> put(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    bool queueOnOffline = true,
  }) async {
    if (includeAuth) await _guardSessionExpiry();

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final isOnline = _connectivity.isOnline;
    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint');
    const requestTimeout = ApiTimeouts.receive;
    final encodedPut = body != null ? jsonEncode(body) : null;

    final client = http.Client();
    try {
      var headers = await _getHeaders(
        includeAuth: includeAuth,
        contentType: contentTypeJson,
        httpMethod: 'PUT',
        endpoint: endpoint,
      );

      headers = await _applyRequestInterceptors(headers, endpoint);

      DebugLogger.logApi('PUT ${uri.toString()}');
      DebugLogger.logApi('Headers: ${_maskSensitiveHeaders(headers)}');
      if (encodedPut != null) {
        DebugLogger.logApi('Body: ${_maskSensitiveBody(encodedPut)}');
      }

      http.Response response = await client
          .put(uri, headers: headers, body: encodedPut)
          .timeout(requestTimeout);

      DebugLogger.logApi('PUT Response Status: ${response.statusCode}');
      if (response.statusCode < 200 || response.statusCode >= 300) {
        final preview = response.body.length > 800
            ? '${response.body.substring(0, 800)}…'
            : response.body;
        DebugLogger.logApi('PUT Response Body preview: $preview');
      }

      // Handle 401 — attempt silent JWT refresh then retry once.
      if (response.statusCode == 401 && includeAuth) {
        DebugLogger.logApi('401 Unauthorized — attempting JWT refresh');
        final hasRefresh = await _jwtService.hasRefreshToken();
        if (hasRefresh && _tokenRefreshCallback != null) {
          final refreshed = await _tokenRefreshCallback!();
          if (refreshed) {
            DebugLogger.logApi('JWT refresh succeeded — retrying PUT');
            final retryHeaders = await _getHeaders(
              includeAuth: includeAuth,
              contentType: contentTypeJson,
              httpMethod: 'PUT',
              endpoint: endpoint,
            );
            http.Response? retryResponse;
            try {
              retryResponse = await client
                  .put(uri, headers: retryHeaders, body: encodedPut)
                  .timeout(requestTimeout);
            } on http.ClientException {
              rethrow; // Network failure during retry — not an auth error
            } on TimeoutException {
              rethrow;
            } catch (_) {}
            if (retryResponse != null && retryResponse.statusCode != 401) {
              response = retryResponse;
            } else {
              await _jwtService.clearTokens();
              await _session.clearSession();
              throw AuthenticationException('Authentication required. Please log in.');
            }
          } else {
            DebugLogger.logApi('JWT refresh failed — clearing auth state');
            await _jwtService.clearTokens();
            await _session.clearSession();
            throw AuthenticationException('Session expired. Please log in again.');
          }
        } else {
          DebugLogger.logApi('No refresh token or callback — clearing session');
          await _session.clearSession();
          throw AuthenticationException('Authentication required. Please log in.');
        }
      }

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);
      }

      MobileAppUpdateHandler.instance.tryHandleHttpResponse(response);
      return response;
    } on http.ClientException {
      if (!isOnline && queueOnOffline) {
        await _queuePutRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } catch (_) {
      if (!isOnline && queueOnOffline) {
        await _queuePutRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } finally {
      client.close();
    }
  }

  /// Queue a PUT request for later retry
  Future<void> _queuePutRequest(
    String endpoint, {
    Map<String, dynamic>? body,
    bool includeAuth = true,
    required String ownerKey,
  }) async {
    try {
      final request = QueuedRequest(
        method: 'PUT',
        endpoint: endpoint,
        body: body,
        includeAuth: includeAuth,
        ownerKey: ownerKey,
      );
      await _queueService.queueRequest(request);
      DebugLogger.logApi('Queued PUT request for later: $endpoint');
    } catch (e) {
      DebugLogger.logError('Failed to queue PUT request: $e');
    }
  }

  Future<http.Response> delete(
    String endpoint, {
    bool includeAuth = true,
    bool queueOnOffline = true,
    Map<String, String>? additionalHeaders,
  }) async {
    if (includeAuth) await _guardSessionExpiry();

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final isOnline = _connectivity.isOnline;
    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint');
    const requestTimeout = ApiTimeouts.receive;

    final client = http.Client();
    try {
      var headers = await _getHeaders(
        includeAuth: includeAuth,
        contentType: '', // Empty for DELETE requests
        additionalHeaders: additionalHeaders,
        httpMethod: 'DELETE',
        endpoint: endpoint,
      );

      headers = await _applyRequestInterceptors(headers, endpoint);

      DebugLogger.logApi('DELETE ${uri.toString()}');

      http.Response response =
          await client.delete(uri, headers: headers).timeout(requestTimeout);

      DebugLogger.logApi('DELETE Response Status: ${response.statusCode}');

      // Handle 401 — attempt silent JWT refresh then retry once.
      if (response.statusCode == 401 && includeAuth) {
        DebugLogger.logApi('401 Unauthorized — attempting JWT refresh');
        final hasRefresh = await _jwtService.hasRefreshToken();
        if (hasRefresh && _tokenRefreshCallback != null) {
          final refreshed = await _tokenRefreshCallback!();
          if (refreshed) {
            DebugLogger.logApi('JWT refresh succeeded — retrying DELETE');
            final retryHeaders = await _getHeaders(
              includeAuth: includeAuth,
              contentType: '',
              additionalHeaders: additionalHeaders,
              httpMethod: 'DELETE',
              endpoint: endpoint,
            );
            http.Response? retryResponse;
            try {
              retryResponse = await client
                  .delete(uri, headers: retryHeaders)
                  .timeout(requestTimeout);
            } on http.ClientException {
              rethrow; // Network failure during retry — not an auth error
            } on TimeoutException {
              rethrow;
            } catch (_) {}
            if (retryResponse != null && retryResponse.statusCode != 401) {
              response = retryResponse;
            } else {
              await _jwtService.clearTokens();
              await _session.clearSession();
              throw AuthenticationException('Authentication required. Please log in.');
            }
          } else {
            DebugLogger.logApi('JWT refresh failed — clearing auth state');
            await _jwtService.clearTokens();
            await _session.clearSession();
            throw AuthenticationException('Session expired. Please log in again.');
          }
        } else {
          DebugLogger.logApi('No refresh token or callback — clearing session');
          await _session.clearSession();
          throw AuthenticationException('Authentication required. Please log in.');
        }
      }

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);
      }

      MobileAppUpdateHandler.instance.tryHandleHttpResponse(response);
      return response;
    } on http.ClientException {
      if (!isOnline && queueOnOffline) {
        await _queueDeleteRequest(
          endpoint,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } catch (_) {
      if (!isOnline && queueOnOffline) {
        await _queueDeleteRequest(
          endpoint,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } finally {
      client.close();
    }
  }

  /// Queue a DELETE request for later retry
  Future<void> _queueDeleteRequest(
    String endpoint, {
    bool includeAuth = true,
    required String ownerKey,
  }) async {
    try {
      final request = QueuedRequest(
        method: 'DELETE',
        endpoint: endpoint,
        includeAuth: includeAuth,
        ownerKey: ownerKey,
      );
      await _queueService.queueRequest(request);
      DebugLogger.logApi('Queued DELETE request for later: $endpoint');
    } catch (e) {
      DebugLogger.logError('Failed to queue DELETE request: $e');
    }
  }

  // Extract cookies from response headers
  String? extractSessionCookie(http.Response response) {
    final raw = response.headers['set-cookie'];
    final cookies = raw?.trim();
    DebugLogger.logApi('Extracting session cookie from: $cookies');

    if (cookies == null || cookies.isEmpty) {
      DebugLogger.logApi('No Set-Cookie header found');
      return null;
    }

    // Extract session cookie value (adjust pattern based on backend)
    final sessionMatch = RegExp(r'session=([^;]+)').firstMatch(cookies);
    if (sessionMatch != null) {
      final value = sessionMatch.group(1)!;
      // Ignore cleared cookies (empty or whitespace-only value)
      if (value.trim().isEmpty) {
        DebugLogger.logApi('Session cookie cleared by server (empty value)');
        return null;
      }
      final cookie = 'session=$value';
      final preview = cookie.length > 50 ? '${cookie.substring(0, 50)}...' : cookie;
      DebugLogger.logApi('Extracted session cookie: $preview');
      return cookie;
    }

    // Check for explicit session cookie clearing (e.g. "session=; Expires=...")
    final trimmedLeft = cookies.trimLeft();
    if (trimmedLeft.startsWith('session=;') ||
        cookies.contains('Max-Age=0')) {
      DebugLogger.logApi('Session cookie cleared by server');
      return null;
    }

    // Fallback: first name=value before ';' (do not split on ',' — Expires dates contain commas)
    final fallbackCookie = cookies.split(';').first.trim();
    final preview = fallbackCookie.length > 50
        ? '${fallbackCookie.substring(0, 50)}...'
        : fallbackCookie;
    DebugLogger.logApi('Using fallback cookie: $preview');
    return fallbackCookie;
  }

  // Helper to mask sensitive headers for logging
  Map<String, String> _maskSensitiveHeaders(Map<String, String> headers) {
    final masked = Map<String, String>.from(headers);
    if (masked.containsKey('Cookie')) {
      final cookie = masked['Cookie']!;
      if (cookie.length > 50) {
        masked['Cookie'] = '${cookie.substring(0, 50)}... (masked)';
      }
    }
    for (final key in masked.keys.toList()) {
      if (key.toLowerCase() != 'authorization') continue;
      final auth = masked[key]!;
      if (auth.length > 24) {
        masked[key] = '${auth.substring(0, 16)}…***MASKED***';
      }
      break;
    }
    return masked;
  }

  // Helper to mask sensitive body data for logging
  String _maskSensitiveBody(String body) {
    // Mask password values in form-urlencoded data
    return body.replaceAllMapped(
      RegExp(r'password=([^&]+)', caseSensitive: false),
      (match) => 'password=***MASKED***',
    );
  }

  /// Check if an HTTP status code indicates a retryable error
  bool _isRetryableError(int statusCode) {
    // Retry on server errors (5xx) and some client errors
    // 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout are retryable
    return statusCode == 502 || statusCode == 503 || statusCode == 504;
  }

  /// Calculate retry delay with exponential backoff.
  /// attempt=0 → initialDelay, attempt=1 → initialDelay * multiplier, etc.
  Duration _calculateRetryDelay(int attempt, RetryConfig config) {
    final delayMs =
        (config.initialDelay.inMilliseconds * pow(config.backoffMultiplier, attempt))
            .round();
    final delay = Duration(milliseconds: delayMs);
    return delay > config.maxDelay ? config.maxDelay : delay;
  }
}
