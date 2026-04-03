import 'package:flutter/foundation.dart';
import 'dart:async';
import '../../services/connectivity_service.dart';
import '../../services/offline_queue_service.dart';
import '../../services/offline_cache_service.dart';
import '../../services/api_service.dart';
import '../../services/storage_service.dart';
import '../../utils/debug_logger.dart';
import 'package:http/http.dart' as http;
import '../../services/user_scope_service.dart';

/// Provider for managing offline state and sync operations
class OfflineProvider with ChangeNotifier {
  final ConnectivityService _connectivity = ConnectivityService();
  final OfflineQueueService _queueService = OfflineQueueService();
  final OfflineCacheService _cacheService = OfflineCacheService();
  final ApiService _apiService = ApiService();
  final StorageService _storage = StorageService();
  final UserScopeService _scopeService = UserScopeService();

  bool _isOnline = true;
  bool _isSyncing = false;
  int _queuedRequestsCount = 0;
  DateTime? _lastSynced;
  StreamSubscription<NetworkStatus>? _connectivitySubscription;
  Timer? _syncTimer;

  // Getters
  bool get isOnline => _isOnline;
  bool get isOffline => !_isOnline;
  bool get isSyncing => _isSyncing;
  int get queuedRequestsCount => _queuedRequestsCount;
  DateTime? get lastSynced => _lastSynced;

  String? get lastSyncedFormatted {
    if (_lastSynced == null) return null;
    final now = DateTime.now();
    final difference = now.difference(_lastSynced!);

    if (difference.inMinutes < 1) {
      return 'Just now';
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes}m ago';
    } else if (difference.inHours < 24) {
      return '${difference.inHours}h ago';
    } else {
      return '${difference.inDays}d ago';
    }
  }

  /// Initialize offline provider
  Future<void> initialize() async {
    try {
      // Initialize connectivity service
      await _connectivity.initialize();

      // Get initial status
      _isOnline = _connectivity.isOnline;
      await _updateQueuedCount();
      await _loadLastSynced();

      // Listen to connectivity changes
      _connectivitySubscription = _connectivity.networkStatusStream.listen(
        _onConnectivityChanged,
        onError: (error) {
          DebugLogger.logError('Connectivity stream error: $error');
        },
      );

      // Start periodic sync check
      _startSyncTimer();

      notifyListeners();
      DebugLogger.logInfo('OFFLINE_PROVIDER', 'Offline provider initialized');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize offline provider: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Handle connectivity changes
  void _onConnectivityChanged(NetworkStatus status) {
    final wasOnline = _isOnline;
    _isOnline = status == NetworkStatus.connected;

    if (!wasOnline && _isOnline) {
      // Just came online - trigger sync
      DebugLogger.logInfo(
          'OFFLINE_PROVIDER', 'Connection restored - triggering sync');
      syncQueuedRequests();
    }

    notifyListeners();
    DebugLogger.logInfo('OFFLINE_PROVIDER',
        'Network status changed: ${_isOnline ? "Online" : "Offline"}');
  }

  /// Update queued requests count
  Future<void> _updateQueuedCount() async {
    try {
      final ownerKey = await _scopeService.getScope(includeAuth: true);
      _queuedRequestsCount =
          await _queueService.getQueuedCount(ownerKey: ownerKey);
      notifyListeners();
    } catch (e) {
      DebugLogger.logError('Failed to update queued count: $e');
    }
  }

  /// Load last synced timestamp
  Future<void> _loadLastSynced() async {
    try {
      final timestampStr = await _storage.getString('last_synced_timestamp');
      if (timestampStr != null) {
        _lastSynced = DateTime.parse(timestampStr);
        notifyListeners();
      }
    } catch (e) {
      DebugLogger.logError('Failed to load last synced timestamp: $e');
    }
  }

  /// Save last synced timestamp
  Future<void> _saveLastSynced() async {
    try {
      _lastSynced = DateTime.now();
      await _storage.setString(
          'last_synced_timestamp', _lastSynced!.toIso8601String());
      notifyListeners();
    } catch (e) {
      DebugLogger.logError('Failed to save last synced timestamp: $e');
    }
  }

  /// Start periodic sync timer
  void _startSyncTimer() {
    _syncTimer?.cancel();
    _syncTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      if (_isOnline && _queuedRequestsCount > 0) {
        syncQueuedRequests();
      }
    });
  }

  /// Sync queued requests when online
  Future<void> syncQueuedRequests({bool showProgress = true}) async {
    if (_isSyncing) {
      DebugLogger.logInfo('OFFLINE_PROVIDER', 'Sync already in progress');
      return;
    }

    if (!_isOnline) {
      DebugLogger.logInfo('OFFLINE_PROVIDER', 'Cannot sync - offline');
      return;
    }

    _isSyncing = showProgress;
    notifyListeners();

    try {
      final ownerKey = await _scopeService.getScope(includeAuth: true);
      final queuedRequests =
          await _queueService.getQueuedRequests(ownerKey: ownerKey);
      DebugLogger.logInfo('OFFLINE_PROVIDER',
          'Syncing ${queuedRequests.length} queued requests');

      int successCount = 0;
      int failureCount = 0;

      for (final request in queuedRequests) {
        if (!_queueService.shouldRetry(request)) {
          DebugLogger.logInfo('OFFLINE_PROVIDER',
              'Skipping request ${request.id} - exceeded max retries');
          continue;
        }

        try {
          // Execute the queued request
          await _executeQueuedRequest(request);
          await _queueService.removeRequest(request.id!);
          successCount++;
          DebugLogger.logInfo(
              'OFFLINE_PROVIDER', 'Successfully synced request ${request.id}');
        } catch (e) {
          failureCount++;
          final newRetryCount = request.retryCount + 1;
          await _queueService.updateRetryCount(
            request.id!,
            newRetryCount,
            errorMessage: e.toString(),
          );
          DebugLogger.logError('Failed to sync request ${request.id}: $e');

          if (newRetryCount >= _queueService.maxRetries) {
            DebugLogger.logInfo('OFFLINE_PROVIDER',
                'Request ${request.id} exceeded max retries - will be removed');
            await _queueService.removeRequest(request.id!);
          }
        }
      }

      // Clean up old requests
      await _queueService.clearOldRequests();

      // Update counts
      await _updateQueuedCount();

      if (successCount > 0) {
        await _saveLastSynced();
      }

      DebugLogger.logInfo('OFFLINE_PROVIDER',
          'Sync completed: $successCount success, $failureCount failures');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to sync queued requests: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    } finally {
      _isSyncing = false;
      notifyListeners();
    }
  }

  /// Execute a queued request
  Future<void> _executeQueuedRequest(QueuedRequest request) async {
    http.Response response;

    switch (request.method.toUpperCase()) {
      case 'GET':
        response = await _apiService.get(
          request.endpoint,
          queryParams: request.queryParams,
          includeAuth: request.includeAuth,
        );
        break;
      case 'POST':
        response = await _apiService.post(
          request.endpoint,
          body: request.body,
          includeAuth: request.includeAuth,
          contentType: request.contentType ?? ApiService.contentTypeJson,
        );
        break;
      case 'PUT':
        response = await _apiService.put(
          request.endpoint,
          body: request.body,
          includeAuth: request.includeAuth,
        );
        break;
      case 'DELETE':
        response = await _apiService.delete(
          request.endpoint,
          includeAuth: request.includeAuth,
        );
        break;
      default:
        throw Exception('Unsupported HTTP method: ${request.method}');
    }

    // Check if response was successful
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw Exception('HTTP ${response.statusCode}: ${response.body}');
    }
  }

  /// Manually trigger sync
  Future<void> manualSync() async {
    await syncQueuedRequests(showProgress: true);
  }

  /// Dispose resources
  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    _syncTimer?.cancel();
    _connectivity.dispose();
    super.dispose();
  }
}
