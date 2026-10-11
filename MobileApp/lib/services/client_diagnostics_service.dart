import 'dart:io' show Platform;

import 'package:dio/dio.dart';

import '../config/app_config.dart';
import '../utils/debug_logger.dart';
import 'api_service.dart';
import 'app_build_metadata.dart';
import '../di/service_locator.dart';

/// Sends on-device failures to the Backoffice (`POST /diagnostics/client-error`)
/// so they appear as `mobile_client_error` security events with full details,
/// even though users only see a generic message. Fire-and-forget: reporting never
/// throws and is skipped when the device is offline.
class ClientDiagnosticsService {
  ClientDiagnosticsService._();

  static const String categoryOfflineDownload = 'offline_download';
  static const String categoryOfflineOpen = 'offline_open';

  static const Duration _repeatWindow = Duration(minutes: 10);
  static final Map<String, DateTime> _lastSent = {};

  /// Short human-readable description plus structured extras for [error].
  static ({String type, String message, Map<String, dynamic> details})
      describe(Object error) {
    if (error is DioException) {
      final uri = error.requestOptions.uri;
      return (
        type: 'DioException/${error.type.name}',
        message: error.message ?? error.toString(),
        details: {
          'http_status': error.response?.statusCode,
          'request': '${error.requestOptions.method} ${uri.host}${uri.path}',
        },
      );
    }
    final dynamic e = error;
    Map<String, dynamic> extra = const {};
    try {
      final d = e.details;
      if (d is Map<String, dynamic>) extra = d;
    } catch (_) {}
    return (type: error.runtimeType.toString(), message: error.toString(), details: extra);
  }

  static Future<void> report({
    required String category,
    required Object error,
    StackTrace? stackTrace,
    int? assignmentId,
    int? templateId,
    String? language,
    List<String> trace = const [],
    Map<String, dynamic> extraDetails = const {},
  }) async {
    try {
      final info = describe(error);
      final key = '$category|$assignmentId|${info.type}|${info.message}';
      final now = DateTime.now();
      final last = _lastSent[key];
      if (last != null && now.difference(last) < _repeatWindow) return;
      _lastSent[key] = now;

      final api = sl<ApiService>();
      await api.post(
        AppConfig.clientDiagnosticsEndpoint,
        body: {
          'category': category,
          'message': info.message,
          'error_type': info.type,
          'stack': stackTrace?.toString() ?? '',
          'assignment_id': assignmentId,
          'template_id': templateId,
          'language': language,
          'app_version': AppBuildMetadata.appVersionSemver,
          'platform': Platform.isIOS ? 'ios' : 'android',
          'os_version': Platform.operatingSystemVersion,
          'details': {
            ...info.details,
            ...extraDetails,
            'trace': trace,
          },
        },
        queueOnOffline: false,
        retryable: false,
      );
    } catch (e) {
      DebugLogger.logWarn('DIAGNOSTICS', 'Could not report $category failure: $e');
    }
  }
}
