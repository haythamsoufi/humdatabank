import 'dart:async';
import 'package:connectivity_plus/connectivity_plus.dart';
import '../utils/debug_logger.dart';

enum NetworkStatus {
  connected,
  disconnected,
  connecting,
}

class ConnectivityService {
  static final ConnectivityService _instance = ConnectivityService._internal();
  factory ConnectivityService() => _instance;
  ConnectivityService._internal();

  final Connectivity _connectivity = Connectivity();
  StreamController<NetworkStatus>? _networkStatusController;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  NetworkStatus _currentStatus = NetworkStatus.connecting;
  bool _initialized = false;

  // Get stream of network status changes
  Stream<NetworkStatus> get networkStatusStream {
    _networkStatusController ??= StreamController<NetworkStatus>.broadcast();
    return _networkStatusController!.stream;
  }

  // Get current network status
  NetworkStatus get currentStatus => _currentStatus;

  // Check if currently online
  bool get isOnline => _currentStatus == NetworkStatus.connected;

  // Check if currently offline
  bool get isOffline => _currentStatus == NetworkStatus.disconnected;

  /// Initialize connectivity monitoring
  Future<void> initialize() async {
    if (_initialized) {
      DebugLogger.logInfo(
          'CONNECTIVITY', 'Connectivity service already initialized');
      return;
    }

    DebugLogger.logInfo('CONNECTIVITY', 'Initializing connectivity service...');

    try {
      // Check initial connectivity status
      await _checkConnectivity();

      // Listen for connectivity changes
      _connectivitySubscription = _connectivity.onConnectivityChanged.listen(
        _onConnectivityChanged,
        onError: (error) {
          DebugLogger.logError('Connectivity stream error: $error');
        },
      );

      _initialized = true;
      DebugLogger.logInfo(
          'CONNECTIVITY', 'Connectivity service initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize connectivity service: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      _currentStatus = NetworkStatus.disconnected;
      _notifyStatusChange();
    }
  }

  /// Check current connectivity status
  Future<void> _checkConnectivity() async {
    try {
      final results = await _connectivity.checkConnectivity();
      final wasOnline = isOnline;

      // Determine if we have any active connection
      final hasConnection =
          results.any((result) => result != ConnectivityResult.none);

      if (hasConnection) {
        // Additional check: try to reach the internet
        // For now, we'll assume WiFi/Mobile means connected
        // In production, you might want to ping a specific server
        _currentStatus = NetworkStatus.connected;
      } else {
        _currentStatus = NetworkStatus.disconnected;
      }

      if (wasOnline != isOnline) {
        _notifyStatusChange();
        DebugLogger.logInfo('CONNECTIVITY',
            'Network status changed: ${isOnline ? "Online" : "Offline"}');
      }
    } catch (e) {
      DebugLogger.logError('Error checking connectivity: $e');
      _currentStatus = NetworkStatus.disconnected;
      _notifyStatusChange();
    }
  }

  /// Handle connectivity changes
  void _onConnectivityChanged(List<ConnectivityResult> results) {
    final wasOnline = isOnline;

    // Determine if we have any active connection
    final hasConnection =
        results.any((result) => result != ConnectivityResult.none);

    if (hasConnection) {
      // Set to connecting first, then check actual internet access
      _currentStatus = NetworkStatus.connecting;
      _notifyStatusChange();

      // Wait a bit and check if connection is actually working
      Future.delayed(const Duration(seconds: 1), () {
        _checkConnectivity();
      });
    } else {
      _currentStatus = NetworkStatus.disconnected;
      _notifyStatusChange();
    }

    if (wasOnline != isOnline) {
      DebugLogger.logInfo('CONNECTIVITY',
          'Network status changed: ${isOnline ? "Online" : "Offline"}');
    }
  }

  /// Notify listeners of status change
  void _notifyStatusChange() {
    _networkStatusController?.add(_currentStatus);
  }

  /// Manually check connectivity (useful for retry scenarios)
  Future<bool> checkConnection() async {
    await _checkConnectivity();
    return isOnline;
  }

  /// Dispose resources
  void dispose() {
    _connectivitySubscription?.cancel();
    _networkStatusController?.close();
    _networkStatusController = null;
    _connectivitySubscription = null;
    _initialized = false;
    DebugLogger.logInfo('CONNECTIVITY', 'Connectivity service disposed');
  }
}
