import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';

import '../../models/shared/ai_chat.dart';
import '../../services/ai_chat_service.dart';
import '../../services/ai_chat_persistence_service.dart';
import '../../services/storage_service.dart';
import '../../utils/ai_chat_structured_coerce.dart';
import '../../utils/debug_logger.dart';

class AiChatProvider with ChangeNotifier {
  final AiChatService _service = AiChatService();
  final AiChatPersistenceService _persistence = AiChatPersistenceService();
  final Uuid _uuid = const Uuid();

  bool _isLoading = false;
  bool _isStreaming = false;
  String? _error;
  String? _errorType; // 'quota_exceeded' or null
  double? _retryDelay; // seconds
  String? _conversationId;
  String? _failedMessage; // Message that failed due to quota error

  List<AiChatMessage> _messages = [];
  List<AiConversationSummary> _conversations = [];

  WebSocketChannel? _channel;
  StreamSubscription? _wsSub;

  // Prevent overlapping server syncs per conversation
  final Set<String> _syncInFlight = {};

  final StorageService _storage = StorageService();

  /// Agent/tool steps while streaming (WS `step` / `step_detail`, same as Backoffice chatbot).
  List<AiChatAgentStep> _agentSteps = [];
  String? _lastPreparingQueryDetail;
  bool _wsUserCancelled = false;

  bool _policyAcknowledged = false;
  List<String> _sourcesSelected = ['historical', 'system_documents', 'upr_documents'];
  String _preferredLanguageCode = 'en';
  String? _streamStatusHint;
  bool _inflightRestoreActive = false;
  int _inflightPollEpoch = 0;

  static const _preparingQueryLabel = 'Preparing query…';
  static final RegExp _progressTickRe = RegExp(r'^(.+?):\s*(\d+)\s*/\s*(\d+)\s*$');

  bool get isLoading => _isLoading;
  bool get isStreaming => _isStreaming;
  String? get error => _error;
  String? get errorType => _errorType;
  double? get retryDelay => _retryDelay;
  String? get conversationId => _conversationId;
  String? get failedMessage => _failedMessage;

  List<AiChatMessage> get messages => List.unmodifiable(_messages);
  List<AiConversationSummary> get conversations => List.unmodifiable(_conversations);

  List<AiChatAgentStep> get agentSteps => List.unmodifiable(_agentSteps);
  bool get policyAcknowledged => _policyAcknowledged;
  List<String> get selectedSources => List.unmodifiable(_sourcesSelected);
  String? get streamStatusHint => _streamStatusHint;
  bool get inflightRestoreActive => _inflightRestoreActive;

  void clearStreamStatusHint() {
    _streamStatusHint = null;
    notifyListeners();
  }

  /// Load policy ack + source toggles (keys aligned with Backoffice `ngodb_chatbot_*`).
  Future<void> loadChatUiPrefs() async {
    await _storage.init();
    final ack = await _storage.getString('ngodb_chatbot_ai_policy_acknowledged');
    _policyAcknowledged = ack == '1';
    final raw = await _storage.getString('ngodb_chatbot_sources');
    if (raw != null && raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          const allowed = {'historical', 'system_documents', 'upr_documents'};
          final next = decoded.map((e) => e.toString()).where(allowed.contains).toList();
          if (next.isNotEmpty) {
            _sourcesSelected = next;
          }
        }
      } catch (_) {
        /* keep default */
      }
    }
    notifyListeners();
  }

  Future<void> acknowledgeAiPolicy() async {
    await _storage.init();
    await _storage.setString('ngodb_chatbot_ai_policy_acknowledged', '1');
    _policyAcknowledged = true;
    notifyListeners();
  }

  Future<void> setAiSourceEnabled(String key, bool enabled) async {
    const allowed = {'historical', 'system_documents', 'upr_documents'};
    if (!allowed.contains(key)) return;
    if (enabled) {
      if (!_sourcesSelected.contains(key)) {
        _sourcesSelected = [..._sourcesSelected, key];
      }
    } else {
      _sourcesSelected = _sourcesSelected.where((k) => k != key).toList();
    }
    if (_sourcesSelected.isEmpty) {
      _sourcesSelected = ['historical', 'system_documents', 'upr_documents'];
    }
    await _storage.init();
    await _storage.setString('ngodb_chatbot_sources', jsonEncode(_sourcesSelected));
    notifyListeners();
  }

  void setPreferredLanguageCode(String code) {
    final c = code.trim().toLowerCase();
    if (c.isEmpty) return;
    _preferredLanguageCode = c.length > 8 ? c.substring(0, 8) : c;
  }

  Future<void> stopStreaming({required bool isAuthenticated}) async {
    if (!_isStreaming && !_inflightRestoreActive) return;
    final cid = _conversationId;
    if (_isStreaming) {
      _wsUserCancelled = true;
      await _disconnectWs();
      _isStreaming = false;
      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }
    }
    _clearAgentProgress();
    _streamStatusHint = null;
    _inflightRestoreActive = false;
    _inflightPollEpoch++;
    notifyListeners();
    if (isAuthenticated && cid != null && cid.isNotEmpty) {
      unawaited(_service.clearConversationInflight(cid));
    }
  }

  void _clearAgentProgress() {
    _agentSteps = [];
    _lastPreparingQueryDetail = null;
  }

  void _initAgentProgressIfNeeded() {
    if (_agentSteps.isEmpty) {
      _agentSteps = [const AiChatAgentStep(message: _preparingQueryLabel)];
    }
  }

  List<String> _sourcesForPayload() {
    if (_sourcesSelected.isEmpty) {
      return ['historical', 'system_documents', 'upr_documents'];
    }
    return List<String>.from(_sourcesSelected);
  }

  Map<String, dynamic> _mobilePageContext() {
    return {
      'surface': 'mobile_ai_chat',
      'platform': 'flutter',
    };
  }

  List<Map<String, dynamic>> _conversationHistoryPayload() {
    final out = <Map<String, dynamic>>[];
    for (final m in _messages) {
      if (m.role == 'error') continue;
      if (m.role == 'assistant' && m.content.isEmpty) continue;
      out.add({'isUser': m.role == 'user', 'message': m.content});
    }
    if (out.length <= 5) return out;
    return out.sublist(out.length - 5);
  }

  Map<String, dynamic> _webSocketPayload({
    required String message,
    String? clientMessageId,
  }) {
    return {
      'type': 'user_message',
      'message': message,
      'conversation_id': _conversationId,
      if (clientMessageId != null && clientMessageId.isNotEmpty) 'client_message_id': clientMessageId,
      'preferred_language': _preferredLanguageCode,
      'page_context': _mobilePageContext(),
      'client': 'mobile',
      'conversationHistory': _conversationHistoryPayload(),
      'sources': _sourcesForPayload(),
      'keep_running_on_disconnect': true,
    };
  }

  void _finalizePreviousStepForNext(int index) {
    if (index < 0 || index >= _agentSteps.length) return;
    final step = _agentSteps[index];
    if (step.detailLines.isNotEmpty) return;
    if (step.message.trim() == _preparingQueryLabel && _lastPreparingQueryDetail != null) {
      _agentSteps[index] = step.copyWith(detailLines: [_lastPreparingQueryDetail!]);
      _lastPreparingQueryDetail = null;
    } else {
      _agentSteps[index] = step.copyWith(detailLines: const ['Done.']);
    }
  }

  void _appendDetailOnStep(int idx, String trimmed) {
    if (idx < 0 || idx >= _agentSteps.length) return;
    final step = _agentSteps[idx];
    final lines = List<String>.from(step.detailLines);
    if (lines.isNotEmpty && lines.last.trim() == trimmed) return;

    final newP = _progressTickRe.firstMatch(trimmed);
    final lastLine = lines.isNotEmpty ? lines.last.trim() : '';
    final lastP = _progressTickRe.firstMatch(lastLine);
    if (newP != null &&
        lastP != null &&
        newP.group(1)!.trim().isNotEmpty &&
        newP.group(1)!.trim() == lastP.group(1)!.trim()) {
      lines[lines.length - 1] = trimmed;
    } else {
      lines.add(trimmed);
    }
    _agentSteps[idx] = step.copyWith(detailLines: lines);
  }

  void _applyWsStepMessage(String rawMessage, String? detail) {
    final trimmed = rawMessage.trim();
    if (trimmed.isEmpty) return;
    _initAgentProgressIfNeeded();

    if (trimmed == _preparingQueryLabel && detail != null && detail.trim().isNotEmpty) {
      _lastPreparingQueryDetail = detail.trim();
    }

    final last = _agentSteps.isNotEmpty ? _agentSteps.last : null;
    final lastLabel = last?.message ?? '';

    if (last != null && lastLabel.trim() == trimmed) {
      if (detail != null && detail.trim().isNotEmpty) {
        _appendDetailOnStep(_agentSteps.length - 1, detail.trim());
      }
      return;
    }

    final newP = _progressTickRe.firstMatch(trimmed);
    final lastP = _progressTickRe.firstMatch(lastLabel.trim());
    if (last != null && newP != null && lastP != null) {
      final newPrefix = newP.group(1)!.trim();
      final lastPrefix = lastP.group(1)!.trim();
      if (newPrefix.isNotEmpty && newPrefix == lastPrefix) {
        final idx = _agentSteps.length - 1;
        _agentSteps[idx] = AiChatAgentStep(
          message: trimmed,
          detailLines: List<String>.from(_agentSteps[idx].detailLines),
        );
        if (detail != null && detail.trim().isNotEmpty) {
          _appendDetailOnStep(idx, detail.trim());
        }
        return;
      }
    }

    if (last != null) {
      _finalizePreviousStepForNext(_agentSteps.length - 1);
    }

    final initialDetails = <String>[];
    if (detail != null && detail.trim().isNotEmpty) initialDetails.add(detail.trim());
    _agentSteps = [..._agentSteps, AiChatAgentStep(message: trimmed, detailLines: initialDetails)];
  }

  void _applyWsStepDetail(String rawDetail) {
    final trimmed = rawDetail.trim();
    if (trimmed.isEmpty) return;
    _initAgentProgressIfNeeded();
    if (_agentSteps.isEmpty) return;
    _appendDetailOnStep(_agentSteps.length - 1, trimmed);
  }

  int? _parseTraceId(dynamic v) {
    if (v == null) return null;
    if (v is int) return v;
    return int.tryParse(v.toString());
  }

  double? _parseDouble(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  List<Map<String, dynamic>> _mergeStructuredPayloads(
    List<Map<String, dynamic>> existing,
    List<Map<String, dynamic>> incoming,
  ) {
    final seen = <String>{};
    for (final p in existing) {
      seen.add(jsonEncode(p));
    }
    final out = List<Map<String, dynamic>>.from(existing);
    for (final p in incoming) {
      final s = jsonEncode(p);
      if (seen.contains(s)) continue;
      seen.add(s);
      out.add(p);
    }
    return out;
  }

  Map<String, dynamic> _assistantPersistMeta(AiChatMessage m) {
    return {
      if (m.traceId != null) 'trace_id': m.traceId,
      if (m.confidence != null) 'confidence': m.confidence,
      if (m.groundingScore != null) 'grounding_score': m.groundingScore,
      if (m.userRating != null) 'user_rating': m.userRating,
      if (m.structuredPayloads.isNotEmpty) 'structured_payloads': m.structuredPayloads,
    };
  }

  void _applyInflightSnapshot(Map<String, dynamic> inflight) {
    final steps = inflight['steps'];
    if (steps is! List || steps.isEmpty) {
      _agentSteps = [const AiChatAgentStep(message: _preparingQueryLabel)];
      return;
    }
    final out = <AiChatAgentStep>[];
    for (final s in steps) {
      if (s is! Map) continue;
      final msg = s['message']?.toString() ?? '';
      if (msg.trim().isEmpty) continue;
      final dl = s['detail_lines'];
      final lines = dl is List ? dl.map((e) => e.toString()).toList() : <String>[];
      out.add(AiChatAgentStep(message: msg, detailLines: lines));
    }
    _agentSteps = out.isNotEmpty ? out : [const AiChatAgentStep(message: _preparingQueryLabel)];
  }

  void _maybeRestoreInflight(Map<String, dynamic>? getConvResponse, String conversationId, bool isAuthenticated) {
    if (!isAuthenticated || getConvResponse == null) return;
    final conv = getConvResponse['conversation'];
    if (conv is! Map) return;
    final metaRaw = conv['meta'];
    if (metaRaw is! Map) return;
    final inflight = metaRaw['inflight'];
    if (inflight is! Map) return;
    if ((inflight['status']?.toString() ?? '') != 'in_progress') return;
    _inflightRestoreActive = true;
    _applyInflightSnapshot(Map<String, dynamic>.from(inflight));
    _inflightPollEpoch++;
    final epoch = _inflightPollEpoch;
    unawaited(_pollServerInflight(conversationId, epoch, isAuthenticated));
  }

  Future<void> _pollServerInflight(String conversationId, int epoch, bool isAuthenticated) async {
    if (!isAuthenticated) return;
    for (var i = 0; i < 120; i++) {
      await Future.delayed(const Duration(seconds: 2));
      if (epoch != _inflightPollEpoch || _conversationId != conversationId) return;
      try {
        final data = await _service.getConversation(conversationId);
        final conv = data['conversation'];
        Map<String, dynamic>? active;
        if (conv is Map) {
          final meta = conv['meta'];
          if (meta is Map) {
            final inf = meta['inflight'];
            if (inf is Map && (inf['status']?.toString() ?? '') == 'in_progress') {
              active = Map<String, dynamic>.from(inf);
            }
          }
        }
        if (active == null) {
          _inflightRestoreActive = false;
          _clearAgentProgress();
          await _syncConversationFromServer(conversationId);
          if (_conversationId == conversationId) {
            _messages = await _persistence.getConversationMessages(conversationId);
          }
          notifyListeners();
          return;
        }
        _applyInflightSnapshot(active);
        notifyListeners();
      } catch (_) {}
    }
    _inflightRestoreActive = false;
    _clearAgentProgress();
    notifyListeners();
  }

  Future<void> _handleWsJson(
    Map<String, dynamic> data, {
    required String outboundMessage,
    required bool isAuthenticated,
  }) async {
    final type = data['type']?.toString();
    if (type == 'meta') {
      final cid = data['conversation_id']?.toString();
      if (cid != null && cid.isNotEmpty && cid != _conversationId) {
        _conversationId = cid;

        final firstUser = (_messages.isNotEmpty && _messages.first.role == 'user') ? _messages.first.content : null;
        final title = firstUser == null
            ? null
            : (firstUser.length > 80 ? '${firstUser.substring(0, 80)}...' : firstUser);

        final convo = AiConversationSummary(
          id: cid,
          title: title,
          updatedAt: DateTime.now(),
          lastMessageAt: DateTime.now(),
        );
        await _persistence.saveConversation(convo);

        final index = _conversations.indexWhere((c) => c.id == cid);
        if (index >= 0) {
          _conversations[index] = convo;
        } else {
          _conversations.insert(0, convo);
        }
        _conversations.sort((a, b) {
          final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
          final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
          return bTime.compareTo(aTime);
        });
      }
      return;
    }

    if (type == 'step') {
      final msg = data['message']?.toString();
      final det = data['detail']?.toString();
      if (msg != null && msg.trim().isNotEmpty) {
        _applyWsStepMessage(msg, det);
      } else if (det != null && det.trim().isNotEmpty) {
        _applyWsStepDetail(det);
      }
      return;
    }

    if (type == 'step_detail') {
      _applyWsStepDetail(data['detail']?.toString() ?? '');
      return;
    }

    if (type == 'structured') {
      final merged = coerceStructuredFromEnvelope(data);
      if (merged.isEmpty) return;
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        _messages[_messages.length - 1] = last.copyWith(
          structuredPayloads: _mergeStructuredPayloads(last.structuredPayloads, merged),
        );
      }
      return;
    }

    if (type == 'status') {
      _streamStatusHint = data['message']?.toString();
      notifyListeners();
      return;
    }

    if (type == 'delta') {
      final delta = data['text']?.toString() ?? '';
      if (delta.isNotEmpty) {
        _clearAgentProgress();
        _streamStatusHint = null;
      }
      if (_messages.isNotEmpty) {
        final last = _messages.last;
        _messages[_messages.length - 1] = last.copyWith(content: last.content + delta);
      }
      return;
    }

    if (type == 'done') {
      _clearAgentProgress();
      _streamStatusHint = null;
      _isStreaming = false;
      _inflightRestoreActive = false;

      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        final response = data['response']?.toString() ?? '';
        var content = last.content;
        if (content.trim().isEmpty && response.trim().isNotEmpty) {
          content = response;
        }
        final structured = _mergeStructuredPayloads(last.structuredPayloads, coerceStructuredFromEnvelope(data));
        final traceId = _parseTraceId(data['trace_id']) ?? last.traceId;
        var conf = last.confidence;
        var grounding = last.groundingScore;
        final metaMap = data['meta'];
        if (metaMap is Map) {
          final mm = Map<String, dynamic>.from(metaMap);
          conf = _parseDouble(mm['confidence']) ?? conf;
          grounding = _parseDouble(mm['grounding_score']) ?? grounding;
        }
        conf = _parseDouble(data['confidence']) ?? conf;
        grounding = _parseDouble(data['grounding_score']) ?? grounding;

        _messages[_messages.length - 1] = last.copyWith(
          content: content,
          structuredPayloads: structured,
          traceId: traceId,
          confidence: conf,
          groundingScore: grounding,
        );
      }

      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        if (last.content.trim().isEmpty && last.structuredPayloads.isEmpty && last.traceId == null) {
          _messages.removeLast();
        }
      }

      if (_conversationId != null && _messages.isNotEmpty) {
        final lastMsg = _messages.last;
        if (lastMsg.role == 'assistant' &&
            (lastMsg.content.isNotEmpty || lastMsg.structuredPayloads.isNotEmpty)) {
          await _persistence.saveMessage(
            conversationId: _conversationId!,
            role: 'assistant',
            content: lastMsg.content,
            localMessageId: _uuid.v4(),
            syncState: AiChatPersistenceService.syncStatePendingServer,
            meta: _assistantPersistMeta(lastMsg),
          );
          final title = _messages.isNotEmpty
              ? (_messages.first.content.length > 80 ? '${_messages.first.content.substring(0, 80)}...' : _messages.first.content)
              : null;
          final convo = AiConversationSummary(
            id: _conversationId!,
            title: title,
            updatedAt: DateTime.now(),
            lastMessageAt: DateTime.now(),
          );
          await _persistence.saveConversation(convo);

          final index = _conversations.indexWhere((c) => c.id == _conversationId);
          if (index >= 0) {
            _conversations[index] = convo;
          } else {
            _conversations.insert(0, convo);
          }
          _conversations.sort((a, b) {
            final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
            final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
            return bTime.compareTo(aTime);
          });
        }
      }
      if (_conversationId != null) {
        unawaited(_syncConversationFromServer(_conversationId!));
      }
      return;
    }

    if (type == 'error') {
      _clearAgentProgress();
      _streamStatusHint = null;
      _errorType = data['error_type']?.toString();
      _error = data['message']?.toString() ?? 'Chat failed';
      if (data['retry_delay'] != null) {
        try {
          _retryDelay = double.tryParse(data['retry_delay'].toString());
        } catch (_) {
          _retryDelay = null;
        }
      } else {
        _retryDelay = null;
      }
      _isStreaming = false;

      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }

      if (_errorType == 'empty_response' && _messages.isNotEmpty) {
        final userMessage = _messages.last;
        if (userMessage.role == 'user') {
          _failedMessage = userMessage.content;
        }
      }

      if (_errorType == 'quota_exceeded') {
        final userMessages = _messages.where((m) => m.role == 'user').toList();
        if (userMessages.isNotEmpty) {
          _failedMessage = userMessages.last.content;
        }
      }

      _messages.add(AiChatMessage(
        role: 'error',
        content: _error ?? 'Chat failed',
        errorType: _errorType,
        retryDelay: _retryDelay,
      ));
    }
  }

  Future<void> _runWebSocketStream({
    required String message,
    required bool isAuthenticated,
    String? clientMessageId,
  }) async {
    await _disconnectWs();
    _channel = await _service.connectWebSocket();
    _channel!.sink.add(jsonEncode(_webSocketPayload(message: message, clientMessageId: clientMessageId)));

    _wsSub = _channel!.stream.listen(
      (event) async {
        try {
          final decoded = jsonDecode(event.toString());
          if (decoded is! Map) return;
          final data = Map<String, dynamic>.from(decoded);
          await _handleWsJson(data, outboundMessage: message, isAuthenticated: isAuthenticated);
          notifyListeners();
        } catch (_) {
          /* malformed */
        }
      },
      onError: (e) async {
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        DebugLogger.logWarn('AI', 'WS error, falling back to HTTP: $e');
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
          _messages.removeLast();
        }
        _clearAgentProgress();
        _isStreaming = false;
        notifyListeners();
        await _sendHttpIntoLastAssistant(
          message,
          isAuthenticated: isAuthenticated,
          persistUserMessage: false,
          clientMessageId: clientMessageId,
        );
      },
      onDone: () {
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
          _messages.removeLast();
        }
        _clearAgentProgress();
        _isStreaming = false;
        notifyListeners();
      },
    );
  }

  Future<void> ensureTokenIfLoggedIn({required bool isAuthenticated}) async {
    if (!isAuthenticated) return;
    // Best effort: fetch token only if we don't already have one cached.
    // If it fails, cookie auth may still work for HTTP, but WS benefits from token headers.
    final cached = await _service.getCachedToken();
    if (cached != null && cached.isNotEmpty) return;
    await _service.fetchAndCacheToken();
  }

  Future<void> loadConversations({required bool isAuthenticated}) async {
    if (!isAuthenticated) {
      // Logged-out: show locally cached/offline conversations
      _conversations = await _persistence.getAllConversations();
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      // Load from local DB first (fast)
      _conversations = await _persistence.getAllConversations();
      // Sort by most recent first
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      notifyListeners();

      // Then sync from server (if online)
      try {
        final raw = await _service.listConversations();
        final serverConvos = raw.map((e) => AiConversationSummary.fromJson(Map<String, dynamic>.from(e))).toList();

        // Save server conversations to local DB
        for (final convo in serverConvos) {
          await _persistence.saveConversation(convo);
        }

        // Merge: keep local-only conversations that don't exist on server yet
        final byId = <String, AiConversationSummary>{for (final c in serverConvos) c.id: c};
        for (final local in _conversations) {
          if (!byId.containsKey(local.id)) {
            byId[local.id] = local;
          }
        }
        _conversations = byId.values.toList();
        // Sort by most recent first
        _conversations.sort((a, b) {
          final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
          final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
          return bTime.compareTo(aTime);
        });
      } catch (e) {
        DebugLogger.logWarn('AI', 'Failed to sync conversations from server, using local: $e');
        // Keep local conversations if server sync fails
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> openConversation({required bool isAuthenticated, required String conversationId}) async {
    _isLoading = true;
    _error = null;
    notifyListeners();
    try {
      // Load from local DB first (fast)
      _conversationId = conversationId;
      _messages = await _persistence.getConversationMessages(conversationId);
      notifyListeners();

      // Then sync from server (if online)
      if (isAuthenticated) {
        final snap = await _syncConversationFromServer(conversationId);
        _messages = await _persistence.getConversationMessages(conversationId);
        notifyListeners();
        _maybeRestoreInflight(snap, conversationId, isAuthenticated);

        // If we have offline-only messages, import them once after login to keep the server conversation consistent.
        await _maybeImportOfflineMessages(conversationId);
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void startNewConversation() {
    _conversationId = null;
    _messages = [];
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;
    _clearAgentProgress();
    _streamStatusHint = null;
    _inflightRestoreActive = false;
    _inflightPollEpoch++;
    notifyListeners();
  }

  /// Ensure we have a stable local conversation UUID so we can persist offline and later merge on login.
  /// The server will accept a provided UUID for authenticated users, so the same ID can be reused across sync.
  Future<String> _ensureLocalConversationId({String? initialTitle}) async {
    if (_conversationId != null && _conversationId!.isNotEmpty) return _conversationId!;
    final cid = _uuid.v4();
    _conversationId = cid;
    final now = DateTime.now();
    final convo = AiConversationSummary(
      id: cid,
      title: initialTitle != null && initialTitle.isNotEmpty
          ? (initialTitle.length > 80 ? '${initialTitle.substring(0, 80)}...' : initialTitle)
          : null,
      updatedAt: now,
      lastMessageAt: now,
    );
    await _persistence.saveConversation(convo, meta: {'local_created': true});
    // Upsert into drawer list immediately
    final index = _conversations.indexWhere((c) => c.id == cid);
    if (index >= 0) {
      _conversations[index] = convo;
    } else {
      _conversations.insert(0, convo);
    }
    _conversations.sort((a, b) {
      final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
      final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
      return bTime.compareTo(aTime);
    });
    notifyListeners();
    return cid;
  }

  Future<void> deleteConversation(String conversationId, {required bool isAuthenticated}) async {
    try {
      // Delete from server first (best effort - if it fails, still delete locally)
      if (isAuthenticated) {
        try {
          await _service.deleteConversation(conversationId);
        } catch (e) {
          DebugLogger.logWarn('AI', 'Failed to delete conversation from server (continuing with local delete): $e');
          // Continue with local deletion even if server deletion fails
        }
      }

      // Delete from local DB
      await _persistence.deleteConversation(conversationId);

      // Remove from in-memory list
      _conversations.removeWhere((c) => c.id == conversationId);

      // If this was the current conversation, start a new one
      if (_conversationId == conversationId) {
        startNewConversation();
      }

      notifyListeners();
    } catch (e) {
      DebugLogger.logErrorWithTag('AI', 'Failed to delete conversation: $e');
      _error = 'Failed to delete conversation';
      notifyListeners();
    }
  }

  Future<void> clearAllConversations({required bool isAuthenticated}) async {
    try {
      // Delete all from server (best effort - if it fails, still delete locally)
      if (isAuthenticated) {
        for (final conversation in _conversations) {
          try {
            await _service.deleteConversation(conversation.id);
          } catch (e) {
            DebugLogger.logWarn('AI', 'Failed to delete conversation ${conversation.id} from server: $e');
          }
        }
      }

      // Clear from local DB
      await _persistence.clearAllConversations();

      // Clear in-memory list
      _conversations = [];

      // Start a new conversation
      startNewConversation();

      notifyListeners();
    } catch (e) {
      DebugLogger.logErrorWithTag('AI', 'Failed to clear all conversations: $e');
      _error = 'Failed to clear all conversations';
      notifyListeners();
    }
  }

  /// Retry sending the failed message (if any)
  Future<void> retryFailedMessage({required bool isAuthenticated}) async {
    // Avoid duplicating the user message; retry the last user message in-place.
    await retryLastMessage(isAuthenticated: isAuthenticated);
  }

  /// Retry the last user message without adding a duplicate
  Future<void> retryLastMessage({required bool isAuthenticated}) async {
    // Find the last user message
    final userMessages = _messages.where((m) => m.role == 'user').toList();
    if (userMessages.isEmpty) return;

    final lastUserMessage = userMessages.last;
    final message = lastUserMessage.content;

    // Clear error state
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    // Remove any error messages or empty assistant placeholders at the end
    while (_messages.isNotEmpty &&
           (_messages.last.role == 'assistant' && _messages.last.content.isEmpty)) {
      _messages.removeLast();
    }

    // Add assistant placeholder for streaming
    _messages.add(AiChatMessage(role: 'assistant', content: ''));
    _isStreaming = true;
    notifyListeners();

    // Anonymous: just use HTTP fallback
    if (!isAuthenticated) {
      await _sendHttpIntoLastAssistant(message, isAuthenticated: false, persistUserMessage: false);
      return;
    }

    _clearAgentProgress();
    _initAgentProgressIfNeeded();
    try {
      await _runWebSocketStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: null,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'WS connect failed, falling back to HTTP: $e');
      _isStreaming = false;
      _clearAgentProgress();
      notifyListeners();
      await _sendHttpIntoLastAssistant(message, isAuthenticated: isAuthenticated, persistUserMessage: false);
    }
  }

  /// Get message content for editing (doesn't clear messages yet)
  /// Messages will be cleared when sendEditedMessage is called
  String? editMessageAt(int messageIndex) {
    if (messageIndex < 0 || messageIndex >= _messages.length) return null;
    final message = _messages[messageIndex];
    if (message.role != 'user') return null;

    // Don't clear messages yet - just return the content for editing
    // Messages will be cleared when sendEditedMessage is called

    // Clear any streaming state
    _isStreaming = false;
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;
    _clearAgentProgress();
    unawaited(_disconnectWs());

    notifyListeners();
    return message.content;
  }

  /// Send a message after editing (replaces the message at editIndex and clears all after it)
  Future<void> sendEditedMessage({
    required String message,
    required int editIndex,
    required bool isAuthenticated,
  }) async {
    // Editing cannot mutate server history; we fork a new conversation starting from the history before editIndex.
    // This yields predictable behavior and keeps merge/sync consistent.
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    final history = <AiChatMessage>[];
    for (int i = 0; i < _messages.length && i < editIndex; i++) {
      final m = _messages[i];
      if (m.role == 'error') continue;
      // Skip empty assistant placeholders
      if (m.role == 'assistant' && m.content.isEmpty) continue;
      history.add(m);
    }

    // Start a new forked conversation (new id), persist history offline-first
    startNewConversation();
    final newCid = await _ensureLocalConversationId(
      initialTitle: history.isNotEmpty ? history.first.content : message,
    );

    _messages = List<AiChatMessage>.from(history);
    notifyListeners();

    for (final m in history) {
      await _persistence.saveMessage(
        conversationId: newCid,
        role: m.role,
        content: m.content,
        localMessageId: _uuid.v4(),
        syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
        createdAt: m.createdAt,
      );
    }

    // If authenticated, import the fork history to the server so the conversation is consistent across devices.
    if (isAuthenticated && history.isNotEmpty) {
      try {
        final importPayload = history.map((m) {
          return {
            'client_message_id': _uuid.v4(),
            'role': m.role,
            'content': m.content,
            'created_at': m.createdAt.toIso8601String(),
          };
        }).toList();
        await _service.importConversationMessages(conversationId: newCid, messages: importPayload);
      } catch (e) {
        DebugLogger.logWarn('AI', 'Failed to import fork history (continuing): $e');
      }
    }

    // Now send the edited message normally (it will append user+assistant and stream the reply)
    await sendMessageStreaming(
      message: message,
      isAuthenticated: isAuthenticated,
      preferredLanguageCode: _preferredLanguageCode,
    );
  }

  Future<void> sendMessageStreaming({
    required String message,
    required bool isAuthenticated,
    String? preferredLanguageCode,
  }) async {
    if (preferredLanguageCode != null && preferredLanguageCode.isNotEmpty) {
      setPreferredLanguageCode(preferredLanguageCode);
    }
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null; // Clear any previous failed message
    final cid = await _ensureLocalConversationId(initialTitle: message);
    final userLocalId = _uuid.v4();
    _messages.add(AiChatMessage(role: 'user', content: message));
    _messages.add(AiChatMessage(role: 'assistant', content: '')); // placeholder to stream into
    _isStreaming = true;
    notifyListeners();

    // Persist user message immediately (offline-first)
    await _persistence.saveMessage(
      conversationId: cid,
      role: 'user',
      content: message,
      localMessageId: userLocalId,
      syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
    );

    // Anonymous: just use HTTP fallback (no persistence anyway)
    if (!isAuthenticated) {
      await _sendHttpIntoLastAssistant(message, isAuthenticated: false, persistUserMessage: false);
      return;
    }

    _clearAgentProgress();
    _initAgentProgressIfNeeded();
    try {
      await _runWebSocketStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: userLocalId,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'WS connect failed, falling back to HTTP: $e');
      _isStreaming = false;
      _clearAgentProgress();
      notifyListeners();
      await _sendHttpIntoLastAssistant(
        message,
        isAuthenticated: isAuthenticated,
        persistUserMessage: false,
        clientMessageId: userLocalId,
      );
    }
  }

  Future<void> _sendHttpIntoLastAssistant(
    String message, {
    bool isAuthenticated = false,
    bool persistUserMessage = true,
    String? clientMessageId,
  }) async {
    _clearAgentProgress();
    _isStreaming = true;
    notifyListeners();
    try {
      // For anonymous requests, do not send a conversation_id to the server (server ignores it anyway).
      final serverConversationId = isAuthenticated ? _conversationId : null;
      final data = await _service.sendMessageHttp(
        message: message,
        conversationId: serverConversationId,
        isAuthenticated: isAuthenticated,
        clientMessageId: isAuthenticated ? clientMessageId : null,
        pageContext: _mobilePageContext(),
        preferredLanguage: _preferredLanguageCode,
        conversationHistory: isAuthenticated ? _conversationHistoryPayload() : null,
        sources: isAuthenticated ? _sourcesForPayload() : null,
      );
      final newCid = data['conversation_id']?.toString();
      if (isAuthenticated && newCid != null && newCid.isNotEmpty) {
        _conversationId = newCid;
      }
      final reply = data['reply']?.toString() ?? '';
      final structured = coerceStructuredFromEnvelope(data);
      final tid = _parseTraceId(data['trace_id']);
      double? conf;
      double? grounding;
      final metaTop = data['meta'];
      if (metaTop is Map) {
        final mm = Map<String, dynamic>.from(metaTop);
        conf = _parseDouble(mm['confidence']);
        grounding = _parseDouble(mm['grounding_score']);
      }
      final asstMsg = AiChatMessage(
        role: 'assistant',
        content: reply,
        traceId: tid,
        structuredPayloads: structured,
        confidence: conf,
        groundingScore: grounding,
      );
      if (_messages.isNotEmpty) {
        // Find the last assistant placeholder (empty content) to update
        bool foundPlaceholder = false;
        for (int i = _messages.length - 1; i >= 0; i--) {
          if (_messages[i].role == 'assistant' && _messages[i].content.isEmpty) {
            _messages[i] = asstMsg;
            foundPlaceholder = true;
            break;
          }
        }
        // If no placeholder found, add a new assistant message
        if (!foundPlaceholder) {
          _messages.add(asstMsg);
        }

        if (_conversationId != null) {
          // Save user message (optional - callers may already have persisted it)
          if (persistUserMessage) {
            await _persistence.saveMessage(
              conversationId: _conversationId!,
              role: 'user',
              content: message,
              localMessageId: _uuid.v4(),
              syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
            );
          }
          // Save assistant reply
          await _persistence.saveMessage(
            conversationId: _conversationId!,
            role: 'assistant',
            content: asstMsg.content,
            localMessageId: _uuid.v4(),
            syncState: isAuthenticated ? AiChatPersistenceService.syncStatePendingServer : AiChatPersistenceService.syncStateLocalOnly,
            meta: _assistantPersistMeta(asstMsg),
          );
          // Update conversation summary
          final title = message.length > 80 ? '${message.substring(0, 80)}...' : message;
          final convo = AiConversationSummary(
            id: _conversationId!,
            title: title,
            updatedAt: DateTime.now(),
            lastMessageAt: DateTime.now(),
          );
          await _persistence.saveConversation(convo);

          // Update conversation in list immediately
          final index = _conversations.indexWhere((c) => c.id == _conversationId);
          if (index >= 0) {
            _conversations[index] = convo;
          } else {
            _conversations.insert(0, convo);
          }
          // Sort by most recent first
          _conversations.sort((a, b) {
            final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
            final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
            return bTime.compareTo(aTime);
          });
        }
      }
      _isStreaming = false;
      notifyListeners();
    } catch (e) {
      _isStreaming = false; // Stop streaming immediately on error

      // Extract error message
      String errorMessage = e.toString();
      // Remove "Exception: " prefix if present
      if (errorMessage.startsWith('Exception: ')) {
        errorMessage = errorMessage.substring(11);
      }

      _error = errorMessage;

      // Check if it's a quota error from HTTP response
      final errorStr = errorMessage.toLowerCase();
      String? errorType;
      if (errorStr.contains('quota') || errorStr.contains('429') || errorStr.contains('rate limit')) {
        errorType = 'quota_exceeded';
        _errorType = 'quota_exceeded';
        // Store the last user message for retry if it exists
        final userMessages = _messages.where((m) => m.role == 'user').toList();
        if (userMessages.isNotEmpty) {
          _failedMessage = userMessages.last.content;
        }
      } else if (errorStr.contains('timeout')) {
        errorType = 'timeout_error';
        _errorType = 'timeout_error';
      } else if (errorStr.contains('connection') || errorStr.contains('network')) {
        errorType = 'network_error';
        _errorType = 'network_error';
      } else {
        errorType = 'server_error';
        _errorType = 'server_error';
      }

      // Remove the assistant placeholder if it exists
      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }

      // Add error message bubble to the conversation
      _messages.add(AiChatMessage(
        role: 'error',
        content: errorMessage,
        errorType: errorType,
      ));

      notifyListeners();
    }
  }

  Future<Map<String, dynamic>?> _syncConversationFromServer(String conversationId) async {
    if (_syncInFlight.contains(conversationId)) return null;
    _syncInFlight.add(conversationId);
    try {
      final data = await _service.getConversation(conversationId);
      final msgs = (data['messages'] as List?) ?? [];
      final serverMessages = msgs.map((m) => Map<String, dynamic>.from(m)).toList();

      await _persistence.replaceServerMessages(
        conversationId: conversationId,
        serverMessages: serverMessages,
      );
      await _persistence.reconcilePendingMessages(
        conversationId: conversationId,
        serverMessages: serverMessages,
      );
      return data;
    } catch (e) {
      DebugLogger.logWarn('AI', 'Failed to sync conversation from server: $e');
      return null;
    } finally {
      _syncInFlight.remove(conversationId);
    }
  }

  Future<void> _maybeImportOfflineMessages(String conversationId) async {
    try {
      final localOnly = await _persistence.getLocalOnlyMessagesForImport(conversationId, limit: 200);
      if (localOnly.isEmpty) return;

      final importPayload = localOnly.map((m) {
        return {
          'client_message_id': m['local_message_id']?.toString(),
          'role': m['role']?.toString(),
          'content': m['content']?.toString(),
          'created_at': m['created_at']?.toString(),
        };
      }).toList();

      await _service.importConversationMessages(conversationId: conversationId, messages: importPayload);

      // Prevent repeated imports; mark as pending-server so they can be reconciled after the next snapshot
      await _persistence.updateConversationMessagesSyncState(
        conversationId: conversationId,
        from: AiChatPersistenceService.syncStateLocalOnly,
        to: AiChatPersistenceService.syncStatePendingServer,
      );

      await _syncConversationFromServer(conversationId);
    } catch (e) {
      DebugLogger.logWarn('AI', 'Offline message import skipped/failed: $e');
    }
  }

  Future<void> _disconnectWs() async {
    try {
      await _wsSub?.cancel();
    } catch (_) {}
    _wsSub = null;
    try {
      await _channel?.sink.close();
    } catch (_) {}
    _channel = null;
  }

  Future<void> submitMessageFeedback(int messageIndex, String rating) async {
    if (messageIndex < 0 || messageIndex >= _messages.length) return;
    final m = _messages[messageIndex];
    if (m.role != 'assistant' || m.traceId == null) return;
    final r = rating.trim().toLowerCase();
    if (r != 'like' && r != 'dislike') return;
    final ok = await _service.submitFeedback(traceId: m.traceId!, rating: r);
    if (!ok) return;
    _messages[messageIndex] = m.copyWith(userRating: r);
    notifyListeners();
  }

  @override
  void dispose() {
    _disconnectWs();
    super.dispose();
  }
}
