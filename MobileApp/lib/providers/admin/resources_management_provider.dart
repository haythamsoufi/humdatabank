import 'package:flutter/foundation.dart';
import '../../config/app_config.dart';
import '../../models/shared/resource.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class ResourcesManagementProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();

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
    await runAsyncOperation(() async {
      if (shouldDeferRemoteFetch) {
        _isLoading = false;
        notifyListeners();
        return;
      }
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
        DebugLogger.logErrorWithTag('RESOURCES', 'Error: $e');
      } finally {
        _isLoading = false;
        notifyListeners();
      }
    });
  }

  Future<void> _loadFromAdminRoute(Map<String, String>? queryParams) async {
    final collected = <Resource>[];
    var page = 1;
    var totalPages = 1;
    var lastStatus = 0;
    while (page <= totalPages && page <= 25) {
      final pageParams = {
        ...?queryParams,
        'page': '$page',
        'per_page': '200',
      };
      final response = await _api.get(
        AppConfig.mobileResourcesEndpoint,
        queryParams: pageParams,
      );
      lastStatus = response.statusCode;
      if (response.statusCode != 200) break;
      final jsonData = decodeJsonObject(response.body);
      if (jsonData['success'] != true) {
        if (page == 1 && !response.body.trimLeft().startsWith('{')) {
          _resources = _parseResourcesFromHtml(response.body);
          _error = null;
          return;
        }
        break;
      }
      collected.addAll(mobileDataMaps(jsonData).map(Resource.fromJson));
      totalPages = mobileTotalPages(jsonData);
      page += 1;
    }
    if (collected.isEmpty && lastStatus != 200) {
      _error = 'Failed to load resources: $lastStatus';
      _resources = [];
      return;
    }
    _resources = collected;
    _error = null;
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
      final response = await _api.post(
        '${AppConfig.mobileResourcesEndpoint}/$resourceId/delete',
      );
      if (response.statusCode == 200 || response.statusCode == 302) {
        await loadResources();
        return true;
      } else {
        final decoded = decodeJsonObject(response.body);
        _error = decoded['message']?.toString() ?? 'Failed to delete resource';
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
