import 'dart:convert';

/// HTTP failure from the Backoffice AI endpoints, keeping the status code and
/// the backend's own `error_type` so the UI can tell failures apart instead of
/// collapsing everything into a generic "something went wrong".
class AiChatHttpException implements Exception {
  AiChatHttpException({
    required this.statusCode,
    required this.message,
    this.backendErrorType,
  });

  final int statusCode;
  final String message;

  /// `error_type` field from the JSON error body, when present.
  final String? backendErrorType;

  /// Builds an exception from a raw response, tolerating non-JSON bodies
  /// (HTML error pages from a proxy, empty bodies, etc.).
  factory AiChatHttpException.fromResponse(int statusCode, String body) {
    Map<String, dynamic>? json;
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map) json = Map<String, dynamic>.from(decoded);
    } catch (_) {
      json = null;
    }
    return AiChatHttpException(
      statusCode: statusCode,
      message: extractMessage(json, statusCode),
      backendErrorType: json?['error_type']?.toString(),
    );
  }

  /// Joins the human-readable fields of a backend error body.
  static String extractMessage(Map<String, dynamic>? data, int statusCode) {
    final parts = <String>[];
    if (data != null) {
      final error = data['error']?.toString();
      final message = data['message']?.toString();
      if (error != null && error.isNotEmpty && error != 'Chat failed') {
        parts.add(error);
      }
      if (message != null && message.isNotEmpty && message != error) {
        parts.add(message);
      }
      for (final key in const ['detail', 'details']) {
        final v = data[key]?.toString();
        if (v != null && v.isNotEmpty) parts.add(v);
      }
    }
    if (parts.isNotEmpty) return parts.join(' — ');
    if (statusCode == 401) return 'Your session has expired. Please sign in again.';
    if (statusCode == 403) return 'You do not have access to the AI assistant.';
    if (statusCode >= 500) {
      return 'The assistant is temporarily unavailable. Please try again later.';
    }
    if (statusCode >= 400) return 'Could not complete the request. Please try again.';
    return 'Chat failed';
  }

  /// Maps to the `AiChatMessage.errorType` values the chat UI understands.
  String get chatErrorType {
    final t = backendErrorType;
    if (t == 'quota_exceeded' || t == 'budget_exceeded' || statusCode == 429) {
      return 'quota_exceeded';
    }
    if (t == 'dlp_blocked' || t == 'dlp_requires_confirmation') return t!;
    if (statusCode == 401) return 'auth_required';
    if (statusCode == 403) return 'forbidden';
    if (statusCode == 408 || statusCode == 504) return 'timeout_error';
    if (statusCode == 502 || statusCode == 503) return 'service_unavailable';
    return 'server_error';
  }

  @override
  String toString() => message;
}
