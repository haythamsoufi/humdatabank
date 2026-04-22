import 'package:flutter/foundation.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class UserAnalyticsProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();

  Map<String, dynamic>? _analyticsData;
  bool _isLoading = false;
  String? _error;

  Map<String, dynamic>? get analyticsData => _analyticsData;
  bool get isLoading => _isLoading;
  String? get error => _error;

  /// Loads dashboard stats and the recent activity feed (same sources as admin dashboard).
  Future<void> loadAnalytics() async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final statsResponse = await _api.get(
        AppConfig.mobileDashboardStatsEndpoint,
      );

      if (statsResponse.statusCode == 200) {
        final decoded = decodeJsonObject(statsResponse.body);
        if (mobileResponseIsSuccess(decoded)) {
          final data = unwrapMobileDataMap(decoded) ?? {};
          _analyticsData = Map<String, dynamic>.from(data);
          _error = null;
        } else {
          _error = decoded['message']?.toString() ?? 'Failed to load analytics';
          _analyticsData = null;
        }
      } else {
        _error = 'Failed to load analytics: ${statsResponse.statusCode}';
        _analyticsData = null;
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
    } catch (e) {
      _error = 'Error loading analytics: $e';
      _analyticsData = null;
      DebugLogger.logErrorWithTag('ANALYTICS', 'Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
