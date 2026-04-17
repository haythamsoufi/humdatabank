import 'package:dio/dio.dart';
import '../config/app_config.dart';
import '../utils/debug_logger.dart';
import 'jwt_token_service.dart';
import 'storage_service.dart';
import 'push_notification_service.dart';

/// Dio-based HTTP client with built-in auth, retry, and logging interceptors.
///
/// New code should prefer [DioClient] over the legacy [ApiService] for:
/// - Request cancellation via [CancelToken]
/// - Typed error handling via [DioException]
/// - File upload progress callbacks
/// - Streaming responses
///
/// Migration: Replace `ApiService`/`sl<ApiService>()` GET calls with `DioClient.instance.get(...)`
/// for new endpoints. Existing ApiService calls continue to work unchanged.
class DioClient {
  static final DioClient _instance = DioClient._internal();
  static DioClient get instance => _instance;
  factory DioClient() => _instance;

  late final Dio dio;

  DioClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: AppConfig.baseApiUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 30),
      sendTimeout: const Duration(seconds: 30),
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
    ));

    dio.interceptors.addAll([
      _AuthInterceptor(),
      _RetryInterceptor(),
      _LoggingInterceptor(),
    ]);
  }

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    CancelToken? cancelToken,
    Options? options,
  }) {
    return dio.get<T>(path,
        queryParameters: queryParameters,
        cancelToken: cancelToken,
        options: options);
  }

  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    CancelToken? cancelToken,
    Options? options,
    void Function(int, int)? onSendProgress,
  }) {
    return dio.post<T>(path,
        data: data,
        queryParameters: queryParameters,
        cancelToken: cancelToken,
        options: options,
        onSendProgress: onSendProgress);
  }

  Future<Response<T>> put<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    CancelToken? cancelToken,
    Options? options,
  }) {
    return dio.put<T>(path,
        data: data,
        queryParameters: queryParameters,
        cancelToken: cancelToken,
        options: options);
  }

  Future<Response<T>> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    CancelToken? cancelToken,
    Options? options,
  }) {
    return dio.delete<T>(path,
        data: data,
        queryParameters: queryParameters,
        cancelToken: cancelToken,
        options: options);
  }
}

class _AuthInterceptor extends Interceptor {
  final JwtTokenService _jwtService = JwtTokenService();
  final StorageService _storage = StorageService();

  @override
  Future<void> onRequest(
      RequestOptions options, RequestInterceptorHandler handler) async {
    final accessToken = await _jwtService.getAccessToken();
    if (accessToken != null && accessToken.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $accessToken';
    }

    final cookie = await _storage.getSecure(AppConfig.sessionCookieKey);
    if (cookie != null) {
      options.headers['Cookie'] = cookie;
    }

    try {
      final pushService = PushNotificationService();
      final deviceToken = pushService.currentToken;
      if (deviceToken != null) {
        options.headers['X-Device-Token'] = deviceToken;
      }
    } catch (_) {}

    final lang = await _storage.getString('selected_language') ?? 'en';
    options.headers['Accept-Language'] = lang;

    handler.next(options);
  }
}

class _RetryInterceptor extends Interceptor {
  static const _maxRetries = 3;
  static const _retryableStatuses = {502, 503, 504};

  @override
  Future<void> onError(
      DioException err, ErrorInterceptorHandler handler) async {
    final statusCode = err.response?.statusCode;
    if (statusCode != null && _retryableStatuses.contains(statusCode)) {
      for (int attempt = 1; attempt <= _maxRetries; attempt++) {
        final delay = Duration(seconds: attempt * 2);
        DebugLogger.logApi(
            'Retry $attempt/$_maxRetries after ${delay.inSeconds}s for ${err.requestOptions.path}');
        await Future.delayed(delay);
        try {
          final response =
              await DioClient.instance.dio.fetch(err.requestOptions);
          return handler.resolve(response);
        } on DioException catch (retryErr) {
          if (attempt == _maxRetries) {
            return handler.next(retryErr);
          }
        }
      }
    }
    handler.next(err);
  }
}

class _LoggingInterceptor extends Interceptor {
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    DebugLogger.logApi('[Dio] ${options.method} ${options.uri}');
    handler.next(options);
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    DebugLogger.logApi(
        '[Dio] ${response.statusCode} ${response.requestOptions.path}');
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    DebugLogger.logApi('[Dio] ERROR ${err.type}: ${err.message}');
    handler.next(err);
  }
}
