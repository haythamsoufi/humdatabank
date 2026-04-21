import 'dart:async';
import 'dart:io';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:device_info_plus/device_info_plus.dart';
import '../utils/debug_logger.dart';

/// Service for tracking app performance metrics
class PerformanceService {
  static final PerformanceService _instance = PerformanceService._internal();
  factory PerformanceService() => _instance;
  PerformanceService._internal();

  // Startup timing
  DateTime? _appStartTime;
  DateTime? _firstFrameTime;

  // Initialization timings
  final Map<String, DateTime> _initStartTimes = {};
  final Map<String, Duration> _initDurations = {};

  // Performance metrics
  final Map<String, Duration> _operationDurations = {};
  final List<PerformanceEvent> _events = [];

  bool _initialized = false;

  /// Initialize performance monitoring (call at app start)
  Future<void> initialize() async {
    if (_initialized) return;

    _appStartTime = DateTime.now();

    DebugLogger.logInfo('PERF', 'Performance monitoring initialized');
    _initialized = true;
  }

  /// Record app start time (called when main() starts)
  void recordAppStart() {
    _appStartTime = DateTime.now();
    _logEvent('app_start', 'Application started');
  }

  /// Record main initialization start
  void recordMainStart() {
    _logEvent('main_start', 'Main function started');
  }

  /// Record first frame rendered
  void recordFirstFrame() {
    _firstFrameTime = DateTime.now();
    if (_appStartTime != null) {
      final duration = _firstFrameTime!.difference(_appStartTime!);
      _logEvent('first_frame', 'First frame rendered', duration: duration);
      DebugLogger.logInfo(
          'PERF', 'First frame time: ${duration.inMilliseconds}ms');
    }
  }

  /// Start tracking an initialization phase
  void startInit(String phaseName) {
    _initStartTimes[phaseName] = DateTime.now();
    DebugLogger.logInfo('PERF', 'Starting initialization: $phaseName');
  }

  /// End tracking an initialization phase
  void endInit(String phaseName) {
    final startTime = _initStartTimes[phaseName];
    if (startTime != null) {
      final duration = DateTime.now().difference(startTime);
      _initDurations[phaseName] = duration;
      _logEvent('init_$phaseName', 'Initialization completed: $phaseName',
          duration: duration);
      DebugLogger.logInfo('PERF',
          'Completed initialization: $phaseName (${duration.inMilliseconds}ms)');
      _initStartTimes.remove(phaseName);
    }
  }

  /// Track operation duration
  Future<T> trackOperation<T>(
    String operationName,
    Future<T> Function() operation,
  ) async {
    final startTime = DateTime.now();
    try {
      final result = await operation();
      final duration = DateTime.now().difference(startTime);
      _operationDurations[operationName] = duration;
      _logEvent(
          'operation_$operationName', 'Operation completed: $operationName',
          duration: duration);
      if (duration.inMilliseconds > 1000) {
        DebugLogger.logWarn('PERF',
            'Slow operation detected: $operationName (${duration.inMilliseconds}ms)');
      }
      return result;
    } catch (e) {
      final duration = DateTime.now().difference(startTime);
      _logEvent('operation_$operationName', 'Operation failed: $operationName',
          duration: duration, error: e);
      rethrow;
    }
  }

  /// Track synchronous operation duration
  T trackSyncOperation<T>(
    String operationName,
    T Function() operation,
  ) {
    final startTime = DateTime.now();
    try {
      final result = operation();
      final duration = DateTime.now().difference(startTime);
      _operationDurations[operationName] = duration;
      _logEvent('sync_operation_$operationName',
          'Sync operation completed: $operationName',
          duration: duration);
      if (duration.inMilliseconds > 100) {
        DebugLogger.logWarn('PERF',
            'Slow sync operation detected: $operationName (${duration.inMilliseconds}ms)');
      }
      return result;
    } catch (e) {
      final duration = DateTime.now().difference(startTime);
      _logEvent('sync_operation_$operationName',
          'Sync operation failed: $operationName',
          duration: duration, error: e);
      rethrow;
    }
  }

  /// Get total startup time
  Duration? getTotalStartupTime() {
    if (_appStartTime == null || _firstFrameTime == null) return null;
    return _firstFrameTime!.difference(_appStartTime!);
  }

  /// Get initialization duration
  Duration? getInitDuration(String phaseName) {
    return _initDurations[phaseName];
  }

  /// Get operation duration
  Duration? getOperationDuration(String operationName) {
    return _operationDurations[operationName];
  }

  /// Get all initialization durations
  Map<String, Duration> getAllInitDurations() {
    return Map.unmodifiable(_initDurations);
  }

  /// Get all operation durations
  Map<String, Duration> getAllOperationDurations() {
    return Map.unmodifiable(_operationDurations);
  }

  /// Get performance summary
  Future<PerformanceSummary> getSummary() async {
    final packageInfo = await PackageInfo.fromPlatform();
    final deviceInfo = DeviceInfoPlugin();

    String deviceModel = 'Unknown';
    String osVersion = 'Unknown';

    try {
      if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        deviceModel = androidInfo.model;
        osVersion = 'Android ${androidInfo.version.release}';
      } else if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        deviceModel = iosInfo.model;
        osVersion = 'iOS ${iosInfo.systemVersion}';
      }
    } catch (e) {
      DebugLogger.logError('Failed to get device info: $e');
    }

    return PerformanceSummary(
      appVersion: packageInfo.version,
      buildNumber: packageInfo.buildNumber,
      deviceModel: deviceModel,
      osVersion: osVersion,
      totalStartupTime: getTotalStartupTime(),
      initDurations: getAllInitDurations(),
      operationDurations: getAllOperationDurations(),
      events: List.unmodifiable(_events),
    );
  }

  /// Log performance event
  void _logEvent(String eventType, String description,
      {Duration? duration, dynamic error}) {
    final event = PerformanceEvent(
      timestamp: DateTime.now(),
      eventType: eventType,
      description: description,
      duration: duration,
      error: error?.toString(),
    );
    _events.add(event);

    // Keep only last 100 events to prevent memory issues
    if (_events.length > 100) {
      _events.removeAt(0);
    }
  }

  /// Clear all performance data
  void clear() {
    _initStartTimes.clear();
    _initDurations.clear();
    _operationDurations.clear();
    _events.clear();
    _appStartTime = null;
    _firstFrameTime = null;
  }
}

/// Performance event record
class PerformanceEvent {
  final DateTime timestamp;
  final String eventType;
  final String description;
  final Duration? duration;
  final String? error;

  PerformanceEvent({
    required this.timestamp,
    required this.eventType,
    required this.description,
    this.duration,
    this.error,
  });

  @override
  String toString() {
    final durationStr =
        duration != null ? ' (${duration!.inMilliseconds}ms)' : '';
    final errorStr = error != null ? ' [ERROR: $error]' : '';
    return '[$timestamp] $eventType: $description$durationStr$errorStr';
  }
}

/// Performance summary
class PerformanceSummary {
  final String appVersion;
  final String buildNumber;
  final String deviceModel;
  final String osVersion;
  final Duration? totalStartupTime;
  final Map<String, Duration> initDurations;
  final Map<String, Duration> operationDurations;
  final List<PerformanceEvent> events;

  PerformanceSummary({
    required this.appVersion,
    required this.buildNumber,
    required this.deviceModel,
    required this.osVersion,
    this.totalStartupTime,
    required this.initDurations,
    required this.operationDurations,
    required this.events,
  });

  /// Print summary to debug logger
  void logSummary() {
    DebugLogger.logInfo('PERF', '=== Performance Summary ===');
    DebugLogger.logInfo('PERF', 'App Version: $appVersion ($buildNumber)');
    DebugLogger.logInfo('PERF', 'Device: $deviceModel');
    DebugLogger.logInfo('PERF', 'OS: $osVersion');

    if (totalStartupTime != null) {
      DebugLogger.logInfo(
          'PERF', 'Total Startup Time: ${totalStartupTime!.inMilliseconds}ms');
    }

    if (initDurations.isNotEmpty) {
      DebugLogger.logInfo('PERF', 'Initialization Durations:');
      initDurations.forEach((name, duration) {
        DebugLogger.logInfo('PERF', '  - $name: ${duration.inMilliseconds}ms');
      });
    }

    if (operationDurations.isNotEmpty) {
      DebugLogger.logInfo('PERF', 'Operation Durations:');
      operationDurations.forEach((name, duration) {
        DebugLogger.logInfo('PERF', '  - $name: ${duration.inMilliseconds}ms');
      });
    }

    DebugLogger.logInfo('PERF', 'Total Events: ${events.length}');
    DebugLogger.logInfo('PERF', '=== End Performance Summary ===');
  }

  /// Get summary as formatted string
  String getFormattedSummary() {
    final buffer = StringBuffer();
    buffer.writeln('=== Performance Summary ===');
    buffer.writeln('App Version: $appVersion ($buildNumber)');
    buffer.writeln('Device: $deviceModel');
    buffer.writeln('OS: $osVersion');

    if (totalStartupTime != null) {
      buffer
          .writeln('Total Startup Time: ${totalStartupTime!.inMilliseconds}ms');
    }

    if (initDurations.isNotEmpty) {
      buffer.writeln('\nInitialization Durations:');
      initDurations.forEach((name, duration) {
        buffer.writeln('  - $name: ${duration.inMilliseconds}ms');
      });
    }

    if (operationDurations.isNotEmpty) {
      buffer.writeln('\nOperation Durations:');
      operationDurations.forEach((name, duration) {
        buffer.writeln('  - $name: ${duration.inMilliseconds}ms');
      });
    }

    buffer.writeln('\nTotal Events: ${events.length}');
    buffer.writeln('=== End Performance Summary ===');
    return buffer.toString();
  }
}
