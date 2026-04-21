import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import '../../config/app_config.dart';
import '../../models/shared/template.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class TemplatesProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Template> _templates = [];
  bool _isLoading = false;
  String? _error;

  List<Template> get templates => _templates;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadTemplates() async {
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
      apiCall: () => _api.get(AppConfig.mobileTemplatesEndpoint),
      context: 'Load Templates',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load templates. Please try again.';
      _templates = [];
      _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        // Try to parse as JSON first
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          if (jsonData['success'] == true) {
            final rawData = jsonData['data'];
            final List<dynamic>? templatesList = rawData is List
                ? rawData
                : rawData is Map ? (rawData['templates'] as List<dynamic>?) : (jsonData['templates'] as List<dynamic>?);
            if (templatesList != null) {
              _templates = templatesList
                  .map((json) => Template.fromJson(json as Map<String, dynamic>))
                  .toList();
            } else {
              _templates = [];
            }
            _error = null;
          } else {
            // Fallback to HTML parsing for backward compatibility
            final html = response.body;
            _templates = _parseTemplatesFromHtml(html);
            _error = null;
          }
        } catch (e) {
          // If JSON parsing fails, try HTML parsing as fallback
          DebugLogger.logWarn('TEMPLATES', 'JSON parse failed, trying HTML: $e');
          final html = response.body;
          _templates = _parseTemplatesFromHtml(html);
          _error = null;
        }
      } catch (e, stackTrace) {
        final error = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse Templates',
        );
        _error = error.getUserMessage();
        _templates = [];
      }
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Load Templates',
      );
      _error = error.getUserMessage();
      _templates = [];
    }

    _isLoading = false;
    notifyListeners();
  }

  List<Template> _parseTemplatesFromHtml(String html) {
    final templates = <Template>[];

    // Parse templates from HTML table
    // Pattern: <tr> with template data
    final rowPattern = RegExp(
      r'<tr[^>]*class="[^"]*bg-white[^"]*"[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(html);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Extract template name (from first <td>)
      final nameMatch = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).firstMatch(rowHtml);

      if (nameMatch == null) continue;

      final nameHtml = nameMatch.group(1) ?? '';
      final nameText = nameHtml.replaceAll(RegExp(r'<[^>]+>'), '').trim();

      // Extract other fields
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.length < 2) continue;

      // Best-effort: detect self-report icon anywhere in the row
      final addToSelfReport = rowHtml.contains('fa-check-circle');

      // Extract template ID from edit link (Backoffice: /admin/templates/edit/<id>)
      final editLinkMatch = RegExp(
        r'/admin/templates/edit/(\d+)',
        caseSensitive: false,
      ).firstMatch(rowHtml);

      final id = editLinkMatch != null
          ? int.tryParse(editLinkMatch.group(1) ?? '0') ?? index
          : index;

      // Extract created date
      final DateTime createdAt = DateTime.now();

      templates.add(Template(
        id: id,
        name: nameText,
        addToSelfReport: addToSelfReport,
        createdAt: createdAt,
      ));

      index++;
    }

    return templates;
  }

  Future<bool> deleteTemplate(int templateId, {int? dataCount}) async {
    try {
      final response = await _api.post(
        '${AppConfig.mobileTemplatesEndpoint}/$templateId/delete',
        body: {},
      );

      return response.statusCode == 200 || response.statusCode == 302;
    } catch (e) {
      DebugLogger.logErrorWithTag('TEMPLATES', 'Error deleting template: $e');
      return false;
    }
  }
}
