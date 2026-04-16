import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../../config/app_config.dart';
import '../../models/shared/reunified_planning_document.dart';
import '../../models/shared/resource.dart';
import '../../services/api_service.dart';
import '../../services/ifrc_reunified_planning_service.dart';
import '../../utils/debug_logger.dart';

class PublicResourcesProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final IfrcReunifiedPlanningService _ifrcReunified = IfrcReunifiedPlanningService.instance;

  List<Resource> _resources = [];
  List<ReunifiedPlanningDocument> _reunifiedPlanningDocuments = [];
  bool _reunifiedLoading = false;
  String? _reunifiedErrorCode;
  bool _isLoading = false;
  bool _isLoadingMore = false;
  String? _error;
  int _currentPage = 1;
  int _totalItems = 0;
  bool _hasMore = false;

  String _searchQuery = '';
  String? _selectedType;
  String _locale = 'en';

  static const int _perPage = 20;

  List<Resource> get resources => _resources;
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  bool get hasMore => _hasMore;
  int get totalItems => _totalItems;
  String get searchQuery => _searchQuery;
  String? get selectedType => _selectedType;

  List<ReunifiedPlanningDocument> get reunifiedPlanningDocuments {
    final q = _searchQuery.trim().toLowerCase();
    if (q.isEmpty) return List.unmodifiable(_reunifiedPlanningDocuments);
    return _reunifiedPlanningDocuments
        .where((d) {
          final hay =
              '${d.title} ${d.countryName ?? ''} ${d.documentTypeLabel ?? ''} ${d.countryCode ?? ''}'
                  .toLowerCase();
          return hay.contains(q);
        })
        .toList(growable: false);
  }

  bool get reunifiedLoading => _reunifiedLoading;

  /// Localization key (see [AppLocalizations]); null when there is no error.
  String? get reunifiedErrorCode => _reunifiedErrorCode;

  /// Load the first page, optionally replacing search/type/locale filters.
  Future<void> loadResources({
    String? search,
    String? type,
    String? locale,
    bool refresh = false,
  }) async {
    if (_isLoading) return;

    if (search != null) _searchQuery = search;
    if (type != null || refresh) _selectedType = type;
    if (locale != null) _locale = locale;

    _currentPage = 1;
    _isLoading = true;
    _error = null;
    notifyListeners();

    final reunifiedFuture = _loadReunifiedPlanningDocuments();

    try {
      final items = await _fetchPage(_currentPage);
      _resources = items;
    } catch (e) {
      _error = e.toString();
      _resources = [];
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Load error: $e');
    }

    await reunifiedFuture;

    _isLoading = false;
    notifyListeners();
  }

  /// Append the next page when the user scrolls to the bottom.
  Future<void> loadMore() async {
    if (_isLoadingMore || !_hasMore || _isLoading) return;

    _isLoadingMore = true;
    notifyListeners();

    try {
      final nextPage = _currentPage + 1;
      final items = await _fetchPage(nextPage);
      _resources = [..._resources, ...items];
      _currentPage = nextPage;
    } catch (e) {
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Load-more error: $e');
    } finally {
      _isLoadingMore = false;
      notifyListeners();
    }
  }

  Future<List<Resource>> _fetchPage(int page) async {
    final params = <String, String>{
      'page': page.toString(),
      'per_page': _perPage.toString(),
      'locale': _locale,
    };
    if (_searchQuery.isNotEmpty) params['search'] = _searchQuery;
    if (_selectedType != null && _selectedType!.isNotEmpty) {
      params['type'] = _selectedType!;
    }

    final response = await _api.get(
      AppConfig.mobilePublicResourcesEndpoint,
      queryParams: params,
      includeAuth: false, // public endpoint — no session required
    );

    if (response.statusCode == 200) {
      final json = jsonDecode(response.body) as Map<String, dynamic>;
      if (json['success'] == true) {
        // mobile_paginated puts the list directly in `data` and pagination
        // fields in the top-level `meta` map.
        final rawItems = (json['data'] as List<dynamic>?) ?? [];
        final meta = json['meta'] as Map<String, dynamic>? ?? {};
        _totalItems = (meta['total'] as int?) ?? rawItems.length;
        final perPage = (meta['per_page'] as int?) ?? _perPage;
        final fetchedPage = (meta['page'] as int?) ?? page;
        _hasMore = fetchedPage * perPage < _totalItems;
        return rawItems
            .map((e) => Resource.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    }

    _hasMore = false;
    throw Exception('Failed to load resources (${response.statusCode}).');
  }

  Future<void> _loadReunifiedPlanningDocuments() async {
    _reunifiedLoading = true;
    _reunifiedErrorCode = null;
    notifyListeners();

    try {
      final config = await _ifrcReunified.fetchConfig();
      if (config == null) {
        _reunifiedPlanningDocuments = [];
        _reunifiedErrorCode = 'reunified_error_config';
        return;
      }

      final listUrl = (config['ifrc_public_site_appeals_url'] as String?)?.trim();
      if (listUrl == null || listUrl.isEmpty) {
        _reunifiedPlanningDocuments = [];
        _reunifiedErrorCode = 'reunified_error_config';
        return;
      }

      if (AppConfig.ifrcApiUser.isEmpty || AppConfig.ifrcApiPassword.isEmpty) {
        _reunifiedPlanningDocuments = [];
        _reunifiedErrorCode = 'reunified_error_credentials';
        return;
      }

      final labels = IfrcReunifiedPlanningService.parseTypeLabels(config);
      _reunifiedPlanningDocuments = await _ifrcReunified.fetchDocuments(
        ifrcListUrl: listUrl,
        typeLabels: labels,
      );
      _reunifiedErrorCode = null;
    } on StateError catch (e) {
      _reunifiedPlanningDocuments = [];
      switch (e.message) {
        case 'missing_credentials':
          _reunifiedErrorCode = 'reunified_error_credentials';
          break;
        case 'ifrc_auth_failed':
          _reunifiedErrorCode = 'reunified_error_ifrc_auth';
          break;
        default:
          _reunifiedErrorCode = 'reunified_error_ifrc';
      }
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Reunified IFRC: $e');
    } catch (e) {
      _reunifiedPlanningDocuments = [];
      _reunifiedErrorCode = 'reunified_error_ifrc';
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Reunified IFRC: $e');
    } finally {
      _reunifiedLoading = false;
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
