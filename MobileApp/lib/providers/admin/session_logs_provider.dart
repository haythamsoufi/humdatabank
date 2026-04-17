import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../config/app_config.dart';
import '../../models/admin/session_log_item.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

/// Loads [GET /api/mobile/v1/admin/analytics/session-logs] and force-logout via
/// [POST /api/mobile/v1/admin/analytics/sessions/<session_id>/end].
class SessionLogsProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<SessionLogItem> _items = [];
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  int _page = 1;
  int _totalPages = 0;
  int _total = 0;
  int _perPage = 50;

  String? _userEmailFilter;
  bool _activeOnly = false;
  int? _minDurationMinutes;

  List<SessionLogItem> get items => List.unmodifiable(_items);
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  int get page => _page;
  int get totalPages => _totalPages;
  int get total => _total;
  bool get hasMore => _totalPages > 0 && _page < _totalPages;

  String? get userEmailFilter => _userEmailFilter;
  bool get activeOnly => _activeOnly;
  int? get minDurationMinutes => _minDurationMinutes;

  void setFilters({
    String? userEmail,
    required bool activeOnly,
    int? minDurationMinutes,
  }) {
    _userEmailFilter =
        userEmail == null || userEmail.trim().isEmpty ? null : userEmail.trim();
    _activeOnly = activeOnly;
    _minDurationMinutes = minDurationMinutes;
  }

  Future<void> refresh() => _fetch(reset: true);

  Future<void> loadMore() async {
    if (!hasMore || _isLoadingMore || _isLoading) return;
    await _fetch(reset: false);
  }

  /// Returns true if the signed-in session was ended (caller should log out).
  Future<bool> forceLogoutSession(String sessionId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(
            '${AppConfig.mobileEndSessionEndpoint}/$sessionId/end',
            body: {},
          ),
      context: 'End session',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to end session. Please try again.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to end sessions (analytics access required).';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 404 || response.statusCode == 400) {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'End session',
      );
      _error = err.getUserMessage();
      notifyListeners();
      return false;
    }

    if (response.statusCode != 200) {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'End session',
      );
      _error = err.getUserMessage();
      notifyListeners();
      return false;
    }

    var loggedOutSelf = false;
    try {
      final decoded = jsonDecode(response.body);
      if (decoded is Map<String, dynamic>) {
        loggedOutSelf = decoded['logged_out_self'] == true;
      }
    } catch (_) {}

    _error = null;
    if (!loggedOutSelf) {
      await refresh();
    } else {
      notifyListeners();
    }
    return loggedOutSelf;
  }

  Future<void> _fetch({required bool reset}) async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }
    if (reset) {
      _isLoading = true;
      _page = 1;
      _items = [];
    } else {
      _isLoadingMore = true;
    }
    _error = null;
    notifyListeners();

    final nextPage = reset ? 1 : _page + 1;
    final queryParams = <String, String>{
      'page': '$nextPage',
      'per_page': '$_perPage',
    };
    if (_userEmailFilter != null && _userEmailFilter!.isNotEmpty) {
      queryParams['user'] = _userEmailFilter!;
    }
    if (_activeOnly) {
      queryParams['active_only'] = 'true';
    }
    if (_minDurationMinutes != null && _minDurationMinutes! > 0) {
      queryParams['min_duration'] = '${_minDurationMinutes!}';
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            AppConfig.mobileSessionLogsEndpoint,
            queryParams: queryParams,
            useCache: false,
          ),
      context: 'Session logs',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load session logs. Please try again.';
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to view session logs (analytics access required).';
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    if (response.statusCode != 200) {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Session logs',
      );
      _error = err.getUserMessage();
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    try {
      final decoded = jsonDecode(response.body);
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('Invalid JSON');
      }
      final rawData = decoded['data'];
      final meta = decoded['meta'] is Map<String, dynamic>
          ? decoded['meta'] as Map<String, dynamic>
          : <String, dynamic>{};
      final List<dynamic> list;
      if (rawData is List) {
        list = rawData;
      } else if (rawData is Map<String, dynamic> && rawData['items'] is List) {
        list = rawData['items'] as List;
      } else {
        list = [];
      }
      final parsed = <SessionLogItem>[];
      for (final e in list) {
        if (e is Map<String, dynamic>) {
          parsed.add(SessionLogItem.fromJson(e));
        }
      }
      _total = meta['total'] as int? ?? int.tryParse('${rawData is Map ? rawData['total'] : 0}') ?? 0;
      _page = meta['page'] as int? ?? nextPage;
      _perPage = meta['per_page'] as int? ?? 50;
      _totalPages = meta['total_pages'] as int? ?? meta['pages'] as int? ?? 0;

      if (reset) {
        _items = parsed;
      } else {
        _items = [..._items, ...parsed];
      }
      _error = null;
    } catch (e, stackTrace) {
      final err = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Parse session logs',
      );
      _error = err.getUserMessage();
      if (reset) _items = [];
    }

    _isLoading = false;
    _isLoadingMore = false;
    notifyListeners();
  }
}
