import 'package:flutter/foundation.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class UserAnalyticsProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();

  Map<String, dynamic>? _analyticsData;

  Map<String, dynamic>? get analyticsData => _analyticsData;
  bool get isLoading => opLoading;
  String? get error => opError;

  /// Loads dashboard stats and the recent activity feed (same sources as admin dashboard).
  Future<void> loadAnalytics() async {
    if (shouldDeferRemoteFetch) {
      notifyListeners();
      return;
    }

    await runAsyncOperation(() async {
      final statsResponse = await _api.get(
        AppConfig.mobileDashboardStatsEndpoint,
      );

      if (statsResponse.statusCode == 200) {
        final decoded = decodeJsonObject(statsResponse.body);
        if (mobileResponseIsSuccess(decoded)) {
          final data = unwrapMobileDataMap(decoded) ?? {};
          _analyticsData = Map<String, dynamic>.from(data);
        } else {
          _analyticsData = null;
          throw Exception(decoded['message']?.toString() ?? 'Failed to load analytics');
        }
      } else {
        _analyticsData = null;
        throw Exception('Failed to load analytics: ${statsResponse.statusCode}');
      }

      if (_analyticsData != null) {
        try {
          final activityResponse = await _api.get(
            AppConfig.mobileDashboardActivityEndpoint,
          );
          if (activityResponse.statusCode == 200) {
            final actDecoded = decodeJsonObject(activityResponse.body);
            if (mobileResponseIsSuccess(actDecoded)) {
              final activityPayload = unwrapMobileDataMap(actDecoded) ?? {};
              _analyticsData!['activity'] = activityPayload;
            }
          }
        } catch (e) {
          DebugLogger.logErrorWithTag('ANALYTICS', 'Activity feed: $e');
        }
      }
    });
  }

  void clearError() => clearOpError();
}
