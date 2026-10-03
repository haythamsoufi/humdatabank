import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../../config/app_config.dart';
import '../../models/shared/template.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class TemplatesProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Template> _templates = [];
  bool _isLoading = false;
  String? _error;

  List<Template> get templates => _templates;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadTemplates() async {
    await runAsyncOperation(() async {
      if (shouldDeferRemoteFetch) {
        _isLoading = false;
        notifyListeners();
        return;
      }
      _isLoading = true;
      _error = null;
      notifyListeners();

      final collected = <Template>[];
      var page = 1;
      var totalPages = 1;
      http.Response? response;
      try {
        while (page <= totalPages && page <= 25) {
          response = await _errorHandler.executeWithErrorHandling<http.Response>(
            apiCall: () => _api.get(
              AppConfig.mobileTemplatesEndpoint,
              queryParams: {'page': '$page', 'per_page': '200'},
            ),
            context: 'Load Templates',
            defaultValue: null,
            maxRetries: 1,
            handleAuthErrors: true,
          );
          if (response == null || response.statusCode != 200) break;
          final jsonData = decodeJsonObject(response.body);
          if (jsonData['success'] != true) break;
          collected.addAll(mobileDataMaps(jsonData).map(Template.fromJson));
          totalPages = mobileTotalPages(jsonData);
          page += 1;
        }
      } catch (e, stackTrace) {
        final error = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse Templates',
        );
        _error = error.getUserMessage();
        _templates = collected;
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (response == null && collected.isEmpty) {
        _error = 'Unable to load templates. Please try again.';
        _templates = [];
        _isLoading = false;
        notifyListeners();
        return;
      }

      if (collected.isNotEmpty || (response != null && response.statusCode == 200)) {
        if (collected.isNotEmpty ||
            (response != null && response.body.trimLeft().startsWith('{'))) {
          _templates = collected;
          _error = null;
        } else if (response != null) {
          _templates = _parseTemplatesFromHtml(response.body);
          _error = null;
        }
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response?.statusCode ?? 'unknown'}'),
          response: response,
          context: 'Load Templates',
        );
        _error = error.getUserMessage();
        _templates = [];
      }

      _isLoading = false;
      notifyListeners();
    });
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
