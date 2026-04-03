import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';

class TranslationManagementProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  List<Map<String, dynamic>> _translations = [];
  bool _isLoading = false;
  String? _error;

  List<Map<String, dynamic>> get translations => _translations;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadTranslations({
    String? search,
    String? languageFilter,
    String? statusFilter,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{};
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (languageFilter != null && languageFilter.isNotEmpty) {
        queryParams['language'] = languageFilter;
      }
      if (statusFilter != null && statusFilter.isNotEmpty) {
        queryParams['status'] = statusFilter;
      }

      final response = await _api.get(
        '/admin/translations/manage',
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        // Try to parse as JSON first
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          if (jsonData['success'] == true) {
            final translationsList = jsonData['translations'] as List<dynamic>?;
            if (translationsList != null) {
              _translations = translationsList
                  .map((t) => t as Map<String, dynamic>)
                  .toList();
            } else {
              _translations = [];
            }
            _error = null;
          } else {
            // Fallback to HTML parsing
            _translations = _parseTranslationsFromHtml(response.body);
            _error = null;
          }
        } catch (e) {
          // If JSON parsing fails, try HTML parsing as fallback
          print('[TRANSLATIONS] JSON parse failed, trying HTML: $e');
          _translations = _parseTranslationsFromHtml(response.body);
          _error = null;
        }
      } else {
        _error = 'Failed to load translations: ${response.statusCode}';
        _translations = [];
      }
    } catch (e) {
      _error = 'Error loading translations: $e';
      _translations = [];
      print('[TRANSLATIONS] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> updateTranslation(
      int translationId, Map<String, dynamic> data) async {
    try {
      final response = await _api.post(
        '/admin/api/translations/$translationId',
        body: data,
      );
      if (response.statusCode == 200) {
        await loadTranslations();
        return true;
      } else {
        final decoded = jsonDecode(response.body);
        _error = decoded['message'] ?? 'Failed to update translation';
        notifyListeners();
        return false;
      }
    } catch (e) {
      _error = 'Error updating translation: $e';
      notifyListeners();
      return false;
    }
  }

  List<Map<String, dynamic>> _parseTranslationsFromHtml(String html) {
    final translations = <Map<String, dynamic>>[];

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

      if (cells.length >= 2) {
        final key = _extractText(cells[0].group(1) ?? '');
        final language =
            _extractText(cells.length > 1 ? cells[1].group(1) ?? '' : '');
        final value =
            cells.length > 2 ? _extractText(cells[2].group(1) ?? '') : '';

        translations.add({
          'id': index++,
          'key': key,
          'language': language,
          'value': value,
        });
      }
    }

    return translations;
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
