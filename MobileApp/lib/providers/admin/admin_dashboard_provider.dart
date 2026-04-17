import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'dart:async';
import 'package:http/http.dart' as http;
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class AdminDashboardProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  Map<String, dynamic>? _stats;
  bool _isLoading = false;
  String? _error;

  Map<String, dynamic>? get stats => _stats;
  bool get isLoading => _isLoading;
  String? get error => _error;

  // Convenience getters - mapped to API response fields
  int get userCount => _stats?['user_count'] ?? 0;
  int get adminCount =>
      _stats?['admin_count'] ?? 0; // Not provided by API, default to 0
  int get focalPointCount =>
      _stats?['focal_point_count'] ?? 0; // Not provided by API, default to 0
  int get templateCount => _stats?['template_count'] ?? 0;
  int get assignmentCount => _stats?['assignment_count'] ?? 0;
  int get todayLogins => _stats?['today_logins'] ?? 0;
  int get recentLogins => _stats?['recent_logins'] ?? 0;
  int get recentActivities =>
      _stats?['recent_submissions'] ?? 0; // API returns 'recent_submissions'
  int get activeSessions =>
      _stats?['active_users'] ??
      0; // API returns 'active_users', not 'active_sessions'
  int get pendingSubmissions =>
      _stats?['pending_public_submissions_count'] ??
      0; // Not provided by API, default to 0
  int get overdueAssignments =>
      _stats?['overdue_assignments'] ?? 0; // Not provided by API, default to 0
  int get securityAlerts =>
      _stats?['unresolved_security_events'] ??
      0; // Not provided by API, default to 0

  Future<void> loadDashboardStats() async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
        AppConfig.mobileDashboardStatsEndpoint,
        timeout: const Duration(seconds: 30),
      ),
      context: 'Admin Dashboard Stats',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load dashboard stats. Please try again.';
      _stats = null;
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        final decoded = jsonDecode(response.body);
        // Backoffice returns stats flat at the top level (no nested 'data' key).
        // Accept: {"status":"success","user_count":27,...}
        //   or:  {"status":"success","data":{"user_count":27,...}}
        final bool isSuccess =
            decoded['status'] == 'success' || decoded['success'] == true;
        if (isSuccess) {
          final nested = decoded['data'];
          _stats = Map<String, dynamic>.from(
              nested is Map ? nested : decoded);
          _error = null;
        } else {
          final error = _errorHandler.parseError(
            error: Exception(
                decoded['message'] ?? 'Failed to load dashboard stats'),
            response: response,
            context: 'Admin Dashboard Stats',
          );
          _error = error.getUserMessage();
          _stats = null;
        }
      } catch (e, stackTrace) {
        final error = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Admin Dashboard Stats parsing',
        );
        _error = error.getUserMessage();
        _stats = null;
      }
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Admin Dashboard Stats',
      );
      _error = error.getUserMessage();
      _stats = null;
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Sends a push notification to the given user IDs ([POST /api/mobile/v1/admin/notifications/send]).
  /// Returns `null` on success, or a short error message for the UI.
  Future<String?> sendAdminPushNotification({
    required String title,
    required String body,
    required List<int> userIds,
    Map<String, dynamic>? dataPayload,
  }) async {
    final trimmedTitle = title.trim();
    final trimmedBody = body.trim();
    if (trimmedTitle.isEmpty || trimmedBody.isEmpty) {
      return 'Title and message are required.';
    }
    if (userIds.isEmpty) {
      return 'At least one user ID is required.';
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
        AppConfig.mobileAdminSendNotificationEndpoint,
        body: {
          'title': trimmedTitle,
          'body': trimmedBody,
          'user_ids': userIds,
          if (dataPayload != null && dataPayload.isNotEmpty) 'data': dataPayload,
        },
      ),
      context: 'Admin send push notification',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      return 'Unable to send notification. Please try again.';
    }

    if (response.statusCode == 403) {
      return 'You do not have permission to send notifications.';
    }

    if (response.statusCode == 400) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['error'] != null) {
          return decoded['error'].toString();
        }
      } catch (_) {}
      return 'Request could not be completed.';
    }

    if (response.statusCode != 200) {
      return 'Unable to send notification. Please try again.';
    }

    try {
      final decoded = jsonDecode(response.body);
      final ok = decoded is Map &&
          (decoded['success'] == true || decoded['status'] == 'success');
      if (ok) {
        return null;
      }
      if (decoded is Map && decoded['error'] != null) {
        return decoded['error'].toString();
      }
    } catch (_) {}

    return 'Unable to send notification. Please try again.';
  }
}
