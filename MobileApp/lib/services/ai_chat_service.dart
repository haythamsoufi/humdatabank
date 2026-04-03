import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../utils/debug_logger.dart';
import 'api_service.dart';
import 'storage_service.dart';

class AiChatService {
  static final AiChatService _instance = AiChatService._internal();
  factory AiChatService() => _instance;
  AiChatService._internal();

  final ApiService _api = ApiService();
  final StorageService _storage = StorageService();

  static const String _aiTokenKey = 'ai_token_v1';

  Future<String?> getCachedToken() async {
    return _storage.getSecure(_aiTokenKey);
  }

  Future<void> clearToken() async {
    await _storage.remove(_aiTokenKey);
  }

  /// Fetch a short-lived AI token from Backoffice using the current session cookie.
  /// Returns null if not authenticated.
  Future<String?> fetchAndCacheToken() async {
    try {
      final resp = await _api.get('/api/ai/v2/token', includeAuth: true, useCache: false);
      if (resp.statusCode != 200) return null;
      final data = jsonDecode(resp.body);
      final token = data['token']?.toString();
      if (token != null && token.isNotEmpty) {
        await _storage.setSecure(_aiTokenKey, token);
      }
      return token;
    } catch (_) {
      return null;
    }
  }

  Map<String, dynamic> _buildChatRequestBody({
    required String message,
    String? conversationId,
    String? clientMessageId,
    Map<String, dynamic>? pageContext,
    String preferredLanguage = 'en',
    List<Map<String, dynamic>>? conversationHistory,
    List<String>? sources,
  }) {
    return {
      'message': message,
      'conversation_id': conversationId,
      if (clientMessageId != null && clientMessageId.isNotEmpty) 'client_message_id': clientMessageId,
      'page_context': pageContext ?? {},
      'preferred_language': preferredLanguage,
      'client': 'mobile',
      if (conversationHistory != null && conversationHistory.isNotEmpty) 'conversationHistory': conversationHistory,
      if (sources != null && sources.isNotEmpty) 'sources': sources,
    };
  }

  /// Non-streaming HTTP fallback with retry logic
  Future<Map<String, dynamic>> sendMessageHttp({
    required String message,
    String? conversationId,
    String? clientMessageId,
    Map<String, dynamic>? pageContext,
    String preferredLanguage = 'en',
    List<Map<String, dynamic>>? conversationHistory,
    List<String>? sources,
    int maxRetries = 2,
    bool isAuthenticated = false,
  }) async {
    Future<Map<String, dynamic>> _doRequest({required String? token}) async {
      final headers = <String, String>{};
      if (token != null && token.isNotEmpty) {
        headers['Authorization'] = 'Bearer $token';
      }

      final body = _buildChatRequestBody(
        message: message,
        conversationId: conversationId,
        clientMessageId: clientMessageId,
        pageContext: pageContext,
        preferredLanguage: preferredLanguage,
        conversationHistory: conversationHistory,
        sources: sources,
      );

      final resp = await _api.post(
        '/api/ai/v2/chat',
        includeAuth: isAuthenticated, // Only require auth if user is authenticated
        body: body,
        additionalHeaders: headers.isEmpty ? null : headers,
      );

      final data = jsonDecode(resp.body);

      // Token might be expired/invalid: refresh once then retry the request.
      if (isAuthenticated && (resp.statusCode == 401 || resp.statusCode == 403)) {
        try {
          await clearToken();
          final refreshed = await fetchAndCacheToken();
          if (refreshed != null && refreshed.isNotEmpty) {
            final retryResp = await _api.post(
              '/api/ai/v2/chat',
              includeAuth: isAuthenticated,
              body: body,
              additionalHeaders: {'Authorization': 'Bearer $refreshed'},
            );
            final retryData = jsonDecode(retryResp.body);
            if (retryResp.statusCode == 200) {
              return Map<String, dynamic>.from(retryData);
            }
            final retryMsg = _extractErrorMessage(Map<String, dynamic>.from(retryData), retryResp.statusCode);
            throw Exception(retryMsg);
          }
        } catch (_) {
          // Fall through: we'll surface the original auth error.
        }
      }

      if (resp.statusCode != 200) {
        String errorMessage = _extractErrorMessage(Map<String, dynamic>.from(data), resp.statusCode);
        throw Exception(errorMessage);
      }

      return Map<String, dynamic>.from(data);
    }

    Exception? lastError;
    for (int attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        final token = await getCachedToken();
        return await _doRequest(token: token);
      } catch (e) {
        lastError = e is Exception ? e : Exception(e.toString());
        // Retry on network errors
        if (attempt < maxRetries && (e.toString().contains('SocketException') || e.toString().contains('TimeoutException'))) {
          await Future.delayed(Duration(milliseconds: 1000 * (attempt + 1)));
          continue;
        }
        rethrow;
      }
    }

    throw lastError ?? Exception('Chat failed after retries');
  }

  /// Streaming via WebSocket (mobile-first)
  Future<WebSocketChannel> connectWebSocket() async {
    String? token = await getCachedToken();
    // Best-effort: if we don't have a token yet but the app considers us authenticated,
    // try fetching one before opening the WS.
    token ??= await fetchAndCacheToken();
    // Convert HTTP(S) URL to WebSocket URL (ws:// or wss://)
    String base = AppConfig.baseApiUrl;

    // Parse the base URL to extract host and port properly
    final baseUri = Uri.parse(base);

    // Build WebSocket URI
    final wsScheme = baseUri.scheme == 'https' ? 'wss' : 'ws';
    // Use default ports: 80 for ws, 443 for wss (don't specify port if it's the default)
    int? wsPort = baseUri.port;
    if (wsPort == 80 && wsScheme == 'ws') wsPort = null;
    if (wsPort == 443 && wsScheme == 'wss') wsPort = null;

    final wsUri = Uri(
      scheme: wsScheme,
      host: baseUri.host,
      port: wsPort,
      path: '/api/ai/v2/ws',
    );

    // Debug log the WebSocket URL (remove in production)
    DebugLogger.logInfo('AI', 'Connecting to WebSocket: ${wsUri.toString()}');

    Future<WebSocketChannel> _connectWith(String? t) async {
      return IOWebSocketChannel.connect(
        wsUri,
        headers: t != null && t.isNotEmpty ? {'Authorization': 'Bearer $t'} : null,
      );
    }

    try {
      return await _connectWith(token);
    } catch (e) {
      // If auth failed, clear + refresh token once and retry.
      final msg = e.toString().toLowerCase();
      if (msg.contains('401') || msg.contains('403') || msg.contains('unauthorized') || msg.contains('forbidden')) {
        await clearToken();
        final refreshed = await fetchAndCacheToken();
        if (refreshed != null && refreshed.isNotEmpty) {
          return await _connectWith(refreshed);
        }
      }
      rethrow;
    }
  }

  /// List conversations (logged-in only)
  Future<List<dynamic>> listConversations() async {
    String? token = await getCachedToken();
    final headers = <String, String>{};
    if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
    final resp = await _api.get(
      '/api/ai/v2/conversations',
      includeAuth: true,
      useCache: false,
      queryParams: {'limit': '50'},
      additionalHeaders: headers.isEmpty ? null : headers,
    );
    final data = jsonDecode(resp.body);
    if (resp.statusCode == 401 || resp.statusCode == 403) {
      await clearToken();
      token = await fetchAndCacheToken();
      if (token != null && token.isNotEmpty) {
        final retryResp = await _api.get(
          '/api/ai/v2/conversations',
          includeAuth: true,
          useCache: false,
          queryParams: {'limit': '50'},
          additionalHeaders: {'Authorization': 'Bearer $token'},
        );
        final retryData = jsonDecode(retryResp.body);
        if (retryResp.statusCode == 200) {
          return (retryData['conversations'] as List?) ?? [];
        }
        throw Exception(retryData['error']?.toString() ?? 'Failed to load conversations');
      }
    }
    if (resp.statusCode != 200) {
      throw Exception(data['error']?.toString() ?? 'Failed to load conversations');
    }
    return (data['conversations'] as List?) ?? [];
  }

  Future<Map<String, dynamic>> getConversation(String conversationId) async {
    String? token = await getCachedToken();
    final headers = <String, String>{};
    if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
    final resp = await _api.get(
      '/api/ai/v2/conversations/$conversationId',
      includeAuth: true,
      useCache: false,
      queryParams: {'limit': '200'},
      additionalHeaders: headers.isEmpty ? null : headers,
    );
    final data = jsonDecode(resp.body);
    if (resp.statusCode == 401 || resp.statusCode == 403) {
      await clearToken();
      token = await fetchAndCacheToken();
      if (token != null && token.isNotEmpty) {
        final retryResp = await _api.get(
          '/api/ai/v2/conversations/$conversationId',
          includeAuth: true,
          useCache: false,
          queryParams: {'limit': '200'},
          additionalHeaders: {'Authorization': 'Bearer $token'},
        );
        final retryData = jsonDecode(retryResp.body);
        if (retryResp.statusCode == 200) {
          return Map<String, dynamic>.from(retryData);
        }
        throw Exception(retryData['error']?.toString() ?? 'Failed to load conversation');
      }
    }
    if (resp.statusCode != 200) {
      throw Exception(data['error']?.toString() ?? 'Failed to load conversation');
    }
    return Map<String, dynamic>.from(data);
  }

  /// Delete a conversation (logged-in only)
  Future<void> deleteConversation(String conversationId) async {
    String? token = await getCachedToken();
    final headers = <String, String>{};
    if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
    final resp = await _api.delete(
      '/api/ai/v2/conversations/$conversationId',
      includeAuth: true,
      additionalHeaders: headers.isEmpty ? null : headers,
    );
    final data = jsonDecode(resp.body);
    if (resp.statusCode == 401 || resp.statusCode == 403) {
      await clearToken();
      token = await fetchAndCacheToken();
      if (token != null && token.isNotEmpty) {
        final retryResp = await _api.delete(
          '/api/ai/v2/conversations/$conversationId',
          includeAuth: true,
          additionalHeaders: {'Authorization': 'Bearer $token'},
        );
        final retryData = jsonDecode(retryResp.body);
        if (retryResp.statusCode == 200 || retryResp.statusCode == 204) return;
        throw Exception(retryData['error']?.toString() ?? 'Failed to delete conversation');
      }
    }
    if (resp.statusCode != 200 && resp.statusCode != 204) {
      throw Exception(data['error']?.toString() ?? 'Failed to delete conversation');
    }
  }

  /// Import offline/local-only messages into a server conversation (logged-in only).
  /// This is used to "merge + keep offline messages" across devices after login.
  Future<void> importConversationMessages({
    required String conversationId,
    required List<Map<String, dynamic>> messages,
  }) async {
    String? token = await getCachedToken();
    final headers = <String, String>{};
    if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';

    final resp = await _api.post(
      '/api/ai/v2/conversations/$conversationId/import',
      includeAuth: true,
      body: {
        'messages': messages,
        'client': 'mobile',
      },
      additionalHeaders: headers.isEmpty ? null : headers,
    );

    final data = jsonDecode(resp.body);
    if (resp.statusCode == 401 || resp.statusCode == 403) {
      await clearToken();
      token = await fetchAndCacheToken();
      if (token != null && token.isNotEmpty) {
        final retryResp = await _api.post(
          '/api/ai/v2/conversations/$conversationId/import',
          includeAuth: true,
          body: {
            'messages': messages,
            'client': 'mobile',
          },
          additionalHeaders: {'Authorization': 'Bearer $token'},
        );
        final retryData = jsonDecode(retryResp.body);
        if (retryResp.statusCode == 200) return;
        throw Exception(retryData['error']?.toString() ?? 'Failed to import conversation messages');
      }
    }
    if (resp.statusCode != 200) {
      throw Exception(data['error']?.toString() ?? 'Failed to import conversation messages');
    }
  }

  /// Extract detailed error message from API response
  String _extractErrorMessage(Map<String, dynamic> data, int statusCode) {
    // Try multiple fields that might contain error information
    String? error = data['error']?.toString();
    String? message = data['message']?.toString();
    String? detail = data['detail']?.toString();
    String? details = data['details']?.toString();

    // Build error message with available information
    List<String> parts = [];

    if (error != null && error.isNotEmpty && error != 'Chat failed') {
      parts.add(error);
    }

    if (message != null && message.isNotEmpty && message != error) {
      parts.add(message);
    }

    if (detail != null && detail.isNotEmpty) {
      parts.add(detail);
    }

    if (details != null && details.isNotEmpty) {
      parts.add(details);
    }

    // If we have detailed info, use it
    if (parts.isNotEmpty) {
      String fullMessage = parts.join(' - ');
      // Include status code for server errors
      if (statusCode >= 500) {
        return 'Server error ($statusCode): $fullMessage';
      }
      return fullMessage;
    }

    // Fallback with status code
    if (statusCode >= 500) {
      return 'Server error ($statusCode): Chat failed. Please try again later.';
    } else if (statusCode >= 400) {
      return 'Error ($statusCode): Chat failed';
    }

    return 'Chat failed';
  }

  /// Like/dislike for a trace (same as web immersive chat).
  Future<bool> submitFeedback({required int traceId, required String rating}) async {
    final r = rating.trim().toLowerCase();
    if (r != 'like' && r != 'dislike') return false;
    try {
      String? token = await getCachedToken();
      final headers = <String, String>{};
      if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      Future<dynamic> _post(String? t) async {
        final h = <String, String>{};
        if (t != null && t.isNotEmpty) h['Authorization'] = 'Bearer $t';
        return _api.post(
          '/api/ai/v2/feedback',
          includeAuth: true,
          body: {'trace_id': traceId, 'rating': r},
          additionalHeaders: h.isEmpty ? null : h,
        );
      }

      var resp = await _post(token);
      if (resp.statusCode == 401 || resp.statusCode == 403) {
        await clearToken();
        token = await fetchAndCacheToken();
        if (token != null && token.isNotEmpty) {
          resp = await _post(token);
        }
      }
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Raw JSON export (`GET /api/ai/v2/conversations/:id/export`).
  Future<Uint8List?> exportConversationJsonBytes(String conversationId) async {
    try {
      String? token = await getCachedToken();
      Future<dynamic> _get(String? t) async {
        final h = <String, String>{};
        if (t != null && t.isNotEmpty) h['Authorization'] = 'Bearer $t';
        return _api.get(
          '/api/ai/v2/conversations/$conversationId/export',
          includeAuth: true,
          useCache: false,
          additionalHeaders: h.isEmpty ? null : h,
        );
      }

      var resp = await _get(token);
      if (resp.statusCode == 401 || resp.statusCode == 403) {
        await clearToken();
        token = await fetchAndCacheToken();
        if (token != null && token.isNotEmpty) {
          resp = await _get(token);
        }
      }
      if (resp.statusCode == 200 && resp.bodyBytes.isNotEmpty) {
        return resp.bodyBytes;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  /// Clears server-side inflight progress (Backoffice immersive / chatbot.js parity).
  Future<void> clearConversationInflight(String conversationId) async {
    try {
      String? token = await getCachedToken();
      final headers = <String, String>{};
      if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      final resp = await _api.post(
        '/api/ai/v2/conversations/$conversationId/clear-inflight',
        includeAuth: true,
        body: const <String, dynamic>{},
        additionalHeaders: headers.isEmpty ? null : headers,
      );
      if (resp.statusCode == 401 || resp.statusCode == 403) {
        await clearToken();
        token = await fetchAndCacheToken();
        if (token != null && token.isNotEmpty) {
          await _api.post(
            '/api/ai/v2/conversations/$conversationId/clear-inflight',
            includeAuth: true,
            body: const <String, dynamic>{},
            additionalHeaders: {'Authorization': 'Bearer $token'},
          );
        }
      }
    } catch (_) {
      // best-effort
    }
  }
}
