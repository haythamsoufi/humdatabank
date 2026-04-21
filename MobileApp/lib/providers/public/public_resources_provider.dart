import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../../config/app_config.dart';
import '../../models/shared/unified_planning_document.dart';
import '../../models/shared/resource.dart';
import '../../models/shared/resource_list_section.dart';
import '../../models/shared/resource_subcategory.dart';
import '../../services/api_service.dart';
import '../../services/storage_service.dart';
import '../../services/ifrc_unified_planning_service.dart';
import '../../services/unified_planning_documents_cache.dart';
import '../../services/unified_planning_pdf_thumbnail_cache.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

class PublicResourcesProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final IfrcUnifiedPlanningService _ifrcUnified = IfrcUnifiedPlanningService.instance;
  late final UnifiedPlanningDocumentsCache _unifiedPlanningDiskCache =
      UnifiedPlanningDocumentsCache(sl<StorageService>());

  List<Resource> _resources = [];
  List<ResourceListSection> _sections = [];
  bool _groupedMode = false;
  bool _groupedCapped = false;
  List<UnifiedPlanningDocument> _unifiedPlanningDocuments = [];
  bool _unifiedPlanningLoading = false;
  String? _unifiedPlanningErrorCode;
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
  List<ResourceListSection> get sections => _sections;
  bool get groupedMode => _groupedMode;
  bool get groupedCapped => _groupedCapped;
  bool get isLoading => _isLoading;
  bool get isLoadingMore => _isLoadingMore;
  String? get error => _error;
  bool get hasMore => _hasMore;
  int get totalItems => _totalItems;
  String get searchQuery => _searchQuery;
  String? get selectedType => _selectedType;

  List<UnifiedPlanningDocument> get unifiedPlanningDocuments =>
      List.unmodifiable(_unifiedPlanningDocuments);

  bool get unifiedPlanningLoading => _unifiedPlanningLoading;

  /// Localization key (see [AppLocalizations]); null when there is no error.
  String? get unifiedPlanningErrorCode => _unifiedPlanningErrorCode;

  /// IFRC GO unified planning PDFs — load from the unified planning screen only.
  Future<void> loadUnifiedPlanningDocuments() async {
    await _loadUnifiedPlanningDocuments();
  }

  /// Load the first page, optionally replacing search/type/locale filters.
  Future<void> loadResources({
    String? search,
    String? type,
    String? locale,
    bool refresh = false,
  }) async {
    if (_isLoading) return;

    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      _isLoadingMore = false;
      notifyListeners();
      return;
    }

    if (search != null) _searchQuery = search;
    if (type != null || refresh) _selectedType = type;
    if (locale != null) _locale = locale;

    _currentPage = 1;
    _isLoading = true;
    _error = null;
    _sections = [];
    _groupedMode = false;
    _groupedCapped = false;
    notifyListeners();

    try {
      final useGrouped = _searchQuery.isEmpty;
      if (useGrouped) {
        final parsed = await _fetchGrouped();
        _sections = parsed.$1;
        _groupedCapped = parsed.$2;
        _resources = [];
        _groupedMode = true;
        _hasMore = false;
        _totalItems = _sections.fold<int>(
          0,
          (sum, s) => sum + s.resources.length,
        );
      } else {
        final items = await _fetchPage(_currentPage);
        _resources = items;
        _sections = [];
        _groupedMode = false;
        _groupedCapped = false;
      }
    } catch (e) {
      _error = e.toString();
      _resources = [];
      _sections = [];
      _groupedMode = false;
      _groupedCapped = false;
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Load error: $e');
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Append the next page when the user scrolls to the bottom.
  Future<void> loadMore() async {
    if (_groupedMode) return;
    if (_isLoadingMore || !_hasMore || _isLoading) return;
    if (shouldDeferRemoteFetch) {
      notifyListeners();
      return;
    }

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

  Future<(List<ResourceListSection>, bool)> _fetchGrouped() async {
    final params = <String, String>{
      'locale': _locale,
      'grouped': 'true',
    };
    if (_selectedType != null && _selectedType!.isNotEmpty) {
      params['type'] = _selectedType!;
    }

    final response = await _api.get(
      AppConfig.mobilePublicResourcesEndpoint,
      queryParams: params,
      includeAuth: false,
    );

    if (response.statusCode != 200) {
      throw Exception('Failed to load resources (${response.statusCode}).');
    }

    final json = jsonDecode(response.body) as Map<String, dynamic>;
    if (json['success'] != true) {
      throw Exception('Failed to load resources.');
    }

    final data = json['data'];
    final meta = json['meta'] as Map<String, dynamic>? ?? {};
    final capped = meta['capped'] == true;

    if (data is! Map<String, dynamic>) {
      return (<ResourceListSection>[], capped);
    }

    final rawSections = (data['sections'] as List<dynamic>?) ?? [];
    final out = <ResourceListSection>[];
    for (final s in rawSections) {
      if (s is! Map<String, dynamic>) continue;
      final subJson = s['subcategory'];
      ResourceSubcategory? sub;
      if (subJson is Map<String, dynamic>) {
        sub = ResourceSubcategory.fromJson(subJson);
      }
      final rawList = (s['resources'] as List<dynamic>?) ?? [];
      final items = rawList
          .map((e) => Resource.fromJson(e as Map<String, dynamic>))
          .toList();
      if (items.isEmpty) continue;
      out.add(ResourceListSection(subcategory: sub, resources: items));
    }
    return (out, capped);
  }

  Future<void> _loadUnifiedPlanningDocuments() async {
    if (shouldDeferRemoteFetch) {
      await UnifiedPlanningPdfThumbnailCache.instance.warmCacheDirectory();
      final snap = await _unifiedPlanningDiskCache.load();
      if (snap != null && snap.documents.isNotEmpty) {
        _unifiedPlanningDocuments = snap.documents;
        UnifiedPlanningPdfThumbnailCache.instance.serverThumbnailsEnabled =
            snap.pdfThumbnailEnabled;
        _unifiedPlanningErrorCode = null;
      }
      _unifiedPlanningLoading = false;
      notifyListeners();
      return;
    }
    _unifiedPlanningLoading = true;
    _unifiedPlanningErrorCode = null;
    notifyListeners();

    try {
      // Resolve disk cache dir before IFRC fetch so grid cards can read JPEGs synchronously.
      await UnifiedPlanningPdfThumbnailCache.instance.warmCacheDirectory();
      UnifiedPlanningPdfThumbnailCache.instance.serverThumbnailsEnabled = true;
      final config = await _ifrcUnified.fetchConfig();
      if (config == null) {
        if (!await _hydrateUnifiedPlanningFromDiskCache()) {
          _unifiedPlanningDocuments = [];
          _unifiedPlanningErrorCode = 'unified_error_config';
        }
        return;
      }

      final thumbFlag = config['pdf_thumbnail_enabled'];
      final pdfThumbsEnabled = thumbFlag is bool ? thumbFlag : true;
      UnifiedPlanningPdfThumbnailCache.instance.serverThumbnailsEnabled =
          pdfThumbsEnabled;

      final listUrl = (config['ifrc_public_site_appeals_url'] as String?)?.trim();
      if (listUrl == null || listUrl.isEmpty) {
        if (!await _hydrateUnifiedPlanningFromDiskCache()) {
          _unifiedPlanningDocuments = [];
          _unifiedPlanningErrorCode = 'unified_error_config';
        }
        return;
      }

      if (AppConfig.ifrcApiUser.isEmpty || AppConfig.ifrcApiPassword.isEmpty) {
        if (!await _hydrateUnifiedPlanningFromDiskCache()) {
          _unifiedPlanningDocuments = [];
          _unifiedPlanningErrorCode = 'unified_error_credentials';
        }
        return;
      }

      final labels = IfrcUnifiedPlanningService.parseTypeLabels(config);
      _unifiedPlanningDocuments = await _ifrcUnified.fetchDocuments(
        ifrcListUrl: listUrl,
        typeLabels: labels,
      );
      _unifiedPlanningErrorCode = null;
      await _unifiedPlanningDiskCache.save(
        documents: _unifiedPlanningDocuments,
        pdfThumbnailEnabled: pdfThumbsEnabled,
      );
    } on StateError catch (e) {
      if (!await _hydrateUnifiedPlanningFromDiskCache()) {
        _unifiedPlanningDocuments = [];
        switch (e.message) {
          case 'missing_credentials':
            _unifiedPlanningErrorCode = 'unified_error_credentials';
            break;
          case 'ifrc_auth_failed':
            _unifiedPlanningErrorCode = 'unified_error_ifrc_auth';
            break;
          default:
            _unifiedPlanningErrorCode = 'unified_error_ifrc';
        }
      }
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Unified planning IFRC: $e');
    } catch (e) {
      if (!await _hydrateUnifiedPlanningFromDiskCache()) {
        _unifiedPlanningDocuments = [];
        _unifiedPlanningErrorCode = 'unified_error_ifrc';
      }
      DebugLogger.logErrorWithTag('PUBLIC_RESOURCES', 'Unified planning IFRC: $e');
    } finally {
      _unifiedPlanningLoading = false;
      notifyListeners();
    }
  }

  /// Applies last persisted unified planning snapshot when live IFRC/config fetch fails.
  Future<bool> _hydrateUnifiedPlanningFromDiskCache() async {
    final snap = await _unifiedPlanningDiskCache.load();
    if (snap == null || snap.documents.isEmpty) return false;
    _unifiedPlanningDocuments = snap.documents;
    UnifiedPlanningPdfThumbnailCache.instance.serverThumbnailsEnabled =
        snap.pdfThumbnailEnabled;
    _unifiedPlanningErrorCode = null;
    return true;
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
