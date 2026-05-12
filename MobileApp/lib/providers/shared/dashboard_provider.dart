import 'package:flutter/foundation.dart';
import '../../models/shared/assignment.dart';
import '../../models/shared/dashboard_data.dart';
import '../../models/shared/entity.dart';
import '../../repositories/dashboard_repository.dart';
import '../../utils/debug_logger.dart';

/// Provider for dashboard state management.
/// Focuses on UI state (loading, error) and delegates data access to DashboardRepository.
class DashboardProvider with ChangeNotifier {
  final DashboardRepository _repository = DashboardRepository();

  List<Assignment> _currentAssignments = [];
  List<Assignment> _pastAssignments = [];
  List<Entity> _entities = [];
  Entity? _selectedEntity;
  bool _isLoading = false;
  String? _error;

  List<Assignment> get currentAssignments => _currentAssignments;
  List<Assignment> get pastAssignments => _pastAssignments;
  List<Entity> get entities => _entities;
  Entity? get selectedEntity => _selectedEntity;
  bool get isLoading => _isLoading;
  String? get error => _error;

  /// Load dashboard data.
  /// Loads from cache first (if not forcing refresh), then fetches from API.
  /// Optionally accepts entity to pass directly to API (bypasses session).
  Future<void> loadDashboard({
    bool forceRefresh = false,
    bool preserveSelectedEntity = false,
    Entity? entity,
  }) async {
    DebugLogger.logDashboard(
      'loadDashboard(forceRefresh=$forceRefresh, preserveEntity=$preserveSelectedEntity, '
      'entity=${entity?.selectionKey ?? "null"})',
    );

    // Load from cache first if available and not forcing refresh
    if (!forceRefresh) {
      final cachedData = await _repository.loadDashboardFromCache();
      if (cachedData != null) {
        DebugLogger.logDashboard(
          'Applied cached dashboard: current=${cachedData.currentAssignments.length}, '
          'past=${cachedData.pastAssignments.length}, entities=${cachedData.entities.length}',
        );
        _updateStateFromData(cachedData, preserveSelectedEntity: preserveSelectedEntity);
        notifyListeners();
      } else {
        DebugLogger.logDashboard('No valid cached dashboard (miss or expired)');
      }
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    // Fetch from API
    // Pass entity if provided (for direct selection) or if preserving and we have one
    final entityToPass = entity ?? (preserveSelectedEntity ? _selectedEntity : null);
    final data = await _repository.loadDashboardFromApi(
      entity: entityToPass,
    );

    if (data == null) {
      DebugLogger.logWarn(
        'DASHBOARD',
        'API returned null — keeping prior state (current=${_currentAssignments.length}, '
        'past=${_pastAssignments.length})',
      );
      // API call failed - check if we have cached data to display
      if (_currentAssignments.isEmpty && _pastAssignments.isEmpty) {
        _error =
            'Unable to load dashboard. Please check your connection and try again.';
      } else {
        _error = null; // Use cached data silently
      }
      _isLoading = false;
      notifyListeners();
      return;
    }

    // Update state with new data
    DebugLogger.logDashboard(
      'Dashboard API OK: current=${data.currentAssignments.length}, '
      'past=${data.pastAssignments.length}, entities=${data.entities.length}, '
      'selected=${data.selectedEntity?.selectionKey ?? "null"}',
    );
    _updateStateFromData(data, preserveSelectedEntity: preserveSelectedEntity);
    await _repository.saveDashboardToCache(data);
    _error = null;
    _isLoading = false;
    notifyListeners();
  }

  /// Re-applies dashboard data from on-device storage only (no API).
  ///
  /// Intended when the device is offline so pull-to-refresh does not block on
  /// network timeouts and retries. When [allowStale] is true, snapshots older
  /// than the normal cache TTL are still applied if present on disk.
  Future<void> refreshFromDiskOnly({bool allowStale = false}) async {
    DebugLogger.logDashboard(
      'refreshFromDiskOnly(allowStale=$allowStale)',
    );
    _isLoading = true;
    _error = null;
    notifyListeners();

    final cached = await _repository.loadDashboardFromCache(
      ignoreExpiry: allowStale,
    );
    if (cached != null) {
      _updateStateFromData(cached, preserveSelectedEntity: true);
      _error = null;
    } else if (_currentAssignments.isEmpty && _pastAssignments.isEmpty) {
      _error =
          'Unable to load dashboard. Please check your connection and try again.';
    }

    _isLoading = false;
    notifyListeners();
  }

  /// Update provider state from repository data.
  void _updateStateFromData(DashboardData data, {bool preserveSelectedEntity = false}) {
    _currentAssignments = data.currentAssignments;
    _pastAssignments = data.pastAssignments;
    _entities = data.entities;
    // Preserve current selection if flag is set, otherwise use API response or keep current
    if (preserveSelectedEntity) {
      // Keep the current selection - don't overwrite it
      // This ensures the user's selection persists during reload
      // However, if the API returned a different entity, log a warning
      // (This might indicate the session wasn't updated yet)
      if (data.selectedEntity != null && _selectedEntity != null) {
        if (data.selectedEntity!.entityType != _selectedEntity!.entityType ||
            data.selectedEntity!.entityId != _selectedEntity!.entityId) {
          DebugLogger.logWarn(
            'DASHBOARD',
            'API returned different selected entity (${data.selectedEntity!.selectionKey}) '
            'than what we set (${_selectedEntity!.selectionKey}). '
            'Session may not be updated yet, but keeping our selection.'
          );
        }
      }
    } else {
      _selectedEntity = data.selectedEntity ?? _selectedEntity;
    }
  }


  /// Load entities from cache.
  /// Entities are typically loaded as part of dashboard data.
  Future<void> loadEntities() async {
    _entities = await _repository.loadEntitiesFromCache();
    if (_entities.isNotEmpty && _selectedEntity == null) {
      _selectedEntity = await _repository.loadSelectedEntityFromStorage(_entities);
    }
    notifyListeners();
  }

  /// Select an entity and update backend.
  /// Updates UI immediately and syncs with backend.
  /// Clears cache and reloads dashboard with assignments for the new entity.
  Future<void> selectEntity(Entity entity) async {
    DebugLogger.logDashboard('Selecting entity: ${entity.selectionKey}');

    // Store previous entity to detect changes
    final previousEntity = _selectedEntity;
    final entityChanged = previousEntity == null ||
        previousEntity.entityType != entity.entityType ||
        previousEntity.entityId != entity.entityId;

    // Set the new entity immediately
    _selectedEntity = entity;

    // Notify listeners immediately so UI updates right away
    notifyListeners();

    // Clear cache when entity changes to ensure fresh data for new entity
    // But preserve the selected entity we just set
    if (entityChanged) {
      DebugLogger.logDashboard('Entity changed - clearing cache');
      _clearCachePreservingEntity();
    }

    // Set loading state while reloading
    _isLoading = true;
    _error = null;
    notifyListeners();

    // Update local storage for persistence
    await _repository.updateSelectedEntityStorage(entity);

    // Reload dashboard to get updated data for selected entity
    // Pass the entity directly to the API via query parameters
    // The API will use the entity from query params and update the session automatically
    await loadDashboard(forceRefresh: true, preserveSelectedEntity: true, entity: entity);

    DebugLogger.logDashboard(
        'After reload: selected entity is ${_selectedEntity?.selectionKey ?? "null"}, '
        'current assignments: ${_currentAssignments.length}, '
        'past assignments: ${_pastAssignments.length}');
  }

  /// Load selected entity from storage.
  /// Used when entities are loaded but selected entity is not yet set.
  Future<void> loadSelectedEntity() async {
    if (_entities.isEmpty) {
      return;
    }

    _selectedEntity =
        await _repository.loadSelectedEntityFromStorage(_entities);
    notifyListeners();
  }

  /// Clear all cached dashboard data.
  void clearCache() {
    _repository.clearCache();
    _currentAssignments = [];
    _pastAssignments = [];
    _entities = [];
    _selectedEntity = null;
    notifyListeners();
  }

  /// Clear cache but preserve the currently selected entity.
  /// Used when entity changes to ensure fresh data while keeping selection.
  void _clearCachePreservingEntity() {
    final preservedEntity = _selectedEntity;
    _repository.clearCache();
    _currentAssignments = [];
    _pastAssignments = [];
    _entities = [];
    // Restore the preserved entity
    _selectedEntity = preservedEntity;
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
