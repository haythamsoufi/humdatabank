import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';

class UserAnalyticsProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  Map<String, dynamic>? _analyticsData;
  bool _isLoading = false;
  String? _error;

  Map<String, dynamic>? get analyticsData => _analyticsData;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadAnalytics({
    String? timeRange,
    String? metricFilter,
  }) async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{};
      if (timeRange != null && timeRange.isNotEmpty) {
        queryParams['time_range'] = timeRange;
      }
      if (metricFilter != null && metricFilter.isNotEmpty) {
        queryParams['metric'] = metricFilter;
      }

      final response = await _api.get(
        AppConfig.mobileDashboardStatsEndpoint,
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        // Match AdminDashboardProvider: Flask json_ok(status=..., data={...}) merges
        // stats at the top level — there is often no nested `data` key.
        final isSuccess = decoded['status'] == 'success' ||
            decoded['success'] == true;
        if (isSuccess) {
          final nested = decoded['data'];
          final Map<String, dynamic> data = Map<String, dynamic>.from(
            nested is Map ? nested as Map<String, dynamic> : decoded,
          );
          if (nested is! Map) {
            data.remove('success');
            data.remove('status');
            data.remove('message');
          }
          _analyticsData = {
            ...data,
            'total_users': data['user_count'],
            'total_submissions': data['public_submission_count'],
          };
          _error = null;
        } else {
          _error = decoded['message']?.toString() ?? 'Failed to load analytics';
          _analyticsData = null;
        }
      } else {
        _error = 'Failed to load analytics: ${response.statusCode}';
        _analyticsData = null;
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

  Future<void> loadActivityData({String? timeRange}) async {
    if (shouldDeferRemoteFetch) {
      return;
    }
    try {
      final queryParams = <String, String>{};
      if (timeRange != null && timeRange.isNotEmpty) {
        queryParams['time_range'] = timeRange;
      }

      final response = await _api.get(
        AppConfig.mobileDashboardActivityEndpoint,
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        final isSuccess = decoded['status'] == 'success' ||
            decoded['success'] == true;
        if (isSuccess) {
          final nested = decoded['data'];
          final Map<String, dynamic> activityPayload = Map<String, dynamic>.from(
            nested is Map ? nested as Map<String, dynamic> : decoded,
          );
          if (nested is! Map) {
            activityPayload.remove('success');
            activityPayload.remove('status');
            activityPayload.remove('message');
          }
          _analyticsData ??= {};
          _analyticsData!['activity'] = activityPayload;
          notifyListeners();
        }
      }
    } catch (e) {
      DebugLogger.logErrorWithTag('ANALYTICS', 'Error loading activity: $e');
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
