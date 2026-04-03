import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/shared/assignment.dart';
import '../models/shared/entity.dart';
import '../services/api_service.dart';
import '../services/error_handler.dart';
import '../services/storage_service.dart';
import '../config/app_config.dart';
import '../utils/debug_logger.dart';

/// Dashboard data model
class DashboardData {
  final List<Assignment> currentAssignments;
  final List<Assignment> pastAssignments;
  final List<Entity> entities;
  final Entity? selectedEntity;
  final DateTime? timestamp;

  DashboardData({
    required this.currentAssignments,
    required this.pastAssignments,
    required this.entities,
    this.selectedEntity,
    this.timestamp,
  });
}

/// Repository for dashboard data access.
/// Handles API calls, caching, and data parsing.
/// Separates data access logic from state management.
class DashboardRepository {
  final ApiService _api = ApiService();
  final StorageService _storage = StorageService();
  final ErrorHandler _errorHandler = ErrorHandler();

  /// Load dashboard data from API.
  /// Optionally accepts entity selection to pass as query parameter.
  /// Returns null if the request fails (error is handled by ErrorHandler).
  Future<DashboardData?> loadDashboardFromApi({Entity? entity}) async {
    DebugLogger.logDashboard('Loading dashboard from API...');

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
      DebugLogger.logWarn('DASHBOARD', 'Failed to load dashboard from API');
      return null;
    }

    try {
      return _parseDashboardResponse(response.body);
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
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

    final currentAssignments = <Assignment>[];
    final pastAssignments = <Assignment>[];
    final entities = <Entity>[];
    Entity? selectedEntity;

    if (json.containsKey('current_assignments')) {
      currentAssignments.addAll((json['current_assignments'] as List)
          .map((item) => Assignment.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (json.containsKey('past_assignments')) {
      pastAssignments.addAll((json['past_assignments'] as List)
          .map((item) => Assignment.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    if (json.containsKey('entities')) {
      entities.addAll((json['entities'] as List)
          .map((item) => Entity.fromJson(item as Map<String, dynamic>))
          .toList());
    }

    // Handle selected_entity from API response
    if (json.containsKey('selected_entity') &&
        json['selected_entity'] != null) {
      final selectedEntityJson =
          json['selected_entity'] as Map<String, dynamic>;
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
      timestamp: DateTime.now(),
    );
  }

  /// Load dashboard data from cache.
  /// Returns null if cache is invalid or missing.
  Future<DashboardData?> loadDashboardFromCache() async {
    try {
      final cachedData =
          await _storage.getString(AppConfig.cachedDashboardKey);
      if (cachedData == null) {
        return null;
      }

      final data = jsonDecode(cachedData);
      final cacheTime = DateTime.parse(data['timestamp']);

      // Check if cache is still valid (within 1 hour)
      if (DateTime.now().difference(cacheTime) >= AppConfig.cacheExpiration) {
        DebugLogger.logDashboard('Cache expired');
        return null;
      }

      final currentAssignments = (data['current_assignments'] as List)
          .map((json) => Assignment.fromJson(json))
          .toList();

      final pastAssignments = (data['past_assignments'] as List)
          .map((json) => Assignment.fromJson(json))
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

      DebugLogger.logDashboard('Saved dashboard to cache');
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error saving to cache: $e');
    }
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

  /// Update selected entity on backend via POST (legacy method, kept for compatibility).
  /// Posts entity selection to dashboard endpoint.
  /// Note: This is no longer needed since we pass entity directly to API, but kept for backward compatibility.
  Future<bool> updateSelectedEntity(Entity entity) async {
    DebugLogger.logDashboard('Updating selected entity via POST: ${entity.selectionKey}');

    // Save to local storage immediately
    await updateSelectedEntityStorage(entity);

    try {
      // Get CSRF token from dashboard page
      final csrfToken = await _getCsrfToken();
      if (csrfToken == null) {
        DebugLogger.logWarn(
            'DASHBOARD', 'Could not get CSRF token, entity selection not posted');
        return false;
      }

      DebugLogger.logDashboard('Posting entity selection to dashboard...');
      final response = await _api.post(
        AppConfig.dashboardEndpoint,
        body: {
          'entity_select': entity.selectionKey, // Format: "entity_type:entity_id"
          'csrf_token': csrfToken,
        },
        includeAuth: true,
        contentType: ApiService.contentTypeFormUrlEncoded,
      );

      // Access response body to ensure the request fully completes
      // This is important for redirects (302) to ensure session is updated
      final responseBody = response.body;
      DebugLogger.logDashboard(
          'Entity selection POST response: ${response.statusCode}, body length: ${responseBody.length}');

      // Both 200 (success) and 302 (redirect after update) indicate success
      final success = response.statusCode == 200 || response.statusCode == 302;

      if (success) {
        DebugLogger.logDashboard('Entity selection POST successful, session should be updated');
      } else {
        DebugLogger.logWarn('DASHBOARD', 'Entity selection POST failed with status ${response.statusCode}');
      }

      return success;
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error posting entity selection: $e');
      return false;
    }
  }

  /// Helper method to get CSRF token from dashboard page.
  Future<String?> _getCsrfToken() async {
    try {
      final response =
          await _api.get(AppConfig.dashboardEndpoint, includeAuth: true);
      if (response.statusCode == 200) {
        // Extract CSRF token from HTML response
        final csrfPattern = RegExp(
          r'<input[^>]*name=[\x22\x27]csrf_token[\x22\x27][^>]*value=[\x22\x27]([^\x22\x27]+)[\x22\x27]',
          caseSensitive: false,
        );
        final match = csrfPattern.firstMatch(response.body);
        if (match != null && match.groupCount >= 1) {
          return match.group(1);
        }
      }
    } catch (e) {
      DebugLogger.logWarn('DASHBOARD', 'Error getting CSRF token: $e');
    }
    return null;
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
