import 'package:flutter/foundation.dart';

/// Shared HTTP timeouts for [ApiService] and [DioClient] JSON API traffic.
@immutable
class ApiTimeouts {
  const ApiTimeouts._();

  static const Duration connect = Duration(seconds: 10);
  static const Duration receive = Duration(seconds: 30);
  static const Duration send = Duration(seconds: 30);

  /// Default for [ApiService.get] when no per-call [timeout] is passed.
  static const Duration defaultGet = receive;
}
