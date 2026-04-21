import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../services/backend_reachability_service.dart';
import '../services/connectivity_service.dart';

/// True when we should skip aggressive remote work (list refresh, analytics POST).
///
/// Combines:
/// - **Radio / OS connectivity** ([ConnectivityService]: only
///   [NetworkStatus.connected] counts as online).
/// - **Primary backend reachability**: recent transport failures to
///   [AppConfig.backendUrl] (e.g. dev server stopped while Wi‑Fi stays on).
///
/// See [BackendReachabilityService], updated from [ApiService] on real outcomes.
bool get shouldDeferRemoteFetch =>
    !ConnectivityService().isOnline ||
    BackendReachabilityService().shouldDeferNonCriticalRemote;

/// TCP/HTTP failures where the radio may still report "connected" (e.g. dev
/// server stopped, flaky Wi‑Fi, VPN). Used to avoid treating these as hard
/// auth failures and to downgrade noisy analytics logs.
bool isTransientBackendFailure(Object error) {
  if (error is SocketException) return true;
  if (error is TimeoutException) return true;
  if (error is http.ClientException) return true;
  final msg = error.toString().toLowerCase();
  if (msg.contains('connection closed')) return true;
  if (msg.contains('connection reset')) return true;
  if (msg.contains('connection refused')) return true;
  if (msg.contains('failed host lookup')) return true;
  if (msg.contains('network is unreachable')) return true;
  if (msg.contains('broken pipe')) return true;
  return false;
}
