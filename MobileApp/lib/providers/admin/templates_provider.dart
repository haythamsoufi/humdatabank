import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../models/shared/template.dart';
import '../../services/api_service.dart';

class TemplatesProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  List<Template> _templates = [];
  bool _isLoading = false;
  String? _error;

  List<Template> get templates => _templates;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadTemplates() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _api.get(
        '/admin/templates',
      );

      if (response.statusCode == 200) {
        // Try to parse as JSON first
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          if (jsonData['success'] == true) {
            final templatesList = jsonData['templates'] as List<dynamic>?;
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
          print('[TEMPLATES] JSON parse failed, trying HTML: $e');
          final html = response.body;
          _templates = _parseTemplatesFromHtml(html);
          _error = null;
        }
      } else {
        _error = 'Failed to load templates: ${response.statusCode}';
        _templates = [];
      }
    } catch (e) {
      _error = 'Error loading templates: $e';
      _templates = [];
      print('[TEMPLATES] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
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

      // Extract template ID from edit link
      final editLinkMatch = RegExp(
        r'/admin/form-builder/edit-template/(\d+)',
        caseSensitive: false,
      ).firstMatch(rowHtml);

      final id = editLinkMatch != null
          ? int.tryParse(editLinkMatch.group(1) ?? '0') ?? index
          : index;

      // Extract created date
      DateTime createdAt = DateTime.now();

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
        '/admin/form-builder/delete-template/$templateId',
        body: {},
      );

      return response.statusCode == 200 || response.statusCode == 302;
    } catch (e) {
      print('[TEMPLATES] Error deleting template: $e');
      return false;
    }
  }

  Future<bool> duplicateTemplate(int templateId) async {
    try {
      final response = await _api.post(
        '/admin/form-builder/duplicate-template/$templateId',
        body: {},
      );

      return response.statusCode == 200 || response.statusCode == 302;
    } catch (e) {
      print('[TEMPLATES] Error duplicating template: $e');
      return false;
    }
  }
}
