import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../models/shared/resource.dart';
import '../../services/api_service.dart';

class ResourcesManagementProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  List<Resource> _resources = [];
  bool _isLoading = false;
  String? _error;

  List<Resource> get resources => _resources;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadResources({
    String? search,
    String? categoryFilter,
    String? languageFilter,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final queryParams = <String, String>{};
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (categoryFilter != null && categoryFilter.isNotEmpty) {
        queryParams['resource_type'] = categoryFilter;
      }
      if (languageFilter != null && languageFilter.isNotEmpty) {
        queryParams['language'] = languageFilter;
      }

      // Use admin route (session-based auth, not API key)
      await _loadFromAdminRoute(queryParams);
    } catch (e) {
      _error = 'Error loading resources: $e';
      _resources = [];
      print('[RESOURCES] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _loadFromAdminRoute(Map<String, String>? queryParams) async {
    final response = await _api.get(
      '/admin/resources',
      queryParams: queryParams,
    );

    if (response.statusCode == 200) {
      // Try to parse as JSON first
      try {
        final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
        if (jsonData['success'] == true) {
          final resourcesList = jsonData['resources'] as List<dynamic>?;
          if (resourcesList != null) {
            _resources = resourcesList
                .map((json) => Resource.fromJson(json as Map<String, dynamic>))
                .toList();
          } else {
            _resources = [];
          }
          _error = null;
        } else {
          // Fallback to HTML parsing for backward compatibility
          _resources = _parseResourcesFromHtml(response.body);
          _error = null;
        }
      } catch (e) {
        // If JSON parsing fails, try HTML parsing as fallback
        print('[RESOURCES] JSON parse failed, trying HTML: $e');
        _resources = _parseResourcesFromHtml(response.body);
        _error = null;
      }
    } else {
      _error = 'Failed to load resources: ${response.statusCode}';
      _resources = [];
    }
  }

  List<Resource> _parseResourcesFromHtml(String html) {
    final resources = <Resource>[];

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

      if (cells.length >= 3) {
        // Extract title from first cell
        final titleHtml = cells[0].group(1) ?? '';
        final title = _extractText(titleHtml);

        // Extract resource type from second cell
        final typeHtml = cells[1].group(1) ?? '';
        final resourceType = _extractText(typeHtml);

        // Extract publication date from third cell
        final dateHtml = cells.length > 2 ? cells[2].group(1) ?? '' : '';
        final dateText = _extractText(dateHtml);

        // Try to extract resource ID from edit/delete links
        final idMatch = RegExp(
          r'/admin/resources/(?:edit|delete|view)/(\d+)',
          caseSensitive: false,
        ).firstMatch(rowHtml);

        final id = idMatch != null
            ? int.tryParse(idMatch.group(1) ?? '0') ?? index
            : index;

        DateTime? publicationDate;
        try {
          if (dateText.isNotEmpty) {
            publicationDate = DateTime.parse(dateText);
          }
        } catch (e) {
          // Keep null if parsing fails
        }

        resources.add(Resource(
          id: id,
          title: title.isNotEmpty ? title : null,
          resourceType: resourceType.isNotEmpty ? resourceType : null,
          publicationDate: publicationDate,
        ));

        index++;
      }
    }

    return resources;
  }

  String _extractText(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<bool> deleteResource(int resourceId) async {
    try {
      final response = await _api.post('/admin/resources/delete/$resourceId');
      if (response.statusCode == 200 || response.statusCode == 302) {
        await loadResources();
        return true;
      } else {
        final decoded = jsonDecode(response.body);
        _error = decoded['message'] ?? 'Failed to delete resource';
        notifyListeners();
        return false;
      }
    } catch (e) {
      _error = 'Error deleting resource: $e';
      notifyListeners();
      return false;
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
