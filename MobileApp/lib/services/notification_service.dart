import 'dart:convert';
import 'dart:async';
import '../config/app_config.dart';
import '../models/shared/notification.dart';
import '../models/shared/notification_preferences.dart';
import 'api_service.dart';
import 'storage_service.dart';
import 'package:http/http.dart' as http;
import '../utils/debug_logger.dart';

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  final ApiService _api = ApiService();
  final StorageService _storage = StorageService();

  // Get notifications list
  Future<List<Notification>> getNotifications({int limit = 20, String? language}) async {
    try {
      DebugLogger.logNotifications(
          'Fetching notifications from ${AppConfig.notificationsEndpoint}');

      final queryParams = <String, String>{
        'page': '1',
        'per_page': limit.toString(),
      };

      // Get language from parameter, or from storage if not provided
      String? currentLanguage = language;
      if (currentLanguage == null || currentLanguage.isEmpty) {
        try {
          currentLanguage = await _storage.getString('selected_language');
        } catch (e) {
          DebugLogger.logNotifications('Could not get language from storage: $e');
        }
      }

      // Add language parameter if available
      if (currentLanguage != null && currentLanguage.isNotEmpty) {
        queryParams['language'] = currentLanguage;
        DebugLogger.logNotifications('Including language parameter: $currentLanguage');
      }

      final response = await _api.get(
        AppConfig.notificationsEndpoint,
        queryParams: queryParams,
      );

      DebugLogger.logNotifications('Response status: ${response.statusCode}');
      DebugLogger.logNotifications(
          'Response body length: ${response.body.length}');

      if (response.statusCode == 200) {
        try {
          final data = jsonDecode(response.body);
          DebugLogger.logNotifications(
              'Parsed JSON data: success=${data['success']}, notifications count=${data['notifications']?.length ?? 0}');

          if (data['success'] == true && data['notifications'] != null) {
            final List<dynamic> notificationsJson = data['notifications'];
            final notifications = notificationsJson
                .map((json) => Notification.fromJson(json))
                .toList();
            DebugLogger.logNotifications(
                'Successfully parsed ${notifications.length} notifications');
            return notifications;
          } else {
            DebugLogger.logNotifications(
                'API returned success=false or no notifications');
            return [];
          }
        } catch (e) {
          DebugLogger.logNotifications('Error parsing JSON: $e');
          DebugLogger.logNotifications(
              'Response body: ${response.body.substring(0, response.body.length > 500 ? 500 : response.body.length)}');
          return [];
        }
      } else {
        DebugLogger.logNotifications(
            'Non-200 status code: ${response.statusCode}');
        return [];
      }
    } catch (e, stackTrace) {
      DebugLogger.logNotifications('Error fetching notifications: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      return [];
    }
  }

  // Get unread notifications count
  Future<int> getUnreadCount() async {
    try {
      // Use longer timeout (20 seconds) for unread count as it may query large notification tables
      final response = await _api.get(
        AppConfig.notificationsCountEndpoint,
        timeout: const Duration(seconds: 20),
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['success'] == true) {
          return data['unread_count'] ?? 0;
        }
      }
      return 0;
    } on AuthenticationException {
      // Re-throw authentication errors so they can be handled upstream
      rethrow;
    } catch (e) {
      DebugLogger.logError('Error fetching unread count: $e');
      return 0;
    }
  }

  // Mark notifications as read
  Future<bool> markAsRead(List<int> notificationIds) async {
    try {
      DebugLogger.logNotifications(
          'Marking notifications as read: $notificationIds');
      final response = await _api.post(
        AppConfig.markNotificationsReadEndpoint,
        body: {'notification_ids': notificationIds},
      );

      DebugLogger.logNotifications('Response status: ${response.statusCode}');
      DebugLogger.logNotifications('Response body: ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final success = data['success'] == true;
        if (!success) {
          final error = data['error'] ?? 'Unknown error';
          DebugLogger.logNotifications('API returned success=false: $error');
          // Store error for better user feedback
          throw Exception(error);
        }
        return success;
      } else {
        DebugLogger.logNotifications(
            'Non-200 status code: ${response.statusCode}');
        String errorMessage = 'Server error (${response.statusCode})';
        try {
          final data = jsonDecode(response.body);
          errorMessage = data['error'] ?? errorMessage;
          DebugLogger.logNotifications('Error from API: $errorMessage');
        } catch (_) {
          DebugLogger.logNotifications('Could not parse error response');
        }
        throw Exception(errorMessage);
      }
    } on AuthenticationException catch (e) {
      DebugLogger.logNotifications('Authentication error: $e');
      rethrow;
    } catch (e, stackTrace) {
      DebugLogger.logNotifications('Error marking notifications as read: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      return false;
    }
  }

  // Mark notifications as unread
  Future<bool> markAsUnread(List<int> notificationIds) async {
    try {
      DebugLogger.logNotifications(
          'Marking notifications as unread: $notificationIds');
      final response = await _api.post(
        AppConfig.markNotificationsUnreadEndpoint,
        body: {'notification_ids': notificationIds},
      );

      DebugLogger.logNotifications('Response status: ${response.statusCode}');
      DebugLogger.logNotifications('Response body: ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final success = data['success'] == true;
        if (!success) {
          final error = data['error'] ?? 'Unknown error';
          DebugLogger.logNotifications('API returned success=false: $error');
          // Store error for better user feedback
          throw Exception(error);
        }
        return success;
      } else {
        DebugLogger.logNotifications(
            'Non-200 status code: ${response.statusCode}');
        String errorMessage = 'Server error (${response.statusCode})';
        try {
          final data = jsonDecode(response.body);
          errorMessage = data['error'] ?? errorMessage;
          DebugLogger.logNotifications('Error from API: $errorMessage');
        } catch (_) {
          DebugLogger.logNotifications('Could not parse error response');
        }
        throw Exception(errorMessage);
      }
    } on AuthenticationException catch (e) {
      DebugLogger.logNotifications('Authentication error: $e');
      rethrow;
    } catch (e, stackTrace) {
      DebugLogger.logNotifications('Error marking notifications as unread: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      // Rethrow so provider can handle the error
      rethrow;
    }
  }

  // Get notification preferences
  Future<NotificationPreferences?> getPreferences() async {
    try {
      final response =
          await _api.get(AppConfig.notificationPreferencesEndpoint);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['success'] == true && data['preferences'] != null) {
          return NotificationPreferences.fromJson(data['preferences']);
        }
      }
      return null;
    } catch (e) {
      DebugLogger.logError('Error fetching notification preferences: $e');
      return null;
    }
  }

  // Update notification preferences
  Future<bool> updatePreferences(NotificationPreferences preferences) async {
    try {
      final jsonData = preferences.toJson();
      DebugLogger.logNotifications('=== UPDATE PREFERENCES START ===');
      DebugLogger.logNotifications(
          'Endpoint: ${AppConfig.notificationPreferencesEndpoint}');
      DebugLogger.logNotifications('Base URL: ${AppConfig.baseApiUrl}');
      DebugLogger.logNotifications(
          'Full URL: ${AppConfig.baseApiUrl}${AppConfig.notificationPreferencesEndpoint}');
      DebugLogger.logNotifications('Updating preferences with data: $jsonData');

      final response = await _api.post(
        AppConfig.notificationPreferencesEndpoint,
        body: jsonData,
      );

      DebugLogger.logNotifications('=== RESPONSE RECEIVED ===');
      DebugLogger.logNotifications('Status code: ${response.statusCode}');
      DebugLogger.logNotifications('Response body: ${response.body}');
      DebugLogger.logNotifications(
          'Response body length: ${response.body.length}');

      DebugLogger.logNotifications('Response status: ${response.statusCode}');
      DebugLogger.logNotifications('Response headers: ${response.headers}');
      DebugLogger.logNotifications('Response body: ${response.body}');
      DebugLogger.logNotifications(
          'Response body length: ${response.body.length}');
      DebugLogger.logNotifications('=== UPDATE PREFERENCES END ===');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        final success = data['success'] == true;
        if (!success) {
          final error = data['error'] ?? 'Unknown error';
          DebugLogger.logWarn(
              'NOTIFICATIONS', 'API returned success=false: $error');
          DebugLogger.logNotifications('API returned success=false: $error');
          throw Exception(error);
        }
        return success;
      } else {
        DebugLogger.logError('=== ERROR RESPONSE (${response.statusCode}) ===');
        String errorMessage = 'Server error (${response.statusCode})';
        String errorDetails = '';
        try {
          final data = jsonDecode(response.body);
          DebugLogger.logNotifications('Parsed error data: $data');
          errorMessage = data['error'] ?? errorMessage;
          errorDetails = data.toString();
          DebugLogger.logError('Error message: $errorMessage');
          DebugLogger.logError('Full error data: $errorDetails');
          DebugLogger.logNotifications('=== ERROR RESPONSE ===');
          DebugLogger.logNotifications('Error message: $errorMessage');
          DebugLogger.logNotifications('Full error data: $errorDetails');
        } catch (e) {
          DebugLogger.logWarn(
              'NOTIFICATIONS', 'Could not parse error response: $e');
          DebugLogger.logWarn(
              'NOTIFICATIONS', 'Raw response body: ${response.body}');
          DebugLogger.logNotifications('Could not parse error response: $e');
          DebugLogger.logNotifications('Raw response body: ${response.body}');
        }
        throw Exception(
            '$errorMessage${errorDetails.isNotEmpty ? ' - $errorDetails' : ''}');
      }
    } on AuthenticationException catch (e) {
      DebugLogger.logNotifications('Authentication error: $e');
      rethrow;
    } on http.ClientException catch (e, stackTrace) {
      DebugLogger.logNotifications('=== NETWORK ERROR ===');
      DebugLogger.logNotifications('ClientException: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      DebugLogger.logNotifications(
          'This usually means the request could not reach the server');
      DebugLogger.logNotifications(
          'Check: 1) Backoffice is running, 2) Correct URL, 3) Network connectivity');
      rethrow;
    } on TimeoutException catch (e, stackTrace) {
      DebugLogger.logNotifications('=== TIMEOUT ERROR ===');
      DebugLogger.logNotifications('TimeoutException: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      rethrow;
    } catch (e, stackTrace) {
      DebugLogger.logNotifications('=== UNEXPECTED ERROR ===');
      DebugLogger.logNotifications('Error type: ${e.runtimeType}');
      DebugLogger.logNotifications('Error: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      rethrow;
    }
  }
}
