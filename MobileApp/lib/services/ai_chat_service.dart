import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../config/app_config.dart';
import '../utils/debug_logger.dart';
import 'ai_chat_exception.dart';
import 'api_service.dart';
import 'storage_service.dart';
import '../di/service_locator.dart';

class AiChatService {
  static final AiChatService _instance = AiChatService._internal();
  factory AiChatService() => _instance;
  AiChatService._internal();

  final ApiService _api = sl<ApiService>();
  final StorageService _storage = StorageService();

  static const String _aiTokenKey = 'ai_token_v1';

  Future<String?> getCachedToken() async {
    return _storage.getSecure(_aiTokenKey);
  }

  Future<void> clearToken() async {
    await _storage.deleteSecure(_aiTokenKey);
  }

  /// Fetch a short-lived AI token from Backoffice using the current session cookie.
  /// Returns null if not authenticated.
  Future<String?> fetchAndCacheToken() async {
    try {
      final resp = await _api.get(AppConfig.aiV2TokenEndpoint, includeAuth: true, useCache: false);
      if (resp.statusCode != 200) {
        DebugLogger.logWarn('AI', 'AI token request failed: HTTP ${resp.statusCode}');
        return null;
      }
      final data = jsonDecode(resp.body);
      final token = data['token']?.toString();
      if (token != null && token.isNotEmpty) {
        await _storage.setSecure(_aiTokenKey, token);
      }
      return token;
    } catch (e) {
      DebugLogger.logWarn('AI', 'AI token request error: $e');
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
    bool branchFromEdit = false,
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
      if (branchFromEdit) 'branch_from_edit': true,
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
    bool branchFromEdit = false,
  }) async {
    Future<Map<String, dynamic>> doChatRequest({required String? token}) async {
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
        branchFromEdit: branchFromEdit,
      );

      final resp = await _api.post(
        AppConfig.aiV2ChatEndpoint,
        includeAuth: isAuthenticated, // Only require auth if user is authenticated
        body: body,
        additionalHeaders: headers.isEmpty ? null : headers,
      );

      // Token might be expired/invalid: refresh once then retry the request.
      if (isAuthenticated && (resp.statusCode == 401 || resp.statusCode == 403)) {
        DebugLogger.logWarn(
          'AI',
          'Chat HTTP ${resp.statusCode}; refreshing token and retrying once',
        );
        try {
          await clearToken();
          final refreshed = await fetchAndCacheToken();
          if (refreshed != null && refreshed.isNotEmpty) {
            final retryResp = await _api.post(
              AppConfig.aiV2ChatEndpoint,
              includeAuth: isAuthenticated,
              body: body,
              additionalHeaders: {'Authorization': 'Bearer $refreshed'},
            );
            if (retryResp.statusCode == 200) {
              return _decodeChatSuccess(retryResp.body);
            }
            throw AiChatHttpException.fromResponse(retryResp.statusCode, retryResp.body);
          }
        } on AiChatHttpException {
          rethrow;
        } catch (e) {
          DebugLogger.logWarn('AI', 'Chat token refresh retry failed: $e');
        }
      }

      if (resp.statusCode != 200) {
        final error = AiChatHttpException.fromResponse(resp.statusCode, resp.body);
        DebugLogger.logWarn(
          'AI',
          'Chat HTTP ${resp.statusCode} '
          'type=${error.backendErrorType ?? '-'} message=${error.message}',
        );
        throw error;
      }

      return _decodeChatSuccess(resp.body);
    }

    Exception? lastError;
    for (int attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        final token = await getCachedToken();
        return await doChatRequest(token: token);
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

  Map<String, dynamic> _decodeChatSuccess(String body) {
    final decoded = jsonDecode(body);
    if (decoded is! Map) {
      throw const FormatException('Unexpected chat response format');
    }
    return Map<String, dynamic>.from(decoded);
  }

  /// Streaming via WebSocket (mobile-first)
  Future<WebSocketChannel> connectWebSocket() async {
    // Always attempt a fresh token fetch before opening the WS connection.
    // Using only a cached token risks sending a stale/expired JWT whose
    // rejection is delivered inside the WS protocol (not as an HTTP error),
    // bypassing the normal HTTP-level 401/403 retry logic.
    // If the fresh fetch fails (network issue, etc.), fall back to the cache.
    String? token = await fetchAndCacheToken();
    token ??= await getCachedToken();
    // Convert HTTP(S) URL to WebSocket URL (ws:// or wss://)
    final base = AppConfig.baseApiUrl;

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
      path: AppConfig.aiV2WsEndpoint,
    );

    // Debug log the WebSocket URL (remove in production)
    DebugLogger.logInfo('AI', 'Connecting to WebSocket: ${wsUri.toString()}');

    Future<WebSocketChannel> connectWithToken(String? t) async {
      return IOWebSocketChannel.connect(
        wsUri,
        headers: t != null && t.isNotEmpty ? {'Authorization': 'Bearer $t'} : null,
      );
    }

    try {
      return await connectWithToken(token);
    } catch (e) {
      // If auth failed, clear + refresh token once and retry.
      final msg = e.toString().toLowerCase();
      if (msg.contains('401') || msg.contains('403') || msg.contains('unauthorized') || msg.contains('forbidden')) {
        await clearToken();
        final refreshed = await fetchAndCacheToken();
        if (refreshed != null && refreshed.isNotEmpty) {
          return await connectWithToken(refreshed);
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
      AppConfig.aiV2ConversationsEndpoint,
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
          AppConfig.aiV2ConversationsEndpoint,
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
      '${AppConfig.aiV2ConversationsEndpoint}/$conversationId',
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
          '${AppConfig.aiV2ConversationsEndpoint}/$conversationId',
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
      '${AppConfig.aiV2ConversationsEndpoint}/$conversationId',
      includeAuth: true,
      additionalHeaders: headers.isEmpty ? null : headers,
    );
    final data = jsonDecode(resp.body);
    if (resp.statusCode == 401 || resp.statusCode == 403) {
      await clearToken();
      token = await fetchAndCacheToken();
      if (token != null && token.isNotEmpty) {
        final retryResp = await _api.delete(
          '${AppConfig.aiV2ConversationsEndpoint}/$conversationId',
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
      '${AppConfig.aiV2ConversationsEndpoint}/$conversationId/import',
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
          '${AppConfig.aiV2ConversationsEndpoint}/$conversationId/import',
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

  /// Like/dislike for a trace (same as web immersive chat).
  Future<bool> submitFeedback({required int traceId, required String rating}) async {
    final r = rating.trim().toLowerCase();
    if (r != 'like' && r != 'dislike') return false;
    try {
      String? token = await getCachedToken();
      final headers = <String, String>{};
      if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      Future<dynamic> postFeedbackRequest(String? t) async {
        final h = <String, String>{};
        if (t != null && t.isNotEmpty) h['Authorization'] = 'Bearer $t';
        return _api.post(
          AppConfig.aiV2FeedbackEndpoint,
          includeAuth: true,
          body: {'trace_id': traceId, 'rating': r},
          additionalHeaders: h.isEmpty ? null : h,
        );
      }

      var resp = await postFeedbackRequest(token);
      if (resp.statusCode == 401 || resp.statusCode == 403) {
        await clearToken();
        token = await fetchAndCacheToken();
        if (token != null && token.isNotEmpty) {
          resp = await postFeedbackRequest(token);
        }
      }
      return resp.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Clears server-side inflight progress (Backoffice immersive / chatbot.js parity).
  Future<void> clearConversationInflight(String conversationId) async {
    try {
      String? token = await getCachedToken();
      final headers = <String, String>{};
      if (token != null && token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      final resp = await _api.post(
        '${AppConfig.aiV2ConversationsEndpoint}/$conversationId/clear-inflight',
        includeAuth: true,
        body: const <String, dynamic>{},
        additionalHeaders: headers.isEmpty ? null : headers,
      );
      if (resp.statusCode == 401 || resp.statusCode == 403) {
        await clearToken();
        token = await fetchAndCacheToken();
        if (token != null && token.isNotEmpty) {
          await _api.post(
            '${AppConfig.aiV2ConversationsEndpoint}/$conversationId/clear-inflight',
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
