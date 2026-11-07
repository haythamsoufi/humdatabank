import 'package:flutter/foundation.dart';

/// Shared HTTP timeouts for [ApiService] and [DioClient] JSON API traffic.
@immutable
class ApiTimeouts {
  const ApiTimeouts._();

  static const Duration connect = Duration(seconds: 10);
  static const Duration receive = Duration(seconds: 30);
  static const Duration send = Duration(seconds: 30);

  /// Non-streaming AI chat turns run the whole agent loop server-side (tool calls, LLM turns,
  /// answer verification), which routinely exceeds [receive]. Must stay above the backend's
  /// `AI_AGENT_TIMEOUT_SECONDS` so a slow-but-healthy run is never abandoned and re-submitted.
  static const Duration aiChat = Duration(seconds: 330);

  /// Default for [ApiService.get] when no per-call [timeout] is passed.
  static const Duration defaultGet = receive;
}
