import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../config/app_config.dart';
import '../../models/admin/login_log_item.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

/// Loads [GET /api/mobile/v1/admin/analytics/login-logs] (JWT auth, `admin.analytics.view`).
class LoginLogsProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<LoginLogItem> _items = [];
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  int _page = 1;
  int _totalPages = 0;
  int _total = 0;
  int _perPage = 50;

  String? _userEmailFilter;
  String? _eventType;
  String? _ipFilter;
  bool _suspiciousOnly = false;
  String? _dateFrom;
  String? _dateTo;

  List<LoginLogItem> get items => List.unmodifiable(_items);
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  int get page => _page;
  int get totalPages => _totalPages;
  int get total => _total;
  bool get hasMore =>
      _totalPages > 0 && _page < _totalPages;

  String? get userEmailFilter => _userEmailFilter;
  String? get eventType => _eventType;
  String? get ipFilter => _ipFilter;
  bool get suspiciousOnly => _suspiciousOnly;
  String? get dateFrom => _dateFrom;
  String? get dateTo => _dateTo;

  void setFilters({
    String? userEmail,
    String? eventType,
    String? ip,
    required bool suspiciousOnly,
    String? dateFrom,
    String? dateTo,
  }) {
    _userEmailFilter =
        userEmail == null || userEmail.trim().isEmpty ? null : userEmail.trim();
    _eventType =
        eventType == null || eventType.trim().isEmpty ? null : eventType.trim();
    _ipFilter = ip == null || ip.trim().isEmpty ? null : ip.trim();
    _suspiciousOnly = suspiciousOnly;
    _dateFrom = dateFrom;
    _dateTo = dateTo;
  }

  Future<void> refresh() => _fetch(reset: true);

  Future<void> loadMore() async {
    if (!hasMore || _isLoadingMore || _isLoading) return;
    await _fetch(reset: false);
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
    if (_eventType != null && _eventType!.isNotEmpty) {
      queryParams['event_type'] = _eventType!;
    }
    if (_ipFilter != null && _ipFilter!.isNotEmpty) {
      queryParams['ip'] = _ipFilter!;
    }
    if (_suspiciousOnly) {
      queryParams['suspicious_only'] = 'true';
    }
    if (_dateFrom != null && _dateFrom!.isNotEmpty) {
      queryParams['date_from'] = _dateFrom!;
    }
    if (_dateTo != null && _dateTo!.isNotEmpty) {
      queryParams['date_to'] = _dateTo!;
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            AppConfig.mobileLoginLogsEndpoint,
            queryParams: queryParams,
            useCache: false,
          ),
      context: 'Login logs',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load login logs. Please try again.';
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to view login logs (analytics access required).';
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    if (response.statusCode != 200) {
      final err = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Login logs',
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
      final parsed = <LoginLogItem>[];
      for (final e in list) {
        if (e is Map<String, dynamic>) {
          parsed.add(LoginLogItem.fromJson(e));
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
        context: 'Parse login logs',
      );
      _error = err.getUserMessage();
      if (reset) _items = [];
    }

    _isLoading = false;
    _isLoadingMore = false;
    notifyListeners();
  }
}
