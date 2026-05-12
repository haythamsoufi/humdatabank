import 'package:flutter/foundation.dart';

import '../../models/shared/notification.dart';
import '../../models/shared/notification_preferences.dart';
import '../../services/notification_service.dart';
import '../../services/api_service.dart';
import '../../services/auth_error_handler.dart';
import '../../services/error_handler.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';

class NotificationProvider with ChangeNotifier {
  final NotificationService _notificationService = NotificationService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Notification> _notifications = [];
  int _unreadCount = 0;
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  String? _loadMoreError;

  /// Last page number successfully loaded (1-based). Reset on full refresh.
  int _lastLoadedPage = 0;
  int _notificationsTotal = 0;
  int _perPage = 20;

  NotificationPreferences? _preferences;
  bool _isLoadingPreferences = false;
  String? _preferencesError;

  /// Server-backed list filters (see mobile `/notifications` query params).
  bool _filterUnreadOnly = false;
  String? _filterNotificationType;
  String? _filterPriority;

  /// Client-side filter: actor user id from loaded rows only.
  int? _filterActorUserId;

  List<Notification> get notifications => _notifications;

  bool get filterUnreadOnly => _filterUnreadOnly;

  String? get filterNotificationType => _filterNotificationType;

  String? get filterPriority => _filterPriority;

  int? get filterActorUserId => _filterActorUserId;

  bool get hasActiveNotificationFilters =>
      _filterUnreadOnly ||
      (_filterNotificationType != null &&
          _filterNotificationType!.isNotEmpty) ||
      (_filterPriority != null && _filterPriority!.isNotEmpty) ||
      _filterActorUserId != null;

  /// Rows after optional client-side actor filter (server filters apply to [_notifications]).
  List<Notification> get displayedNotifications {
    if (_filterActorUserId == null) {
      return List<Notification>.from(_notifications);
    }
    return _notifications
        .where((n) => n.actor != null && n.actor!.id == _filterActorUserId)
        .toList();
  }

  /// Distinct non-empty actors from the currently loaded list (for the From filter).
  List<NotificationActor> get distinctActorsForFilter {
    final seen = <int>{};
    final out = <NotificationActor>[];
    for (final n in _notifications) {
      final a = n.actor;
      if (a != null && a.id != 0 && seen.add(a.id)) {
        out.add(a);
      }
    }
    out.sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase()));
    return out;
  }

  /// Updates list filters and reloads page 1 from the API.
  Future<void> applyListFilters({
    required bool unreadOnly,
    String? notificationType,
    String? priority,
    int? actorUserId,
  }) async {
    _filterUnreadOnly = unreadOnly;
    _filterNotificationType =
        (notificationType != null && notificationType.isNotEmpty)
            ? notificationType
            : null;
    _filterPriority =
        (priority != null && priority.isNotEmpty) ? priority : null;
    _filterActorUserId = actorUserId;
    notifyListeners();
    await loadNotifications();
  }

  Future<void> clearListFilters() async {
    _filterUnreadOnly = false;
    _filterNotificationType = null;
    _filterPriority = null;
    _filterActorUserId = null;
    notifyListeners();
    await loadNotifications();
  }
  int get unreadCount => _unreadCount;
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  String? get loadMoreError => _loadMoreError;

  bool get hasMoreNotifications =>
      _lastLoadedPage > 0 && _lastLoadedPage * _perPage < _notificationsTotal;
  NotificationPreferences? get preferences => _preferences;
  bool get isLoadingPreferences => _isLoadingPreferences;
  String? get preferencesError => _preferencesError;

  Future<void> loadNotifications() async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    _loadMoreError = null;
    _lastLoadedPage = 0;
    notifyListeners();

    try {
      DebugLogger.logNotifications('loadNotifications() starting');
      final result = await _notificationService.fetchNotificationsPage(
        page: 1,
        perPage: _perPage,
        unreadOnly: _filterUnreadOnly,
        notificationType: _filterNotificationType,
        priority: _filterPriority,
      );
      if (result == null) {
        _notifications = [];
        _notificationsTotal = 0;
        _lastLoadedPage = 0;
        _error = 'Could not load notifications. Pull to refresh to try again.';
      } else {
        _notifications = result.notifications;
        _notificationsTotal = result.total;
        _perPage = result.perPage;
        _lastLoadedPage = result.page;
        DebugLogger.logNotifications(
          'loadNotifications() done: ${_notifications.length} items on page '
          '$_lastLoadedPage, total=$_notificationsTotal',
        );
        // Badge must reflect server-wide unread total, not unread rows in this page.
        await refreshUnreadCount();
        _error = null;
      }
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

  /// Appends the next page from the API. No-op if nothing more or a load is in flight.
  Future<void> loadMoreNotifications() async {
    if (shouldDeferRemoteFetch ||
        !hasMoreNotifications ||
        _isLoadingMore ||
        _isLoading) {
      return;
    }
    _isLoadingMore = true;
    _loadMoreError = null;
    notifyListeners();

    try {
      final nextPage = _lastLoadedPage + 1;
      final result = await _notificationService.fetchNotificationsPage(
        page: nextPage,
        perPage: _perPage,
        unreadOnly: _filterUnreadOnly,
        notificationType: _filterNotificationType,
        priority: _filterPriority,
      );
      if (result == null) {
        _loadMoreError =
            'Could not load more notifications. Check your connection and try again.';
      } else {
        _notificationsTotal = result.total;
        _perPage = result.perPage;
        _lastLoadedPage = result.page;
        final existing = _notifications.map((n) => n.id).toSet();
        for (final n in result.notifications) {
          if (!existing.contains(n.id)) {
            _notifications.add(n);
            existing.add(n.id);
          }
        }
      }
    } catch (e, stackTrace) {
      final err = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load More Notifications',
      );
      _loadMoreError = err.getUserMessage();
      _errorHandler.logError(err);
    } finally {
      _isLoadingMore = false;
      notifyListeners();
    }
  }

  Future<void> refreshUnreadCount({AuthProvider? authProvider}) async {
    if (shouldDeferRemoteFetch) {
      notifyListeners();
      return;
    }
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
        for (final id in notificationIds) {
          final index = _notifications.indexWhere((n) => n.id == id);
          if (index != -1) {
            _notifications[index] =
                _notifications[index].copyWith(isRead: true);
          }
        }
        notifyListeners();
        await refreshUnreadCount();
      }
      return success;
    } on AuthenticationException {
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
        for (final id in notificationIds) {
          final index = _notifications.indexWhere((n) => n.id == id);
          if (index != -1) {
            _notifications[index] =
                _notifications[index].copyWith(isRead: false);
          }
        }
        notifyListeners();
        await refreshUnreadCount();
      }
      return success;
    } on AuthenticationException {
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
      _preferences ??= NotificationPreferences(
          emailNotifications: true,
          notificationTypesEnabled: [],
          notificationFrequency: 'instant',
          digestDay: null,
          digestTime: null,
          soundEnabled: false,
          pushNotifications: true,
          pushNotificationTypesEnabled: [],
        );
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
