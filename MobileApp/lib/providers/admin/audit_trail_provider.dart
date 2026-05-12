import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../services/audit_trail_home_widget_sync.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class AuditTrailProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();

  List<Map<String, dynamic>> _auditLogs = [];
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  int _totalCount = 0;
  int _perPage = 50;
  int _lastLoadedPage = 0;

  List<Map<String, dynamic>> get auditLogs => _auditLogs;
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  int get totalCount => _totalCount;
  bool get hasMore => _auditLogs.length < _totalCount;

  Future<void> loadAuditLogs({
    String? userEmailContains,
    String? activityTypeFilter,
    DateTime? dateFrom,
    DateTime? dateTo,
    bool append = false,
  }) async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    final nextPage = append ? _lastLoadedPage + 1 : 1;
    if (append) {
      if (!hasMore || _isLoadingMore) return;
      _isLoadingMore = true;
    } else {
      _lastLoadedPage = 0;
      _isLoading = true;
    }
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{
        'page': '$nextPage',
        'per_page': '$_perPage',
      };
      if (userEmailContains != null && userEmailContains.isNotEmpty) {
        queryParams['user'] = userEmailContains;
      }
      if (activityTypeFilter != null && activityTypeFilter.isNotEmpty) {
        queryParams['activity_type'] = activityTypeFilter;
      }
      if (dateFrom != null) {
        queryParams['date_from'] = dateFrom.toIso8601String().split('T')[0];
      }
      if (dateTo != null) {
        queryParams['date_to'] = dateTo.toIso8601String().split('T')[0];
      }

      try {
        final response = await _api.get(
          AppConfig.mobileAuditTrailEndpoint,
          queryParams: queryParams,
          useCache: false,
        );

        if (response.statusCode == 200) {
          try {
            final jsonData = jsonDecode(response.body);
            if (jsonData is Map<String, dynamic> &&
                mobileResponseIsSuccess(jsonData)) {
              final entriesList = mobileDataListLoose(jsonData);
              final newRows = entriesList
                  .whereType<Map<String, dynamic>>()
                  .map(_normalizeAuditRow)
                  .toList();

              final meta = jsonData['meta'];
              if (meta is Map<String, dynamic>) {
                _totalCount = _readPositiveInt(meta['total']) ?? _totalCount;
                _perPage = _readPositiveInt(meta['per_page']) ?? _perPage;
                _lastLoadedPage =
                    _readPositiveInt(meta['page']) ?? nextPage;
              } else if (!append) {
                _totalCount = newRows.length;
                _lastLoadedPage = nextPage;
              }

              if (append) {
                if (newRows.isEmpty) {
                  _totalCount = _auditLogs.length;
                } else {
                  _auditLogs = [..._auditLogs, ...newRows];
                }
              } else {
                _auditLogs = newRows;
              }
              _error = null;
              if (!append) {
                await syncAuditTrailToHomeWidget(_auditLogs);
              }
            } else {
              _applyHtmlFallback(response.body, append: append);
            }
          } catch (e) {
            DebugLogger.logWarn('AUDIT', 'JSON parse failed, trying HTML: $e');
            _applyHtmlFallback(response.body, append: append);
          }
        } else {
          _error = 'Failed to load audit logs: ${response.statusCode}';
          if (!append) _auditLogs = [];
        }
      } catch (e) {
        DebugLogger.logErrorWithTag('AUDIT', 'Error parsing: $e');
        if (!append) _auditLogs = [];
        _error = 'Error loading audit logs: $e';
      }
    } catch (e) {
      _error = 'Error loading audit logs: $e';
      if (!append) _auditLogs = [];
      DebugLogger.logErrorWithTag('AUDIT', 'Error: $e');
    } finally {
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
    }
  }

  Future<void> loadMoreAuditLogs({
    String? userEmailContains,
    String? activityTypeFilter,
    DateTime? dateFrom,
    DateTime? dateTo,
  }) async {
    await loadAuditLogs(
      userEmailContains: userEmailContains,
      activityTypeFilter: activityTypeFilter,
      dateFrom: dateFrom,
      dateTo: dateTo,
      append: true,
    );
  }

  int? _readPositiveInt(Object? v) {
    if (v is int) return v;
    if (v is double) return v.round();
    if (v is String) return int.tryParse(v);
    return null;
  }

  void _applyHtmlFallback(String body, {required bool append}) {
    final parsed = _parseAuditLogsFromHtml(body);
    if (append) {
      _auditLogs = [..._auditLogs, ...parsed];
    } else {
      _auditLogs = parsed;
      _totalCount = parsed.length;
    }
    _error = null;
    if (!append) {
      syncAuditTrailToHomeWidget(_auditLogs);
    }
  }

  /// Align legacy HTML rows and mobile API rows for the UI / home widget.
  Map<String, dynamic> _normalizeAuditRow(Map<String, dynamic> raw) {
    final activityType =
        (raw['activity_type'] ?? raw['action'] ?? '').toString();
    final userName = raw['user_name']?.toString();
    final userEmail = raw['user_email']?.toString();
    final legacyUser = raw['user']?.toString();
    return {
      ...raw,
      'activity_type': activityType.isEmpty ? null : activityType,
      'user_display': userName ?? userEmail ?? legacyUser,
      'user_subtitle': userName != null &&
              userEmail != null &&
              userName.isNotEmpty &&
              userEmail.isNotEmpty &&
              userName != userEmail
          ? userEmail
          : (userName != null && userEmail == null ? null : userEmail),
    };
  }

  List<Map<String, dynamic>> _parseAuditLogsFromHtml(String html) {
    final logs = <Map<String, dynamic>>[];

    // Parse HTML table rows
    final rowPattern = RegExp(
      r'<tr[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(html);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Skip header rows
      if (rowHtml.contains('<th') || rowHtml.contains('thead')) {
        continue;
      }

      // Extract cells
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.length >= 4) {
        final timestamp = _extractText(cells[0].group(1) ?? '');
        final user = _extractText(cells[1].group(1) ?? '');
        final action = _extractText(cells[2].group(1) ?? '');
        final description = _extractText(cells[3].group(1) ?? '');

        logs.add({
          'id': index++,
          'timestamp': timestamp,
          'user': user,
          'action': action,
          'activity_type': action.isNotEmpty ? action : null,
          'description': description,
          'user_display': user,
        });
      }
    }

    return logs;
  }

  String _extractText(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
