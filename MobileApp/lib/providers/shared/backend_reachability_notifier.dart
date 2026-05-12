import 'dart:async';

import 'package:flutter/foundation.dart';

import '../../services/backend_reachability_service.dart';
import '../../services/backend_reachability_ui_callback.dart';
import '../../services/connectivity_service.dart';

/// Drives a banner when the device is "online" but the primary backoffice host
/// is unreachable (see [BackendReachabilityService]).
class BackendReachabilityNotifier with ChangeNotifier {
  BackendReachabilityNotifier();

  Timer? _pollTimer;
  bool _showServerUnreachable = false;

  bool get showServerUnreachableBanner => _showServerUnreachable;

  void start() {
    BackendReachabilityUiCallback.bump = _recompute;
    _pollTimer?.cancel();
    // Clears the banner when the defer window expires without new traffic.
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) => _recompute());
    _recompute();
  }

  void _recompute() {
    final online = ConnectivityService().isOnline;
    final backendDown =
        BackendReachabilityService().shouldDeferNonCriticalRemote;
    final next = online && backendDown;
    if (next != _showServerUnreachable) {
      _showServerUnreachable = next;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    BackendReachabilityUiCallback.bump = null;
    _pollTimer?.cancel();
    super.dispose();
  }
}
