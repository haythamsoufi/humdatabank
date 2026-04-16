import '../config/app_config.dart';
import 'backend_reachability_ui_callback.dart';
import '../utils/debug_logger.dart' show DebugLogger, LogLevel;

/// Tracks whether recent HTTP traffic to the **primary backoffice** succeeded.
///
/// Wi‑Fi/cellular can stay "connected" while the dev server, VPN, or tunnel is
/// down. [ConnectivityService] alone cannot detect that; this service learns
/// from real [ApiService] outcomes to the host in [AppConfig.backendUrl].
class BackendReachabilityService {
  BackendReachabilityService._internal();
  static final BackendReachabilityService _instance =
      BackendReachabilityService._internal();
  factory BackendReachabilityService() => _instance;

  DateTime? _deferNonCriticalUntil;

  /// After transport failures to the primary backend, skip optional traffic
  /// (pull-to-refresh, screen-view POST) briefly so the UI does not spin.
  static const _deferDuration = Duration(seconds: 45);

  Uri? _primaryOrigin;

  Uri _parsePrimaryOrigin() {
    if (_primaryOrigin != null) return _primaryOrigin!;
    try {
      final u = Uri.parse(AppConfig.backendUrl);
      _primaryOrigin = Uri(
        scheme: u.scheme,
        host: u.host,
        port: u.hasPort ? u.port : null,
      );
      return _primaryOrigin!;
    } catch (_) {
      _primaryOrigin = Uri();
      return _primaryOrigin!;
    }
  }

  /// True when [uri] targets the configured backoffice host/port.
  bool matchesPrimaryBackend(Uri uri) {
    final p = _parsePrimaryOrigin();
    if (!p.hasScheme || p.host.isEmpty) return false;
    return uri.host.toLowerCase() == p.host.toLowerCase() && uri.port == p.port;
  }

  /// Call after a **live** 2xx response from the primary backend (not cache-only).
  void recordPrimaryBackendSuccess() {
    _deferNonCriticalUntil = null;
    BackendReachabilityUiCallback.bumpUi();
  }

  /// Call after transport failure to the primary backend (timeouts, connection
  /// closed, etc.), including when a cached body is returned as fallback.
  void recordPrimaryBackendTransportFailure() {
    _deferNonCriticalUntil = DateTime.now().add(_deferDuration);
    DebugLogger.log(
      'BACKEND_REACH',
      'Primary backend unreachable — deferring non-critical remote work '
      'until ${_deferNonCriticalUntil!.toIso8601String()}',
      level: LogLevel.debug,
    );
    BackendReachabilityUiCallback.bumpUi();
  }

  /// When true, optional API work should no-op quickly (see [shouldDeferRemoteFetch]).
  bool get shouldDeferNonCriticalRemote {
    final until = _deferNonCriticalUntil;
    if (until == null) return false;
    if (DateTime.now().isBefore(until)) return true;
    _deferNonCriticalUntil = null;
    return false;
  }
}
