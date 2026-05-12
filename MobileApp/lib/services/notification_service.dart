import 'dart:convert';
import 'dart:async';
import '../config/app_config.dart';
import '../models/shared/notification.dart';
import '../models/shared/notification_preferences.dart';
import 'api_service.dart';
import 'storage_service.dart';
import 'package:http/http.dart' as http;
import '../utils/debug_logger.dart';
import '../di/service_locator.dart';

/// One page of notifications plus pagination metadata from [mobile_paginated].
class NotificationsFetchResult {
  final List<Notification> notifications;
  final int total;
  final int page;
  final int perPage;

  const NotificationsFetchResult({
    required this.notifications,
    required this.total,
    required this.page,
    required this.perPage,
  });

  bool get hasMore => page * perPage < total;
}

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  final ApiService _api = sl<ApiService>();
  final StorageService _storage = StorageService();

  /// Fetches a single page of notifications (mobile API `page` / `per_page`).
  /// Returns null when the request fails (non-200, network error, or unreadable body).
  Future<NotificationsFetchResult?> fetchNotificationsPage({
    int page = 1,
    int perPage = 20,
    String? language,
    bool unreadOnly = false,
    String? notificationType,
    String? priority,
  }) async {
    try {
      DebugLogger.logNotifications(
          'Fetching notifications from ${AppConfig.notificationsEndpoint} '
          '(page=$page perPage=$perPage unreadOnly=$unreadOnly '
          'type=$notificationType priority=$priority)');

      final queryParams = <String, String>{
        'page': page.toString(),
        'per_page': perPage.toString(),
      };
      if (unreadOnly) {
        queryParams['unread_only'] = 'true';
      }
      if (notificationType != null && notificationType.isNotEmpty) {
        queryParams['type'] = notificationType;
      }
      if (priority != null && priority.isNotEmpty) {
        queryParams['priority'] = priority;
      }

      // Get language from parameter, or from storage if not provided
      String? currentLanguage = language;
      if (currentLanguage == null || currentLanguage.isEmpty) {
        try {
          currentLanguage =
              await _storage.getString(AppConfig.selectedLanguageKey);
        } catch (e) {
          DebugLogger.logNotifications('Could not get language from storage: $e');
        }
      }

      // Add language parameter if available
      if (currentLanguage != null && currentLanguage.isNotEmpty) {
        queryParams['language'] = currentLanguage;
        DebugLogger.logNotifications('Including language parameter: $currentLanguage');
      }

      // Never cache: stale payloads would undo read/unread state after refresh or
      // after loadNotifications() following mark-as-read (ApiService default TTL is 1h).
      final response = await _api.get(
        AppConfig.notificationsEndpoint,
        queryParams: queryParams,
        useCache: false,
      );

      DebugLogger.logNotifications('Response status: ${response.statusCode}');
      DebugLogger.logNotifications(
          'Response body length: ${response.body.length}');

      if (response.statusCode == 200) {
        try {
          final decoded = jsonDecode(response.body);
          DebugLogger.logNotifications(
            'Parsed JSON root type: ${decoded.runtimeType}',
          );

          List<dynamic>? notificationsJson;
          if (decoded is Map<String, dynamic>) {
            final keys = decoded.keys.toList()..sort();
            DebugLogger.logNotifications('Top-level keys: $keys');
            final meta = decoded['meta'];
            if (meta is Map) {
              DebugLogger.logNotifications('meta: $meta');
            }

            // mobile_paginated: { success, data: [ {...}, ... ], meta: { total, page, ... } }
            final data = decoded['data'];
            if (data is List) {
              notificationsJson = data;
              DebugLogger.logNotifications(
                'Using mobile_paginated list: ${data.length} items in data[]',
              );
            } else if (decoded['notifications'] is List) {
              notificationsJson = decoded['notifications'] as List<dynamic>;
              DebugLogger.logNotifications(
                'Using legacy notifications[]: ${notificationsJson.length} items',
              );
            } else {
              DebugLogger.logNotifications(
                'Unexpected shape: success=${decoded['success']}, '
                'data type=${data.runtimeType}, has notifications=${decoded.containsKey('notifications')}',
              );
            }
          }

          int resolvedTotal = 0;
          int resolvedPage = page;
          int resolvedPerPage = perPage;
          if (decoded is Map<String, dynamic>) {
            final meta = decoded['meta'];
            if (meta is Map<String, dynamic>) {
              final t = meta['total'];
              if (t is num) {
                resolvedTotal = t.toInt();
              }
              final p = meta['page'];
              if (p is num) {
                resolvedPage = p.toInt();
              }
              final pp = meta['per_page'];
              if (pp is num) {
                resolvedPerPage = pp.toInt();
              }
            }
          }

          if (notificationsJson == null) {
            DebugLogger.logNotifications(
              'No notification list in response — treating as failure',
            );
            return null;
          }

          if (notificationsJson.isEmpty) {
            DebugLogger.logNotifications('Empty notifications list for this page');
            return NotificationsFetchResult(
              notifications: const [],
              total: resolvedTotal,
              page: resolvedPage,
              perPage: resolvedPerPage,
            );
          }

          final notifications = notificationsJson
              .map((json) =>
                  Notification.fromJson(json as Map<String, dynamic>))
              .toList();
          if (resolvedTotal < notifications.length) {
            resolvedTotal = notifications.length;
          }
          DebugLogger.logNotifications(
            'Successfully built ${notifications.length} Notification models '
            '(total=$resolvedTotal page=$resolvedPage)',
          );
          return NotificationsFetchResult(
            notifications: notifications,
            total: resolvedTotal,
            page: resolvedPage,
            perPage: resolvedPerPage,
          );
        } catch (e) {
          DebugLogger.logNotifications('Error parsing JSON: $e');
          DebugLogger.logNotifications(
              'Response body: ${response.body.substring(0, response.body.length > 500 ? 500 : response.body.length)}');
          return null;
        }
      } else {
        DebugLogger.logNotifications(
            'Non-200 status code: ${response.statusCode}');
        return null;
      }
    } catch (e, stackTrace) {
      DebugLogger.logNotifications('Error fetching notifications: $e');
      DebugLogger.logNotifications('Stack trace: $stackTrace');
      return null;
    }
  }

  // Get unread notifications count
  Future<int> getUnreadCount() async {
    try {
      // Use longer timeout (20 seconds) for unread count as it may query large notification tables
      final response = await _api.get(
        AppConfig.notificationsCountEndpoint,
        timeout: const Duration(seconds: 20),
        useCache: false,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        DebugLogger.logNotifications(
          'unread count raw type: ${decoded.runtimeType}',
        );
        if (decoded is! Map<String, dynamic>) {
          return 0;
        }
        final keys = decoded.keys.toList()..sort();
        DebugLogger.logNotifications('unread count JSON keys: $keys');

        // mobile_ok: { success, data: { unread_count: n } }
        final inner = decoded['data'];
        int? n;
        if (inner is Map<String, dynamic> && inner['unread_count'] != null) {
          n = (inner['unread_count'] as num).toInt();
          DebugLogger.logNotifications('unread_count from data envelope: $n');
        } else if (decoded['unread_count'] != null) {
          n = (decoded['unread_count'] as num).toInt();
          DebugLogger.logNotifications('unread_count from top level: $n');
        } else if (decoded['success'] == true) {
          DebugLogger.logNotifications(
            'success=true but no unread_count found — defaulting to 0',
          );
        }
        return n ?? 0;
      }
      DebugLogger.logNotifications(
        'unread count non-200: ${response.statusCode}',
      );
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
        String errorMessage =
            'Unable to update notifications. Please try again.';
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
        String errorMessage =
            'Unable to update notifications. Please try again.';
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
        String errorMessage =
            'Could not save notification settings. Please try again.';
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
