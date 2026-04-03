import 'package:flutter/foundation.dart';
import 'package:provider/provider.dart';
import '../../models/shared/notification.dart';
import '../../models/shared/notification_preferences.dart';
import '../../services/notification_service.dart';
import '../../services/api_service.dart';
import '../../services/auth_error_handler.dart';
import '../../services/error_handler.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/debug_logger.dart';

class NotificationProvider with ChangeNotifier {
  final NotificationService _notificationService = NotificationService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Notification> _notifications = [];
  int _unreadCount = 0;
  bool _isLoading = false;
  String? _error;

  NotificationPreferences? _preferences;
  bool _isLoadingPreferences = false;
  String? _preferencesError;

  List<Notification> get notifications => _notifications;
  int get unreadCount => _unreadCount;
  bool get isLoading => _isLoading;
  String? get error => _error;
  NotificationPreferences? get preferences => _preferences;
  bool get isLoadingPreferences => _isLoadingPreferences;
  String? get preferencesError => _preferencesError;

  Future<void> loadNotifications() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      // Language will be automatically retrieved from storage by notification service
      _notifications = await _notificationService.getNotifications();
      _unreadCount = _notifications.where((n) => !n.isRead).length;
      _error = null;
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Notifications',
      );
      _error = error.getUserMessage();
      _errorHandler.logError(error);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> refreshUnreadCount({AuthProvider? authProvider}) async {
    final authErrorHandler = AuthErrorHandler();

    try {
      final count = await authErrorHandler.executeWithAuthHandling<int>(
        apiCall: () => _notificationService.getUnreadCount(),
        context: 'Notifications',
        defaultValue: 0,
        silent: true, // Silent for background refresh
      );

      if (count != null) {
        _unreadCount = count;
        notifyListeners();
      }
    } catch (e) {
      // Silently handle timeout/connection errors for unread count
      // Don't show error to user as this is a background refresh
      final errorMsg = e.toString();
      if (errorMsg.contains('timeout') || errorMsg.contains('Timeout')) {
        DebugLogger.logWarn('NOTIFICATIONS',
            'Timeout refreshing unread count - will retry later');
      } else if (errorMsg.contains('Failed host lookup') ||
          errorMsg.contains('Connection refused')) {
        DebugLogger.logWarn(
            'NOTIFICATIONS', 'Cannot connect to server - will retry later');
      } else if (!authErrorHandler.isAuthenticationError(e)) {
        // Only log non-auth errors
        DebugLogger.logWarn(
            'NOTIFICATIONS', 'Error refreshing unread count: $e');
      }
      // Keep previous count on error instead of resetting to 0
      // _unreadCount = 0; // Commented out to preserve last known count
      notifyListeners();
    }
  }

  Future<bool> markAsRead(List<int> notificationIds) async {
    try {
      _error = null;
      final success = await _notificationService.markAsRead(notificationIds);
      if (success) {
        for (var id in notificationIds) {
          final index = _notifications.indexWhere((n) => n.id == id);
          if (index != -1) {
            _notifications[index] = Notification(
              id: _notifications[index].id,
              title: _notifications[index].title,
              message: _notifications[index].message,
              type: _notifications[index].type,
              isRead: true,
              createdAt: _notifications[index].createdAt,
              metadata: _notifications[index].metadata,
              relatedUrl: _notifications[index].relatedUrl,
              priority: _notifications[index].priority,
              notificationTypeLabel: _notifications[index].notificationTypeLabel,
              entityName: _notifications[index].entityName,
              entityType: _notifications[index].entityType,
            );
          }
        }
        _unreadCount = _notifications.where((n) => !n.isRead).length;
        notifyListeners();
      }
      return success;
    } on AuthenticationException catch (e) {
      _error = 'Session expired. Please log in again.';
      notifyListeners();
      return false;
    } catch (e) {
      _error = 'Error: ${e.toString()}';
      notifyListeners();
      return false;
    }
  }

  Future<bool> markAsUnread(List<int> notificationIds) async {
    try {
      _error = null;
      final success = await _notificationService.markAsUnread(notificationIds);
      if (success) {
        for (var id in notificationIds) {
          final index = _notifications.indexWhere((n) => n.id == id);
          if (index != -1) {
            _notifications[index] = Notification(
              id: _notifications[index].id,
              title: _notifications[index].title,
              message: _notifications[index].message,
              type: _notifications[index].type,
              isRead: false,
              createdAt: _notifications[index].createdAt,
              metadata: _notifications[index].metadata,
              relatedUrl: _notifications[index].relatedUrl,
              priority: _notifications[index].priority,
              notificationTypeLabel: _notifications[index].notificationTypeLabel,
              entityName: _notifications[index].entityName,
              entityType: _notifications[index].entityType,
            );
          }
        }
        _unreadCount = _notifications.where((n) => !n.isRead).length;
        notifyListeners();
      }
      return success;
    } on AuthenticationException catch (e) {
      _error = 'Session expired. Please log in again.';
      notifyListeners();
      return false;
    } catch (e) {
      _error = 'Error: ${e.toString()}';
      notifyListeners();
      return false;
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  Future<void> loadPreferences() async {
    _isLoadingPreferences = true;
    _preferencesError = null;
    notifyListeners();

    try {
      _preferences = await _notificationService.getPreferences();
      if (_preferences == null) {
        // Create default preferences if none exist
        _preferences = NotificationPreferences(
          emailNotifications: true,
          notificationTypesEnabled: [],
          notificationFrequency: 'instant',
          digestDay: null,
          digestTime: null,
          soundEnabled: false,
          pushNotifications: true,
          pushNotificationTypesEnabled: [],
        );
      }
    } catch (e) {
      _preferencesError = e.toString();
    } finally {
      _isLoadingPreferences = false;
      notifyListeners();
    }
  }

  Future<bool> updatePreferences(NotificationPreferences preferences) async {
    _preferencesError = null;
    notifyListeners();
    try {
      final success = await _notificationService.updatePreferences(preferences);
      if (success) {
        _preferences = preferences;
        notifyListeners();
      }
      return success;
    } catch (e) {
      _preferencesError = e.toString();
      notifyListeners();
      return false;
    }
  }

  void clearPreferencesError() {
    _preferencesError = null;
    notifyListeners();
  }
}
