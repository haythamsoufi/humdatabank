import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';

class TranslationManagementProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  /// Matches Backoffice `list_translations` max (`max_per_page=200`).
  static const int _perPage = 200;

  List<Map<String, dynamic>> _translations = [];
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  int _page = 0;
  int _totalPages = 0;
  int _total = 0;

  String? _activeSearch;
  String? _activeLanguageFilter;
  String? _activeStatusFilter;
  String? _activeSourceFilter;

  /// Locale codes from API `meta.languages` (system supported languages). Null = unknown / do not filter.
  Set<String>? _translationLocaleAllowlist;

  List<Map<String, dynamic>> get translations => _translations;
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  int get total => _total;
  bool get hasMore => _totalPages > 0 && _page < _totalPages;

  /// Lowercased locale codes enabled in Backoffice; use to filter translation maps in the UI.
  Set<String>? get translationLocaleAllowlist => _translationLocaleAllowlist;

  List<String> _translationSourceOptions = [];
  bool _translationSourcesLoading = false;
  bool _translationSourcesLoaded = false;

  List<String> get translationSourceOptions =>
      List.unmodifiable(_translationSourceOptions);

  bool get translationSourcesLoading => _translationSourcesLoading;

  /// Loads distinct gettext #: paths for the source filter (cached after first success).
  Future<void> ensureTranslationSourcesLoaded({bool force = false}) async {
    if (force) {
      _translationSourcesLoaded = false;
    }
    if (_translationSourcesLoading) return;
    if (_translationSourcesLoaded) return;
    _translationSourcesLoading = true;
    notifyListeners();
    try {
      final response = await _api.get(
        AppConfig.mobileTranslationSourcesEndpoint,
        useCache: false,
      );
      if (response.statusCode == 200) {
        final body = jsonDecode(response.body);
        if (body is Map<String, dynamic> && body['success'] == true) {
          final data = body['data'];
          if (data is Map<String, dynamic> && data['sources'] is List) {
            _translationSourceOptions = (data['sources'] as List)
                .map((e) => e.toString())
                .where((s) => s.isNotEmpty)
                .toList();
          } else {
            _translationSourceOptions = [];
          }
        } else {
          _translationSourceOptions = [];
        }
      } else {
        _translationSourceOptions = [];
      }
    } catch (e) {
      DebugLogger.logWarn('TRANSLATIONS', 'Failed to load source paths: $e');
      _translationSourceOptions = [];
    } finally {
      _translationSourcesLoading = false;
      _translationSourcesLoaded = true;
      notifyListeners();
    }
  }

  Future<void> loadTranslations({
    String? search,
    String? languageFilter,
    String? statusFilter,
    String? sourceFilter,
  }) async {
    await _fetch(
      reset: true,
      search: search,
      languageFilter: languageFilter,
      statusFilter: statusFilter,
      sourceFilter: sourceFilter,
    );
  }

  /// Loads the next page from the mobile API (server default is 50/page; we use 200).
  Future<void> loadMore() async {
    if (!hasMore || _isLoadingMore || _isLoading) return;
    await _fetch(
      reset: false,
      search: _activeSearch,
      languageFilter: _activeLanguageFilter,
      statusFilter: _activeStatusFilter,
      sourceFilter: _activeSourceFilter,
    );
  }

  Future<void> _fetch({
    required bool reset,
    String? search,
    String? languageFilter,
    String? statusFilter,
    String? sourceFilter,
  }) async {
    if (reset) {
      _isLoading = true;
      _page = 0;
      _translations = [];
      _totalPages = 0;
      _total = 0;
      _activeSearch = search;
      _activeLanguageFilter = languageFilter;
      _activeStatusFilter = statusFilter;
      _activeSourceFilter = sourceFilter;
    } else {
      _isLoadingMore = true;
    }
    _error = null;
    notifyListeners();

    try {
      final nextPage = reset ? 1 : _page + 1;
      final queryParams = <String, String>{
        'page': '$nextPage',
        'per_page': '$_perPage',
      };
      if (_activeSearch != null && _activeSearch!.isNotEmpty) {
        queryParams['search'] = _activeSearch!;
      }
      if (_activeLanguageFilter != null &&
          _activeLanguageFilter!.isNotEmpty) {
        queryParams['language'] = _activeLanguageFilter!;
      }
      if (_activeStatusFilter != null && _activeStatusFilter!.isNotEmpty) {
        queryParams['status'] = _activeStatusFilter!;
      }
      if (_activeSourceFilter != null && _activeSourceFilter!.isNotEmpty) {
        queryParams['source'] = _activeSourceFilter!;
      }

      final response = await _api.get(
        AppConfig.mobileTranslationsEndpoint,
        queryParams: queryParams,
        useCache: false,
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          if (jsonData['success'] == true) {
            final rawData = jsonData['data'];
            final meta = jsonData['meta'] is Map<String, dynamic>
                ? jsonData['meta'] as Map<String, dynamic>
                : <String, dynamic>{};
            final List<dynamic>? translationsList = rawData is List
                ? rawData
                : rawData is Map
                    ? (rawData['translations'] as List<dynamic>?)
                    : (jsonData['translations'] as List<dynamic>?);
            final parsed = translationsList != null
                ? translationsList
                    .map((t) => t as Map<String, dynamic>)
                    .toList()
                : <Map<String, dynamic>>[];

            _total = meta['total'] is int
                ? meta['total'] as int
                : int.tryParse('${meta['total'] ?? 0}') ?? 0;
            _page = meta['page'] is int
                ? meta['page'] as int
                : int.tryParse('${meta['page'] ?? nextPage}') ?? nextPage;
            _totalPages = meta['total_pages'] is int
                ? meta['total_pages'] as int
                : int.tryParse(
                      '${meta['total_pages'] ?? meta['pages'] ?? 0}',
                    ) ??
                    0;

            if (meta.containsKey('languages') && meta['languages'] is List) {
              _translationLocaleAllowlist = (meta['languages'] as List)
                  .map((e) => e.toString().toLowerCase())
                  .toSet();
            } else if (reset) {
              _translationLocaleAllowlist = null;
            }

            if (reset) {
              _translations = parsed;
            } else {
              _translations = [..._translations, ...parsed];
            }
            _error = null;
          } else {
            _translations = reset ? _parseTranslationsFromHtml(response.body) : _translations;
            if (reset) {
              _translationLocaleAllowlist = null;
              _total = _translations.length;
              _page = 1;
              _totalPages = 1;
            }
            _error = null;
          }
        } catch (e) {
          DebugLogger.logWarn('TRANSLATIONS', 'JSON parse failed, trying HTML: $e');
          final fromHtml = _parseTranslationsFromHtml(response.body);
          if (reset) {
            _translations = fromHtml;
            _translationLocaleAllowlist = null;
            _total = fromHtml.length;
            _page = 1;
            _totalPages = 1;
          }
          _error = null;
        }
      } else {
        _error = 'Failed to load translations: ${response.statusCode}';
        if (reset) {
          _translations = [];
          _translationLocaleAllowlist = null;
        }
      }
    } catch (e) {
      _error = 'Error loading translations: $e';
      if (reset) {
        _translations = [];
        _translationLocaleAllowlist = null;
      }
      DebugLogger.logErrorWithTag('TRANSLATIONS', 'Error: $e');
    } finally {
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
    }
  }

  Future<bool> updateTranslation(
      int translationId, Map<String, dynamic> data) async {
    try {
      final response = await _api.post(
        '${AppConfig.mobileTranslationsEndpoint}/$translationId',
        body: data,
      );
      if (response.statusCode == 200) {
        await _fetch(
          reset: true,
          search: _activeSearch,
          languageFilter: _activeLanguageFilter,
          statusFilter: _activeStatusFilter,
          sourceFilter: _activeSourceFilter,
        );
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
