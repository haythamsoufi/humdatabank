import 'package:flutter/foundation.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../models/shared/indicator.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/debug_logger.dart';

class IndicatorBankAdminProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<Indicator> _indicators = [];
  bool _isLoading = false;
  String? _error;

  List<Indicator> get indicators => _indicators;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadIndicators({
    String? search,
    String? categoryFilter,
    String? sectorFilter,
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
        queryParams['type'] = categoryFilter;
      }
      if (sectorFilter != null && sectorFilter.isNotEmpty) {
        queryParams['sector'] = sectorFilter;
      }

      // Use the admin HTML route (requires session authentication)
      final response =
          await _errorHandler.executeWithErrorHandling<http.Response>(
        apiCall: () => _api.get(
          '/admin/indicator_bank',
          queryParams: queryParams.isNotEmpty ? queryParams : null,
        ),
        context: 'Load Indicators (Admin)',
        defaultValue: null,
        maxRetries: 1,
        handleAuthErrors: true,
      );

      if (response == null) {
        _error = 'Unable to load indicators. Please try again.';
        _indicators = [];
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
              final indicatorsList = jsonData['indicators'] as List<dynamic>?;
              if (indicatorsList != null) {
                _indicators = indicatorsList
                    .map((json) => Indicator.fromJson(json as Map<String, dynamic>))
                    .toList();
              } else {
                _indicators = [];
              }
              _error = null;
              DebugLogger.log(
                  'INDICATORS', 'Parsed ${_indicators.length} indicators from JSON',
                  level: LogLevel.debug);
            } else {
              // Fallback to HTML parsing for backward compatibility
              _indicators = _parseIndicatorsFromHtml(response.body);
              _error = null;
            }
          } catch (e) {
            // If JSON parsing fails, try HTML parsing as fallback
            print('[INDICATORS] JSON parse failed, trying HTML: $e');
            _indicators = _parseIndicatorsFromHtml(response.body);
            _error = null;
            DebugLogger.log(
                'INDICATORS', 'Parsed ${_indicators.length} indicators from HTML',
                level: LogLevel.debug);
          }
        } catch (e, stackTrace) {
          final error = _errorHandler.parseError(
            error: e,
            stackTrace: stackTrace,
            context: 'Parse Indicators',
          );
          _error = error.getUserMessage();
          _indicators = [];
        }
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response.statusCode}'),
          response: response,
          context: 'Load Indicators (Admin)',
        );
        _error = error.getUserMessage();
        _indicators = [];
      }
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Indicators (Admin)',
      );
      _error = error.getUserMessage();
      _indicators = [];
      _errorHandler.logError(error);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  List<Indicator> _parseIndicatorsFromHtml(String html) {
    final indicators = <Indicator>[];

    // Find the indicators table - look for table with id="indicatorsTable" or similar
    String? tableHtml;

    // Try to find the main indicators table
    final tableMatch = RegExp(
      r'<table[^>]*id="[^"]*indicator[^"]*"[^>]*>([\s\S]*?)</table>',
      caseSensitive: false,
      dotAll: true,
    ).firstMatch(html);

    if (tableMatch != null) {
      tableHtml = tableMatch.group(0);
    } else {
      // Fallback: find any table in the main content area
      final contentMatch = RegExp(
        r'<table[^>]*>([\s\S]*?)</table>',
        caseSensitive: false,
        dotAll: true,
      ).firstMatch(html);
      tableHtml = contentMatch?.group(0);
    }

    if (tableHtml == null) {
      DebugLogger.logWarn('INDICATORS', 'No table found in HTML');
      return indicators;
    }

    // Parse HTML table rows
    final rowPattern = RegExp(
      r'<tr[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(tableHtml);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Skip header rows
      if (rowHtml.contains('<th') ||
          rowHtml.contains('thead') ||
          rowHtml.trim().isEmpty) {
        continue;
      }

      // Extract cells
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.isEmpty) continue;

      // Extract indicator ID from first cell (column 0)
      // ID is in a link like: <a href="...">{{ indicator.id }}</a>
      int id = index;
      if (cells.isNotEmpty) {
        final idHtml = cells[0].group(1) ?? '';
        final idText = _extractText(idHtml);
        id = int.tryParse(idText) ?? index;

        // Also try to extract from link if text extraction fails
        if (id == index) {
          final idMatch = RegExp(
            r'/admin/indicator_bank/(?:edit|delete|view|archive)/(\d+)',
            caseSensitive: false,
          ).firstMatch(rowHtml);
          if (idMatch != null) {
            id = int.tryParse(idMatch.group(1) ?? '0') ?? index;
          }
        }
      }

      // Extract indicator name from second cell (column 1 - Name English)
      String name = '';
      if (cells.length > 1) {
        final nameHtml = cells[1].group(1) ?? '';
        name = _extractText(nameHtml);
      }

      // Extract type from ninth cell (column 8 - Type)
      String? type;
      if (cells.length > 8) {
        final typeHtml = cells[8].group(1) ?? '';
        final typeText = _extractText(typeHtml);
        if (typeText.isNotEmpty && typeText != '-') {
          type = typeText;
        }
      }

      // Extract definition from eleventh cell (column 10 - Definition)
      String? definition;
      if (cells.length > 10) {
        final definitionHtml = cells[10].group(1) ?? '';
        // Try to get full definition from data attribute first
        final dataAttrMatch = RegExp(
          r'data-full-definition="([^"]*)"',
          caseSensitive: false,
        ).firstMatch(definitionHtml);
        if (dataAttrMatch != null) {
          definition = dataAttrMatch.group(1)?.trim();
        } else {
          final definitionText = _extractText(definitionHtml);
          if (definitionText.isNotEmpty && definitionText != '-') {
            definition = definitionText;
          }
        }
      }

      // Extract sector from nineteenth cell (column 18 - Sector)
      String? sector;
      if (cells.length > 18) {
        final sectorHtml = cells[18].group(1) ?? '';
        // Sector is in nested divs with class "sector-items"
        final sectorItems = RegExp(
          r'<div[^>]*class="sector-items"[^>]*>([\s\S]*?)</div>',
          caseSensitive: false,
        ).firstMatch(sectorHtml);

        if (sectorItems != null) {
          final itemsHtml = sectorItems.group(1) ?? '';
          final itemDivs = RegExp(
            r'<div[^>]*>([\s\S]*?)</div>',
            caseSensitive: false,
          ).allMatches(itemsHtml);

          final sectorNames = <String>[];
          for (final div in itemDivs) {
            final sectorName = _extractText(div.group(1) ?? '');
            if (sectorName.isNotEmpty && sectorName != '-') {
              sectorNames.add(sectorName);
            }
          }
          if (sectorNames.isNotEmpty) {
            sector = sectorNames.join(', ');
          }
        } else {
          // Fallback: extract text directly
          final sectorText = _extractText(sectorHtml);
          if (sectorText.isNotEmpty && sectorText != '-') {
            sector = sectorText;
          }
        }
      }

      // Extract sub-sector from twentieth cell (column 19 - Sub-Sector)
      String? subSector;
      if (cells.length > 19) {
        final subSectorHtml = cells[19].group(1) ?? '';
        // Sub-sector is also in nested divs with class "sector-items"
        final subSectorItems = RegExp(
          r'<div[^>]*class="sector-items"[^>]*>([\s\S]*?)</div>',
          caseSensitive: false,
        ).firstMatch(subSectorHtml);

        if (subSectorItems != null) {
          final itemsHtml = subSectorItems.group(1) ?? '';
          final itemDivs = RegExp(
            r'<div[^>]*>([\s\S]*?)</div>',
            caseSensitive: false,
          ).allMatches(itemsHtml);

          final subSectorNames = <String>[];
          for (final div in itemDivs) {
            final subSectorName = _extractText(div.group(1) ?? '');
            if (subSectorName.isNotEmpty && subSectorName != '-') {
              subSectorNames.add(subSectorName);
            }
          }
          if (subSectorNames.isNotEmpty) {
            subSector = subSectorNames.join(', ');
          }
        } else {
          // Fallback: extract text directly
          final subSectorText = _extractText(subSectorHtml);
          if (subSectorText.isNotEmpty && subSectorText != '-') {
            subSector = subSectorText;
          }
        }
      }

      if (name.isNotEmpty) {
        indicators.add(Indicator(
          id: id,
          name: name,
          type: type,
          sector: sector,
          subSector: subSector,
          description: definition,
        ));
        index++;
      }
    }

    return indicators;
  }

  String _extractText(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<bool> deleteIndicator(int indicatorId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post('/admin/indicator_bank/delete/$indicatorId'),
      context: 'Delete Indicator',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to delete indicator. Please try again.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 200 || response.statusCode == 302) {
      await loadIndicators();
      return true;
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Delete Indicator',
      );
      _error = error.getUserMessage();
      notifyListeners();
      return false;
    }
  }

  Future<bool> archiveIndicator(int indicatorId) async {
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post('/admin/indicator_bank/archive/$indicatorId'),
      context: 'Archive Indicator',
      defaultValue: null,
      maxRetries: 0,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to archive indicator. Please try again.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 200 || response.statusCode == 302) {
      await loadIndicators();
      return true;
    } else {
      final error = _errorHandler.parseError(
        error: Exception('HTTP ${response.statusCode}'),
        response: response,
        context: 'Archive Indicator',
      );
      _error = error.getUserMessage();
      notifyListeners();
      return false;
    }
  }

  Future<Indicator?> getIndicatorById(int id) async {
    try {
      // Try to get from cached list first
      try {
        final cached = _indicators.firstWhere(
          (ind) => ind.id == id,
        );
        if (cached.name != null && cached.name!.isNotEmpty) {
          return cached;
        }
      } catch (e) {
        // Not found in cache, continue to fetch
      }

      // If not in cache, reload indicators to ensure we have the latest data
      await loadIndicators();

      // Try again from the refreshed list
      try {
        final cached = _indicators.firstWhere(
          (ind) => ind.id == id,
        );
        if (cached.name != null && cached.name!.isNotEmpty) {
          return cached;
        }
      } catch (e) {
        // Still not found
      }

      // If still not found, try to fetch from view route and parse HTML
      final response = await _api.get('/admin/indicator_bank/view/$id');
      if (response.statusCode == 200) {
        // Parse HTML to extract indicator data
        final indicator = _parseIndicatorFromViewHtml(response.body, id);
        return indicator;
      }
      return null;
    } catch (e) {
      DebugLogger.logError('Error fetching indicator $id: $e');
      return null;
    }
  }

  Indicator? _parseIndicatorFromViewHtml(String html, int id) {
    // Try to extract data from view page HTML
    // This is a simplified parser - you may need to adjust based on actual HTML structure

    // Extract name
    final nameMatch = RegExp(
      r'<h[1-6][^>]*>([^<]*indicator[^<]*name[^<]*|[^<]+)</h[1-6]>',
      caseSensitive: false,
    ).firstMatch(html);

    String? name;
    if (nameMatch != null) {
      name = _extractText(nameMatch.group(1) ?? '');
    }

    // Try to find name in common patterns
    if (name == null || name.isEmpty) {
      final namePattern = RegExp(
        r'<td[^>]*>Name[^<]*</td>\s*<td[^>]*>([^<]+)</td>',
        caseSensitive: false,
      ).firstMatch(html);
      if (namePattern != null) {
        name = _extractText(namePattern.group(1) ?? '');
      }
    }

    // Extract type
    String? type;
    final typePattern = RegExp(
      r'<td[^>]*>Type[^<]*</td>\s*<td[^>]*>([^<]+)</td>',
      caseSensitive: false,
    ).firstMatch(html);
    if (typePattern != null) {
      type = _extractText(typePattern.group(1) ?? '');
      if (type == '-' || type.isEmpty) type = null;
    }

    // Extract definition
    String? definition;
    final defPattern = RegExp(
      r'<td[^>]*>Definition[^<]*</td>\s*<td[^>]*>([^<]+)</td>',
      caseSensitive: false,
    ).firstMatch(html);
    if (defPattern != null) {
      definition = _extractText(defPattern.group(1) ?? '');
      if (definition == '-' || definition.isEmpty) definition = null;
    }

    // Extract sector
    String? sector;
    final sectorPattern = RegExp(
      r'<td[^>]*>Sector[^<]*</td>\s*<td[^>]*>([^<]+)</td>',
      caseSensitive: false,
    ).firstMatch(html);
    if (sectorPattern != null) {
      sector = _extractText(sectorPattern.group(1) ?? '');
      if (sector == '-' || sector.isEmpty) sector = null;
    }

    if (name == null || name.isEmpty) {
      return null;
    }

    return Indicator(
      id: id,
      name: name,
      type: type,
      sector: sector,
      description: definition,
    );
  }

  Future<bool> updateIndicator(int id, Map<String, dynamic> data) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _api.post(
        '/admin/indicator_bank/edit/$id',
        body: data,
        additionalHeaders: {'X-Requested-With': 'XMLHttpRequest'},
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        if (decoded['success'] == true) {
          _error = null;
          // Reload indicators to get updated data
          await loadIndicators();
          return true;
        } else {
          _error = decoded['message'] ?? 'Failed to update indicator';
          return false;
        }
      } else {
        final decoded = jsonDecode(response.body);
        _error = decoded['message'] ??
            'Failed to update indicator: ${response.statusCode}';
        return false;
      }
    } on AuthenticationException catch (e) {
      _error = e.toString();
      return false;
    } catch (e) {
      _error = 'Error updating indicator: $e';
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
