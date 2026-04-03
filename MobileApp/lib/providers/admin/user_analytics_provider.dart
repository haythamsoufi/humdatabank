import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';

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
        '/admin/api/dashboard/stats',
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded['status'] == 'success' && decoded['data'] != null) {
          final data = decoded['data'] as Map<String, dynamic>;
          // Map backend field names to expected field names
          _analyticsData = {
            ...data,
            'total_users': data['user_count'],
            'total_submissions': data['public_submission_count'],
          };
          _error = null;
        } else {
          _error = decoded['message'] ?? 'Failed to load analytics';
          _analyticsData = null;
        }
      } else {
        _error = 'Failed to load analytics: ${response.statusCode}';
        _analyticsData = null;
      }
    } catch (e) {
      _error = 'Error loading analytics: $e';
      _analyticsData = null;
      print('[ANALYTICS] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> loadActivityData({String? timeRange}) async {
    try {
      final queryParams = <String, String>{};
      if (timeRange != null && timeRange.isNotEmpty) {
        queryParams['time_range'] = timeRange;
      }

      final response = await _api.get(
        '/admin/api/dashboard/activity',
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded['status'] == 'success' && decoded['data'] != null) {
          if (_analyticsData == null) {
            _analyticsData = {};
          }
          _analyticsData!['activity'] = decoded['data'];
          notifyListeners();
        }
      }
    } catch (e) {
      print('[ANALYTICS] Error loading activity: $e');
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
