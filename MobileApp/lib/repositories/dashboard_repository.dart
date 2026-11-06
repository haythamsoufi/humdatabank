import 'dart:convert';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:http/http.dart' as http;
import '../models/shared/assignment.dart';
import '../models/shared/dashboard_data.dart';
import '../models/shared/entity.dart';
import '../models/shared/focal_point_contact.dart';
import '../services/api_service.dart';
import '../services/error_handler.dart';
import '../services/offline/entity_dashboard_store.dart';
import '../services/storage_service.dart';
import '../config/app_config.dart';
import '../utils/debug_logger.dart';
import '../di/service_locator.dart';

/// Repository for dashboard data access.
/// Handles API calls, caching, and data parsing.
/// Separates data access logic from state management.
class DashboardRepository {
  final ApiService _api = sl<ApiService>();
  final StorageService _storage = StorageService();
  final ErrorHandler _errorHandler = ErrorHandler();
  final EntityDashboardStore _entityStore = EntityDashboardStore();

  /// Load dashboard data from API.
  /// Optionally accepts entity selection to pass as query parameter.
  /// Returns null if the request fails (error is handled by ErrorHandler).
  Future<DashboardData?> loadDashboardFromApi({Entity? entity}) async {
    DebugLogger.logDashboard(
      'Loading user dashboard from API (${AppConfig.dashboardApiEndpoint})...',
    );

    // Build endpoint with optional entity query parameter
    String endpoint = AppConfig.dashboardApiEndpoint;
    if (entity != null) {
      final uri = Uri.parse(endpoint);
      final updatedUri = uri.replace(queryParameters: {
        'entity_type': entity.entityType,
        'entity_id': entity.entityId.toString(),
      });
      endpoint = updatedUri.toString();
      DebugLogger.logDashboard('Loading dashboard with entity: ${entity.selectionKey}');
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(endpoint),
      context: 'Dashboard',
      defaultValue: null,
      maxRetries: 2,
      handleAuthErrors: true,
    );

    if (response == null || response.statusCode != 200) {
      DebugLogger.logWarn(
        'DASHBOARD',
        'Failed to load dashboard: status=${response?.statusCode}, '
        'endpoint=$endpoint',
      );
      return null;
    }

    try {
      return _parseDashboardResponse(response.body);
    } catch (e, stackTrace) {
      _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Dashboard parsing',
      );
      DebugLogger.logError('Failed to parse dashboard response: $e');
      return null;
    }
  }

  /// Parse dashboard JSON response.
  DashboardData _parseDashboardResponse(String responseBody) {
    DebugLogger.logDashboard('Parsing dashboard JSON response...');
    DebugLogger.logDashboard('Response length: ${responseBody.length} chars');

    final json = jsonDecode(responseBody);
    if (json is! Map<String, dynamic>) {
      throw Exception('Invalid JSON response format');
    }

    return _parseJsonDashboard(json);
  }

  /// Parse JSON dashboard data.
  DashboardData _parseJsonDashboard(Map<String, dynamic> json) {
    DebugLogger.logDashboard('Parsing JSON dashboard data');

    // Mobile envelope: { success, data: { current_assignments, ... } } — unwrap if present.
    Map<String, dynamic> root = json;
    final inner = json['data'];
    if (inner is Map<String, dynamic> &&
        (inner.containsKey('current_assignments') ||
            inner.containsKey('past_assignments') ||
            inner.containsKey('entities'))) {
      root = inner;
      DebugLogger.logDashboard('Unwrapped mobile_ok `data` envelope for dashboard payload');
    }

    final topKeys = root.keys.toList()..sort();
    DebugLogger.logDashboard('Dashboard JSON keys (after unwrap): $topKeys');
    if (root.containsKey('user_count') &&
        !root.containsKey('current_assignments')) {
      DebugLogger.logWarn(
        'DASHBOARD',
        'Response looks like admin platform stats (user_count) — not assignment lists. '
        'AppConfig.dashboardApiEndpoint must be mobileUserDashboardEndpoint '
        '(/user/dashboard), not admin analytics dashboard-stats.',
      );
    }

    final currentAssignments = <Assignment>[];
    final pastAssignments = <Assignment>[];
    final entities = <Entity>[];
    final nsFocalPoints = <FocalPointContact>[];
    final orgFocalPoints = <FocalPointContact>[];
    final fdsMembers = <FocalPointContact>[];
    Entity? selectedEntity;

    if (root.containsKey('current_assignments')) {
      currentAssignments.addAll((root['current_assignments'] as List)
          .map((item) => Assignment.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (root.containsKey('past_assignments')) {
      pastAssignments.addAll((root['past_assignments'] as List)
          .map((item) => Assignment.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (root.containsKey('entities')) {
      entities.addAll((root['entities'] as List)
          .map((item) => Entity.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (root.containsKey('ns_focal_points')) {
      nsFocalPoints.addAll((root['ns_focal_points'] as List)
          .map((item) => FocalPointContact.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (root.containsKey('org_focal_points')) {
      orgFocalPoints.addAll((root['org_focal_points'] as List)
          .map((item) => FocalPointContact.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (root.containsKey('fds_members')) {
      fdsMembers.addAll((root['fds_members'] as List)
          .map((item) => FocalPointContact.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    // Handle selected_entity from API response
    if (root.containsKey('selected_entity') &&
        root['selected_entity'] != null) {
      final selectedEntityJson =
          root['selected_entity'] as Map<String, dynamic>;
      selectedEntity = Entity.fromJson(selectedEntityJson);
      // Save selected entity to storage
      _storage.setString(
          AppConfig.selectedEntityTypeKey, selectedEntity.entityType);
      _storage.setInt(
          AppConfig.selectedEntityIdKey, selectedEntity.entityId);
    } else if (entities.isNotEmpty) {
      // Default to first entity if none selected
      selectedEntity = entities.first;
    }

    DebugLogger.logDashboard(
        'Parsed ${currentAssignments.length} current and ${pastAssignments.length} past assignments');
    DebugLogger.logDashboard(
        'Parsed ${entities.length} entities, selectedEntity: ${selectedEntity?.displayLabel ?? "null"}');

    return DashboardData(
      currentAssignments: currentAssignments,
      pastAssignments: pastAssignments,
      entities: entities,
      selectedEntity: selectedEntity,
      nsFocalPoints: nsFocalPoints,
      orgFocalPoints: orgFocalPoints,
      fdsMembers: fdsMembers,
      timestamp: DateTime.now(),
    );
  }

  /// Load dashboard data from cache.
  /// Returns null if cache is invalid or missing.
  ///
  /// When [ignoreExpiry] is true, a snapshot older than [AppConfig.cacheExpiration]
  /// is still returned (used for offline pull-to-refresh so the UI can reload
  /// from disk without hitting the network).
  Future<DashboardData?> loadDashboardFromCache({bool ignoreExpiry = false}) async {
    try {
      final cachedData =
          await _storage.getString(AppConfig.cachedDashboardKey);
      if (cachedData == null) {
        return null;
      }

      final data = jsonDecode(cachedData);
      final cacheTime = DateTime.parse(data['timestamp']);

      // Check if cache is still valid (within 1 hour)
      if (!ignoreExpiry &&
          DateTime.now().difference(cacheTime) >= AppConfig.cacheExpiration) {
        DebugLogger.logDashboard('Cache expired');
        return null;
      }

      final currentAssignments = (data['current_assignments'] as List)
          .map((json) => Assignment.fromJson(json))
          .toList();

      final pastAssignments = (data['past_assignments'] as List)
          .map((json) => Assignment.fromJson(json))
          .toList();

      final nsFocalPoints = (data['ns_focal_points'] as List? ?? const [])
          .map((json) => FocalPointContact.fromJson(json as Map<String, dynamic>))
          .toList();

      final orgFocalPoints = (data['org_focal_points'] as List? ?? const [])
          .map((json) => FocalPointContact.fromJson(json as Map<String, dynamic>))
          .toList();

      final fdsMembers = (data['fds_members'] as List? ?? const [])
          .map((json) => FocalPointContact.fromJson(json as Map<String, dynamic>))
          .toList();

      // Try to load entities from cache
      final entities = await loadEntitiesFromCache();

      // Try to load selected entity
      Entity? selectedEntity;
      if (entities.isNotEmpty) {
        final entityType =
            await _storage.getString(AppConfig.selectedEntityTypeKey);
        final entityId = await _storage.getInt(AppConfig.selectedEntityIdKey);

        if (entityType != null && entityId != null) {
          selectedEntity = entities.firstWhere(
            (e) => e.entityType == entityType && e.entityId == entityId,
            orElse: () => entities.first,
          );
        } else if (entities.isNotEmpty) {
          selectedEntity = entities.first;
        }
      }

      DebugLogger.logDashboard('Loaded dashboard from cache');
      return DashboardData(
        currentAssignments: currentAssignments,
        pastAssignments: pastAssignments,
        entities: entities,
        selectedEntity: selectedEntity,
        nsFocalPoints: nsFocalPoints,
        orgFocalPoints: orgFocalPoints,
        fdsMembers: fdsMembers,
        timestamp: cacheTime,
      );
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error loading from cache: $e');
      return null;
    }
  }

  /// Save dashboard data to cache.
  Future<void> saveDashboardToCache(DashboardData data) async {
    try {
      final cacheData = {
        'timestamp': (data.timestamp ?? DateTime.now()).toIso8601String(),
        'current_assignments':
            data.currentAssignments.map((a) => a.toJson()).toList(),
        'past_assignments': data.pastAssignments.map((a) => a.toJson()).toList(),
        'ns_focal_points': data.nsFocalPoints.map((fp) => fp.toJson()).toList(),
        'org_focal_points': data.orgFocalPoints.map((fp) => fp.toJson()).toList(),
        'fds_members': data.fdsMembers.map((fp) => fp.toJson()).toList(),
      };
      await _storage.setString(
          AppConfig.cachedDashboardKey, jsonEncode(cacheData));

      // Also save entities to cache
      if (data.entities.isNotEmpty) {
        await _storage.setString(
          AppConfig.cachedEntitiesKey,
          jsonEncode({
            'entities': data.entities.map((e) => e.toJson()).toList()
          }),
        );
      }

      final entity = data.selectedEntity;
      if (entity != null) {
        await _entityStore.save(EntityDashboardSnapshot.fromData(data, entity));
      }

      DebugLogger.logDashboard('Saved dashboard to cache');
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error saving to cache: $e');
    }
  }

  /// The last dashboard saved for [entity], so it can be shown without a
  /// connection. Null when that entity was never loaded or downloaded.
  Future<EntityDashboardSnapshot?> loadEntitySnapshot(Entity entity) =>
      _entityStore.read(entity);

  /// Downloads the assignments of every entity of the given form templates in
  /// one request and keeps them as those entities' offline dashboards.
  ///
  /// Returns the entities that have assignments of those templates (empty when
  /// the request fails). Selecting any of them later needs no connection, and
  /// their forms can be saved without visiting each entity first.
  Future<List<EntityDashboardSnapshot>> syncOfflineEntityDashboards({
    required Set<int> templateIds,
    int limit = 50,
  }) async {
    if (templateIds.isEmpty) return const [];
    final ids = (templateIds.toList()..sort()).join(',');
    final endpoint =
        '${AppConfig.mobileUserDashboardEndpoint}/offline-entities'
        '?template_ids=$ids&limit=$limit';
    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(endpoint),
      context: 'Offline entity dashboards',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );
    if (response == null || response.statusCode != 200) {
      DebugLogger.logWarn(
        'DASHBOARD',
        'Offline entity dashboards failed: status=${response?.statusCode}',
      );
      return const [];
    }
    final List<EntityDashboardSnapshot> snapshots;
    try {
      snapshots = parseOfflineEntityDashboards(response.body);
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Unreadable offline dashboards: $e');
      return const [];
    }
    for (final snapshot in snapshots) {
      await _entityStore.mergeTemplates(snapshot, templateIds);
    }
    return snapshots;
  }

  /// Parses the `offline-entities` response (with or without the mobile envelope).
  @visibleForTesting
  static List<EntityDashboardSnapshot> parseOfflineEntityDashboards(
    String body,
  ) {
    final json = jsonDecode(body);
    if (json is! Map) throw const FormatException('Invalid response format');
    var root = Map<String, dynamic>.from(json);
    final inner = root['data'];
    if (inner is Map && inner.containsKey('entities')) {
      root = Map<String, dynamic>.from(inner);
    }
    return [
      for (final item in (root['entities'] as List? ?? const []))
        if (item is Map && item['entity'] is Map)
          EntityDashboardSnapshot.fromServerJson(
            Map<String, dynamic>.from(item),
          ),
    ];
  }

  /// Load entities from cache.
  Future<List<Entity>> loadEntitiesFromCache() async {
    try {
      final cachedEntities =
          await _storage.getString(AppConfig.cachedEntitiesKey);
      if (cachedEntities != null) {
        final data = jsonDecode(cachedEntities);
        return (data['entities'] as List)
            .map((json) => Entity.fromJson(json))
            .toList();
      }
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error loading entities from cache: $e');
    }
    return [];
  }

  /// Forgets the saved assignments but keeps the entity list, so the entity
  /// picker still works while another entity's dashboard loads.
  Future<void> clearAssignmentsCache() async {
    await _storage.remove(AppConfig.cachedDashboardKey);
  }

  /// Clear dashboard cache.
  Future<void> clearCache() async {
    await _storage.remove(AppConfig.cachedDashboardKey);
    await _storage.remove(AppConfig.cachedEntitiesKey);
    DebugLogger.logDashboard('Cleared dashboard cache');
  }

  /// Update selected entity in local storage only.
  /// The API will update the session when entity is passed as query parameter.
  Future<void> updateSelectedEntityStorage(Entity entity) async {
    DebugLogger.logDashboard('Saving selected entity to storage: ${entity.selectionKey}');
    await _storage.setString(AppConfig.selectedEntityTypeKey, entity.entityType);
    await _storage.setInt(AppConfig.selectedEntityIdKey, entity.entityId);
  }

  /// Load selected entity from storage.
  Future<Entity?> loadSelectedEntityFromStorage(List<Entity> entities) async {
    if (entities.isEmpty) {
      return null;
    }

    final entityType =
        await _storage.getString(AppConfig.selectedEntityTypeKey);
    final entityId = await _storage.getInt(AppConfig.selectedEntityIdKey);

    if (entityType != null && entityId != null) {
      return entities.firstWhere(
        (e) => e.entityType == entityType && e.entityId == entityId,
        orElse: () => entities.first,
      );
    }

    return entities.first;
  }
}
