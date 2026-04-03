import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import '../config/app_config.dart';
import 'storage_service.dart';
import 'session_service.dart';
import 'push_notification_service.dart';
import 'connectivity_service.dart';
import 'offline_queue_service.dart';
import 'offline_cache_service.dart';
import '../utils/debug_logger.dart';
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

  final StorageService _storage = StorageService();
  final SessionService _session = SessionService();
  final ConnectivityService _connectivity = ConnectivityService();
  final OfflineQueueService _queueService = OfflineQueueService();
  final OfflineCacheService _cacheService = OfflineCacheService();
  final UserScopeService _scopeService = UserScopeService();

  static const String _csrfTokenStorageKey = 'csrf_token_v1';

  Future<String?> _getCachedCsrfToken() async {
    return _storage.getSecure(_csrfTokenStorageKey);
  }

  Future<void> _cacheCsrfToken(String token) async {
    await _storage.setSecure(_csrfTokenStorageKey, token);
  }

  Future<void> _clearCsrfToken() async {
    await _storage.remove(_csrfTokenStorageKey);
  }

  Future<String?> refreshCsrfToken() async {
    try {
      final resp =
          await get('/api/v1/csrf-token', includeAuth: true, useCache: false);
      if (resp.statusCode != 200) return null;
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final token = data['csrf_token']?.toString();
      if (token != null && token.isNotEmpty) {
        await _cacheCsrfToken(token);
      }
      return token;
    } catch (_) {
      return null;
    }
  }

  bool _shouldAttachPublicApiKey(String endpoint) {
    // Only attach to Backoffice public API routes; avoid interfering with AI endpoints.
    return endpoint.startsWith('/api/v1/');
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
    for (final interceptor in _responseInterceptors) {
      await interceptor(response, endpoint);
    }
  }

  Future<Map<String, String>> _getHeaders({
    bool includeAuth = true,
    String contentType = contentTypeJson,
    Map<String, String>? additionalHeaders,
    String? httpMethod,
    String? endpoint,
  }) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest', // Helps backend identify API requests
    };

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

    // Supply shared mobile auth header if configured (needed for CSRF-exempt endpoints).
    if (AppConfig.mobileNotificationApiKey.isNotEmpty) {
      headers['X-Mobile-Auth'] = AppConfig.mobileNotificationApiKey;
    }

    // Attach DB-managed public API key for /api/v1 endpoints (public reads).
    // Do not set if caller already provided Authorization via additionalHeaders.
    if (endpoint != null &&
        _shouldAttachPublicApiKey(endpoint) &&
        AppConfig.apiKey.isNotEmpty &&
        !headers.containsKey('Authorization') &&
        (additionalHeaders == null ||
            !additionalHeaders.containsKey('Authorization'))) {
      headers['Authorization'] = 'Bearer ${AppConfig.apiKey}';
    }

    // Attach CSRF token for unsafe session-authenticated requests.
    if (includeAuth &&
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

  Future<http.Response> get(
    String endpoint, {
    Map<String, String>? queryParams,
    bool includeAuth = true,
    Duration? timeout,
    bool useCache = true,
    Duration? cacheTtl,
    Map<String, String>? additionalHeaders,
  }) async {
    // Check session expiration before making authenticated requests
    if (includeAuth) {
      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        DebugLogger.logApi(
            'Session expired - throwing AuthenticationException');
        throw AuthenticationException('Session expired. Please log in again.');
      }
    }

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

    // Use default timeout of 10 seconds if not specified
    final requestTimeout = timeout ?? const Duration(seconds: 10);

    // Retry configuration
    const retryConfig = RetryConfig(
      maxRetries: 3,
      initialDelay: Duration(seconds: 1),
      backoffMultiplier: 2.0,
    );

    // Create a client that doesn't follow redirects automatically
    // This prevents redirect loops when backend redirects to /login
    final client = http.Client();
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
          if (attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Client error, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
            await Future.delayed(delay);
            continue;
          }
          // Max retries reached - will be handled below
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

      // Check for 401 Unauthorized
      if (response.statusCode == 401) {
        DebugLogger.logApi(
            '401 Unauthorized - throwing AuthenticationException');
        // Clear expired session
        if (includeAuth) {
          await _session.clearSession();
        }
        throw AuthenticationException(
            'Authentication required. Please log in.');
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
    String contentType = contentTypeJson,
    Map<String, String>? additionalHeaders,
    bool queueOnOffline = true,
  }) async {
    // Check session expiration before making authenticated requests
    if (includeAuth) {
      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        DebugLogger.logApi(
            'Session expired - throwing AuthenticationException');
        throw AuthenticationException('Session expired. Please log in again.');
      }
    }

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

    // Ensure we have a CSRF token for unsafe session-auth requests.
    if (includeAuth) {
      final cached = await _getCachedCsrfToken();
      if (cached == null || cached.isEmpty) {
        final token = await refreshCsrfToken();
        if (token != null && token.isNotEmpty) {
          headers = Map<String, String>.from(headers);
          headers['X-CSRFToken'] = token;
        }
      }
    }

    // Apply request interceptors
    headers = await _applyRequestInterceptors(headers, endpoint);

    DebugLogger.logApi('POST ${uri.toString()}');
    DebugLogger.logApi('Content-Type: $contentType');
    DebugLogger.logApi('Headers: ${_maskSensitiveHeaders(headers)}');
    if (encodedBody != null) {
      final bodyStr = encodedBody.toString();
      DebugLogger.logApi('Body: ${_maskSensitiveBody(bodyStr)}');
    }

    // Retry configuration
    const retryConfig = RetryConfig(
      maxRetries: 2, // Fewer retries for POST (modify operations)
      initialDelay: Duration(seconds: 1),
      backoffMultiplier: 2.0,
    );

    final requestTimeout = const Duration(seconds: 30); // Longer timeout for POST
    final client = http.Client();
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
          if (attempt < retryConfig.maxRetries) {
            final delay = _calculateRetryDelay(attempt, retryConfig);
            DebugLogger.logApi(
                'Client error, retrying in ${delay.inSeconds}s... (attempt ${attempt + 1}/${retryConfig.maxRetries + 1}) - URL: ${uri.toString()}');
            await Future.delayed(delay);
            continue;
          }
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

      DebugLogger.logApi('Response Status: ${response.statusCode}');

      // If CSRF failed, refresh token once and retry.
      if (includeAuth && response.statusCode == 400) {
        final bodyText = response.body.toString().toLowerCase();
        if (bodyText.contains('csrf')) {
          await _clearCsrfToken();
          final newToken = await refreshCsrfToken();
          if (newToken != null && newToken.isNotEmpty) {
            final retryHeaders = Map<String, String>.from(headers);
            retryHeaders['X-CSRFToken'] = newToken;
            final retryResp = await client
                .post(uri, headers: retryHeaders, body: encodedBody)
                .timeout(requestTimeout);
            return retryResp;
          }
        }
      }
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

      // Handle authentication errors
      if (response.statusCode == 401) {
        DebugLogger.logApi(
            '401 Unauthorized - throwing AuthenticationException');
        // Clear expired session
        if (includeAuth) {
          await _session.clearSession();
        }
        throw AuthenticationException(
            'Authentication required. Please log in.');
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
    } on http.ClientException catch (e) {
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
    } catch (e) {
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
    // Check session expiration before making authenticated requests
    if (includeAuth) {
      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        DebugLogger.logApi(
            'Session expired - throwing AuthenticationException');
        throw AuthenticationException('Session expired. Please log in again.');
      }
    }

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final isOnline = _connectivity.isOnline;
    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint');

    try {
      var headers = await _getHeaders(
        includeAuth: includeAuth,
        contentType: contentTypeJson,
        httpMethod: 'PUT',
        endpoint: endpoint,
      );

      // Ensure we have a CSRF token for unsafe session-auth requests.
      if (includeAuth) {
        final cached = await _getCachedCsrfToken();
        if (cached == null || cached.isEmpty) {
          final token = await refreshCsrfToken();
          if (token != null && token.isNotEmpty) {
            headers = Map<String, String>.from(headers);
            headers['X-CSRFToken'] = token;
          }
        }
      }

      final response = await http.put(
        uri,
        headers: headers,
        body: body != null ? jsonEncode(body) : null,
      );

      // If CSRF failed, refresh token once and retry.
      if (includeAuth && response.statusCode == 400) {
        final bodyText = response.body.toString().toLowerCase();
        if (bodyText.contains('csrf')) {
          await _clearCsrfToken();
          final newToken = await refreshCsrfToken();
          if (newToken != null && newToken.isNotEmpty) {
            headers = Map<String, String>.from(headers);
            headers['X-CSRFToken'] = newToken;
            final retryResp = await http.put(
              uri,
              headers: headers,
              body: body != null ? jsonEncode(body) : null,
            );
            return retryResp;
          }
        }
      }

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);
      }

      return response;
    } on http.ClientException catch (e) {
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queuePutRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } catch (e) {
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queuePutRequest(
          endpoint,
          body: body,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
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
    // Check session expiration before making authenticated requests
    if (includeAuth) {
      final isExpired = await _session.isSessionExpired();
      if (isExpired) {
        DebugLogger.logApi(
            'Session expired - throwing AuthenticationException');
        throw AuthenticationException('Session expired. Please log in again.');
      }
    }

    final requestScope =
        await _scopeService.getScope(includeAuth: includeAuth);
    final isOnline = _connectivity.isOnline;
    final uri = Uri.parse('${AppConfig.baseApiUrl}$endpoint');

    try {
      final response = await http.delete(
        uri,
        headers: await _getHeaders(
          includeAuth: includeAuth,
          contentType: '', // Empty for DELETE requests
          additionalHeaders: additionalHeaders,
        ),
      );

      // Update last validation time on successful authenticated requests
      if (includeAuth &&
          response.statusCode >= 200 &&
          response.statusCode < 300) {
        await _session.updateLastValidation(isOnline: isOnline);
      }

      return response;
    } on http.ClientException catch (e) {
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queueDeleteRequest(
          endpoint,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
    } catch (e) {
      // Queue request if offline
      if (!isOnline && queueOnOffline) {
        await _queueDeleteRequest(
          endpoint,
          includeAuth: includeAuth,
          ownerKey: requestScope,
        );
      }
      rethrow;
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
    final cookies = response.headers['set-cookie'];
    DebugLogger.logApi('Extracting session cookie from: $cookies');

    if (cookies == null) {
      DebugLogger.logApi('No Set-Cookie header found');
      return null;
    }

    // Extract session cookie (adjust pattern based on backend)
    final sessionMatch = RegExp(r'session=([^;]+)').firstMatch(cookies);
    if (sessionMatch != null) {
      final cookie = 'session=${sessionMatch.group(1)}';
      DebugLogger.logApi(
          'Extracted session cookie: ${cookie.substring(0, 50)}...');
      return cookie;
    }

    // Fallback: return all cookies
    final fallbackCookie = cookies.split(',').first;
    DebugLogger.logApi(
        'Using fallback cookie: ${fallbackCookie.substring(0, 50)}...');
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

  /// Calculate retry delay with exponential backoff
  Duration _calculateRetryDelay(int attempt, RetryConfig config) {
    final delayMs = (config.initialDelay.inMilliseconds *
            (config.backoffMultiplier * attempt))
        .round();
    final delay = Duration(milliseconds: delayMs);
    return delay > config.maxDelay ? config.maxDelay : delay;
  }
}
