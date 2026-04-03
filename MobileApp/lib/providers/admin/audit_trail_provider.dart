import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';

class AuditTrailProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  List<Map<String, dynamic>> _auditLogs = [];
  bool _isLoading = false;
  String? _error;

  List<Map<String, dynamic>> get auditLogs => _auditLogs;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadAuditLogs({
    String? search,
    String? actionFilter,
    String? userFilter,
    DateTime? dateFrom,
    DateTime? dateTo,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{};
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (actionFilter != null && actionFilter.isNotEmpty) {
        queryParams['action'] = actionFilter;
      }
      if (userFilter != null && userFilter.isNotEmpty) {
        queryParams['user_id'] = userFilter;
      }
      if (dateFrom != null) {
        queryParams['date_from'] = dateFrom.toIso8601String().split('T')[0];
      }
      if (dateTo != null) {
        queryParams['date_to'] = dateTo.toIso8601String().split('T')[0];
      }

      // Use the HTML route and parse it
      try {
        final response = await _api.get(
          '/admin/analytics/audit-trail',
          queryParams: queryParams.isNotEmpty ? queryParams : null,
        );

        if (response.statusCode == 200) {
          // Try to parse as JSON first
          try {
            final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
            if (jsonData['success'] == true) {
              final entriesList = jsonData['entries'] as List<dynamic>?;
              if (entriesList != null) {
                _auditLogs = entriesList
                    .map((entry) => entry as Map<String, dynamic>)
                    .toList();
              } else {
                _auditLogs = [];
              }
              _error = null;
            } else {
              // Fallback to HTML parsing
              _auditLogs = _parseAuditLogsFromHtml(response.body);
              _error = null;
            }
          } catch (e) {
            // If JSON parsing fails, try HTML parsing as fallback
            print('[AUDIT] JSON parse failed, trying HTML: $e');
            _auditLogs = _parseAuditLogsFromHtml(response.body);
            _error = null;
          }
        } else {
          _error = 'Failed to load audit logs: ${response.statusCode}';
          _auditLogs = [];
        }
      } catch (e) {
        print('[AUDIT] Error parsing: $e');
        _auditLogs = [];
        _error = 'Error loading audit logs: $e';
      }
    } catch (e) {
      _error = 'Error loading audit logs: $e';
      _auditLogs = [];
      print('[AUDIT] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
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
          'description': description,
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
