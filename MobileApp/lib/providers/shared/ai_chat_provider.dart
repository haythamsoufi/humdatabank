import 'dart:async';
import 'dart:convert';
import 'dart:io' show SocketException;

import 'package:flutter/foundation.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:uuid/uuid.dart';

import '../../models/shared/ai_chat.dart';
import '../../config/api_timeouts.dart';
import '../../config/app_config.dart';
import '../../services/ai_chat_exception.dart';
import '../../services/ai_chat_service.dart';
import '../../services/ai_chat_persistence_service.dart';
import '../../services/storage_service.dart';
import '../../utils/ai_chat_structured_coerce.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';

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
  /// Last auth identity for which [loadConversations] reset in-memory state. When unchanged,
  /// a repeated load (e.g. AiChatScreen re-mounted after switching tabs) only refreshes the
  /// conversation list and preserves [conversationId] / [messages].
  String? _conversationsListSessionKey;
  /// Local-only: pinned conversations surface at the top of the list (drawer / chats).
  Set<String> _pinnedConversationIds = {};

  WebSocketChannel? _channel;
  StreamSubscription? _wsSub;

  /// Incremented on every `_disconnectWs` so stale `onDone` / `onError` callbacks from a
  /// previous socket never mutate the wrong conversation after navigation.
  int _wsConnectionSession = 0;

  /// Conversation id this WebSocket stream belongs to (set when sending; updated on `meta`).
  /// If it diverges from `_conversationId`, events are ignored (defense in depth).
  String? _wsStreamConversationId;

  /// When the active WS send is an edit-branch, HTTP fallbacks must repeat `branch_from_edit` + history.
  bool _wsBranchFromEdit = false;
  List<Map<String, dynamic>>? _wsBranchConversationHistory;

  /// Incremented when switching chats / new chat / full reload so in-flight HTTP completions
  /// cannot apply to the wrong conversation.
  int _navigationEpoch = 0;

  /// Steps captured when the user leaves mid-stream (parity with Backoffice detached step cache).
  final Map<String, List<AiChatAgentStep>> _detachedAgentStepsByConversationId = {};

  // Prevent overlapping server syncs per conversation
  final Set<String> _syncInFlight = {};

  final StorageService _storage = StorageService();

  /// Agent/tool steps while streaming (WS `step` / `step_detail`, same as Backoffice chatbot).
  List<AiChatAgentStep> _agentSteps = [];
  String? _lastPreparingQueryDetail;
  bool _wsUserCancelled = false;
  /// After a `narration` event, insert a blank line once before the final answer deltas.
  bool _pendingNarrationSeparator = false;
  /// Narration for the current turn, kept separate so `done.response` can replace the delta buffer.
  String? _turnNarration;
  /// `client_message_id` of the user row for this turn, so a DLP mask can update that SQLite row.
  String? _activeClientMessageId;

  /// How long to follow a server run that outlived its stream before giving up the progress UI.
  static const Duration _inflightPollInterval = Duration(seconds: 2);
  static const int _inflightMaxPolls = 600; // 20 minutes

  /// Server `request_id` of the in-flight SSE stream (from the `meta` envelope); used so the stop
  /// button can ask the backend to cancel generation instead of only dropping the connection.
  String? _streamRequestId;

  bool _policyAcknowledged = false;
  /// True once [loadChatUiPrefs] has completed at least once.
  /// Guards the policy banner and the send gate so we never incorrectly
  /// block a user who already acknowledged while prefs are still loading.
  bool _prefsLoaded = false;
  List<String> _sourcesSelected = ['historical', 'system_documents', 'upr_documents'];
  String _preferredLanguageCode = 'en';
  String? _streamStatusHint;
  bool _inflightRestoreActive = false;
  int _inflightPollEpoch = 0;
  /// True while `/chat/await` is following a turn that was already submitted.
  bool _storedReplyWaitActive = false;

  /// Categorize HTTP/WS transport failures for user-facing [AiChatMessage.errorType].
  static String? _inferChatErrorType(Object e, String lower) {
    if (lower.contains('quota') || lower.contains('429') || lower.contains('rate limit')) {
      return 'quota_exceeded';
    }
    if (e is SocketException) {
      return 'network_error';
    }
    if (lower.contains('socketexception') ||
        lower.contains('failed host lookup') ||
        lower.contains('host lookup') ||
        lower.contains('nodename nor servname') ||
        lower.contains('network is unreachable') ||
        lower.contains('no address associated with hostname') ||
        lower.contains('no internet') ||
        lower.contains('connection refused') ||
        lower.contains('connection reset') ||
        lower.contains('connection closed') ||
        (lower.contains('clientexception') &&
            (lower.contains('socket') || lower.contains('closed') || lower.contains('lookup')))) {
      return 'network_error';
    }
    if (lower.contains('timeoutexception') ||
        lower.contains('read timed out') ||
        lower.contains('connection timed out') ||
        lower.contains('time out while waiting') ||
        (lower.contains('http') && lower.contains('timeout'))) {
      return 'timeout_error';
    }
    return 'server_error';
  }

  /// True for stream `error` envelopes with no specific `error_type` (the backend's catch-all
  /// emits `"Error"`), as opposed to actionable ones such as quota, DLP or auth failures.
  @visibleForTesting
  static bool isUnclassifiedStreamError(Object? errorType) {
    final t = errorType?.toString().trim() ?? '';
    return t.isEmpty || t == 'Error';
  }

  static const _preparingQueryLabel = 'Preparing query…';
  /// Former completed-step detail marker. Kept so older inflight snapshots still
  /// round-trip; the UI hides it (checkmark already signals completion).
  static const aiAgentStepDoneSentinel = '__AI_STEP_DONE__';
  static final RegExp _progressTickRe = RegExp(r'^(.+?):\s*(\d+)\s*/\s*(\d+)\s*$');

  /// Sub-step lines from [Backoffice] databank tools (`data_retrieval_form` progress)
  /// and similar: update the same detail line in the UI instead of stacking six lines.
  /// English prefixes are recognized directly; any other locale's status line is recognized
  /// by its trailing ellipsis so it replaces in place too.
  static final RegExp _pipelineProgressDetailRe = RegExp(
    r'^(Loading countries|Resolving indicator|Selecting indicator|Querying form data|Building results|Scanning your access|Preparing the databank query)\b',
    caseSensitive: false,
  );

  static bool _endsWithStatusEllipsis(String t) => t.endsWith('…') || t.endsWith('...');

  static bool _isPipelineProgressDetailLine(String s) {
    final t = s.trim();
    if (t.isEmpty) return false;
    if (_pipelineProgressDetailRe.hasMatch(t)) return true;
    // UPR / document search “fetching / scanning” style (English)
    if (RegExp(r'^Retrieving up to\b', caseSensitive: false).hasMatch(t)) {
      return true;
    }
    // Translated status lines keep the trailing ellipsis ("Chargement des pays…").
    // Treating those as the in-flight line replaces them in place instead of stacking one per tick.
    if (_endsWithStatusEllipsis(t)) return true;
    return false;
  }

  /// Server `done.response` is the HTML that gets persisted. Prefer it over the delta buffer,
  /// and keep model narration above that answer when the server text does not already include it.
  @visibleForTesting
  static String composeDoneContent({
    required String buffer,
    required String response,
    required String narration,
  }) {
    final content = response.trim().isNotEmpty ? response : buffer;
    final n = narration.trim();
    if (n.isEmpty) return content;
    if (content.trim().isEmpty) return n;
    if (content.contains(n)) return content;
    return '$n\n\n$content';
  }

  /// Body to store locally so it matches the server row (narration is display-only).
  /// Visual-only turns use the same placeholders Backoffice persists.
  @visibleForTesting
  static String persistedAssistantContent({
    required String response,
    required List<Map<String, dynamic>> structured,
  }) {
    if (response.trim().isNotEmpty) return response;
    final types = <String>{
      for (final p in structured) (p['type'] ?? '').toString().toLowerCase(),
    };
    final hasMap = types.contains('worldmap');
    final hasChart = types.contains('line') || types.contains('bar') || types.contains('pie');
    final hasTable = types.contains('data_table');
    if (hasMap && hasChart) return '[Map and chart visualization]';
    if (hasMap) return '[Map visualization]';
    if (hasTable) return '[Data table]';
    if (hasChart) return '[Chart visualization]';
    return '';
  }

  /// Keep a rewritten or server-refined title. [fallback] is only for a chat that has none yet.
  @visibleForTesting
  static String? titleAfterTurn({String? existingTitle, String? fallback}) {
    final existing = existingTitle?.trim() ?? '';
    if (existing.isNotEmpty) return existing;
    final fb = (fallback ?? '').trim();
    if (fb.isEmpty) return null;
    if (fb.length > 80) return '${fb.substring(0, 80)}...';
    return fb;
  }

  @visibleForTesting
  static bool isPipelineProgressDetail(String s) => _isPipelineProgressDetailLine(s);

  bool get isLoading => _isLoading;
  bool get isStreaming => _isStreaming;
  String? get error => _error;
  String? get errorType => _errorType;
  double? get retryDelay => _retryDelay;
  String? get conversationId => _conversationId;
  String? get failedMessage => _failedMessage;

  /// Set when the server refuses AI because beta access is on and this account
  /// is not allow-listed. The chat screen locks instead of leaving the composer up.
  bool get betaAccessDenied => _betaAccessDenied;
  bool _betaAccessDenied = false;

  void _noteBetaAccessDenial(Object error) {
    if (!AiChatHttpException.errorDeniesBetaAccess(error)) return;
    if (_betaAccessDenied) return;
    _betaAccessDenied = true;
    _isStreaming = false;
    _isLoading = false;
    notifyListeners();
  }

  List<AiChatMessage> get messages => List.unmodifiable(_messages);
  List<AiConversationSummary> get conversations => List.unmodifiable(_orderedConversations());

  List<AiConversationSummary> _orderedConversations() {
    final list = List<AiConversationSummary>.from(_conversations);
    list.sort(_compareConversationDrawerOrder);
    return list;
  }

  int _compareConversationDrawerOrder(AiConversationSummary a, AiConversationSummary b) {
    final ap = _pinnedConversationIds.contains(a.id);
    final bp = _pinnedConversationIds.contains(b.id);
    if (ap != bp) {
      return ap ? -1 : 1;
    }
    final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
    final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
    return bTime.compareTo(aTime);
  }

  bool isConversationPinned(String conversationId) => _pinnedConversationIds.contains(conversationId);

  Future<void> setConversationPinned(String conversationId, bool pinned) async {
    if (pinned) {
      _pinnedConversationIds = {..._pinnedConversationIds, conversationId};
    } else {
      _pinnedConversationIds = {..._pinnedConversationIds}..remove(conversationId);
    }
    await _persistPinnedIds();
    notifyListeners();
  }

  Future<void> _persistPinnedIds() async {
    await _storage.init();
    await _storage.setString(AppConfig.chatbotPinnedConversationIdsKey,
        jsonEncode(_pinnedConversationIds.toList()));
  }

  void _pruneStalePinnedIds() {
    if (_conversations.isEmpty) {
      if (_pinnedConversationIds.isEmpty) return;
      _pinnedConversationIds = {};
      unawaited(_persistPinnedIds());
      return;
    }
    final ids = _conversations.map((c) => c.id).toSet();
    final next = _pinnedConversationIds.intersection(ids);
    if (next.length == _pinnedConversationIds.length) return;
    _pinnedConversationIds = next;
    unawaited(_persistPinnedIds());
  }

  List<AiChatAgentStep> get agentSteps => List.unmodifiable(_agentSteps);
  bool get policyAcknowledged => _policyAcknowledged;
  bool get prefsLoaded => _prefsLoaded;
  List<String> get selectedSources => List.unmodifiable(_sourcesSelected);
  String? get streamStatusHint => _streamStatusHint;
  bool get inflightRestoreActive => _inflightRestoreActive;

  /// True when this chat is still generating: active stream on this device, detached while
  /// viewing another tab, or server-side [inflight] from the conversation list.
  bool isConversationOngoingInDrawer(String conversationId) {
    if (conversationId.isEmpty) return false;
    if (conversationId == _conversationId && (_isStreaming || _inflightRestoreActive)) {
      return true;
    }
    if (_detachedAgentStepsByConversationId.containsKey(conversationId)) {
      return true;
    }
    for (final c in _conversations) {
      if (c.id == conversationId) {
        return c.inflightInProgress;
      }
    }
    return false;
  }

  void clearStreamStatusHint() {
    _streamStatusHint = null;
    notifyListeners();
  }

  /// Load policy ack + source toggles (keys aligned with Backoffice `humdb_chatbot_*`).
  Future<void> loadChatUiPrefs() async {
    await _storage.init();
    final ack = await _storage.getString(AppConfig.chatbotAiPolicyAcknowledgedKey);
    _policyAcknowledged = ack == '1';
    final raw = await _storage.getString(AppConfig.chatbotSourcesKey);
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
    _pinnedConversationIds = {};
    final pinsRaw =
        await _storage.getString(AppConfig.chatbotPinnedConversationIdsKey);
    if (pinsRaw != null && pinsRaw.isNotEmpty) {
      try {
        final decoded = jsonDecode(pinsRaw);
        if (decoded is List) {
          _pinnedConversationIds = decoded.map((e) => e.toString()).where((s) => s.isNotEmpty).toSet();
        }
      } catch (_) {
        _pinnedConversationIds = {};
      }
    }
    _prefsLoaded = true;
    notifyListeners();
  }

  Future<void> acknowledgeAiPolicy() async {
    await _storage.init();
    await _storage.setString(AppConfig.chatbotAiPolicyAcknowledgedKey, '1');
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
      final remaining = _sourcesSelected.where((k) => k != key).toList();
      // The backend needs at least one source. Leave the last toggle on instead of
      // silently turning the other two back on.
      if (remaining.isEmpty) return;
      _sourcesSelected = remaining;
    }
    await _storage.init();
    await _storage.setString(
        AppConfig.chatbotSourcesKey, jsonEncode(_sourcesSelected));
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
    final cancelRequestId = _streamRequestId;
    if (_isStreaming) {
      _wsUserCancelled = true;
      if (cancelRequestId != null && cancelRequestId.isNotEmpty) {
        unawaited(_service.cancelChatStream(cancelRequestId));
      }
      await _disconnectWs();
      _isStreaming = false;
      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }
    }
    _clearAgentProgress();
    _streamStatusHint = null;
    _turnNarration = null;
    _activeClientMessageId = null;
    _inflightRestoreActive = false;
    _inflightPollEpoch++;
    _navigationEpoch++;
    notifyListeners();
    if (isAuthenticated && cid != null && cid.isNotEmpty) {
      unawaited(_service.clearConversationInflight(cid));
    }
  }

  void _clearAgentProgress() {
    _agentSteps = [];
    _lastPreparingQueryDetail = null;
  }

  /// Keep the steps already on screen when a later snapshot is shorter.
  ///
  /// The server snapshot lags the live stream. Replacing a longer list with
  /// "Preparing query…" is what made status disappear after the socket dropped.
  static List<AiChatAgentStep> mergeAgentSteps(
    List<AiChatAgentStep> current,
    List<AiChatAgentStep> incoming,
  ) {
    if (incoming.isEmpty) return current;
    if (current.isNotEmpty && incoming.length < current.length) return current;
    return incoming;
  }

  void _rememberInflightSteps([String? conversationId]) {
    final sid = conversationId ?? _conversationId;
    if (sid == null || sid.isEmpty || _agentSteps.isEmpty) return;
    _detachedAgentStepsByConversationId[sid] = _agentSteps
        .map((e) => e.copyWith(detailLines: List<String>.from(e.detailLines)))
        .toList();
  }

  /// App went to the background. The socket may die; the steps must still be here on return.
  void noteAppBackgrounded() {
    if (!_isStreaming && !_inflightRestoreActive) return;
    _rememberInflightSteps();
  }

  void _initAgentProgressIfNeeded() {
    if (_agentSteps.isEmpty) {
      _agentSteps = [const AiChatAgentStep(message: _preparingQueryLabel)];
    }
  }

  String? _firstUserMessageText() {
    for (final m in _messages) {
      if (m.role == 'user' && m.content.trim().isNotEmpty) return m.content;
    }
    return null;
  }

  /// Replace the optimistic user bubble when DLP masked the text the server actually stored.
  void _applyMaskedUserMessage(String masked) {
    for (var i = _messages.length - 1; i >= 0; i--) {
      if (_messages[i].role != 'user') continue;
      if (_messages[i].content == masked) return;
      _messages[i] = _messages[i].copyWith(content: masked);
      final localId = _activeClientMessageId;
      if (localId != null && localId.isNotEmpty) {
        unawaited(_persistence.updateMessageContentByLocalId(
          localMessageId: localId,
          content: masked,
        ));
      }
      return;
    }
  }

  void _beginAssistantTurn({String? clientMessageId}) {
    _turnNarration = null;
    _pendingNarrationSeparator = false;
    _activeClientMessageId = clientMessageId;
    // A previous Stop/Edit sets this so the dying socket does not resubmit. The next turn
    // must start clear, because that socket's onDone often loses the race and never resets it.
    _wsUserCancelled = false;
  }

  String _truncateConversationTitle(String? text) {
    final t = (text ?? '').trim();
    if (t.isEmpty) return '';
    if (t.length > 80) return '${t.substring(0, 80)}...';
    return t;
  }

  /// When the server streams a "Preparing query…" [detail] (raw then rewritten), update the
  /// app bar and drawer to match [Backoffice] `chat-immersive` + `chatbot-optimistic-title`.
  void _applyLiveTitleFromPreparingQueryDetail(String detail) {
    final t = _truncateConversationTitle(detail);
    if (t.isEmpty) return;
    final cid = _conversationId;
    if (cid == null || cid.isEmpty) return;
    final now = DateTime.now();
    final idx = _conversations.indexWhere((c) => c.id == cid);
    final prev = idx >= 0 ? _conversations[idx] : null;
    final convo = AiConversationSummary(
      id: cid,
      title: t,
      updatedAt: now,
      lastMessageAt: prev?.lastMessageAt ?? prev?.updatedAt ?? now,
    );
    if (idx >= 0) {
      _conversations[idx] = convo;
    } else {
      _conversations.insert(0, convo);
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
    }
    unawaited(_persistence.saveConversation(convo));
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
    bool branchFromEdit = false,
    List<Map<String, dynamic>>? branchConversationHistory,
  }) {
    final hist = branchFromEdit && branchConversationHistory != null
        ? branchConversationHistory
        : _conversationHistoryPayload();
    return {
      'type': 'user_message',
      'message': message,
      'conversation_id': _conversationId,
      if (clientMessageId != null && clientMessageId.isNotEmpty) 'client_message_id': clientMessageId,
      'preferred_language': _preferredLanguageCode,
      'page_context': _mobilePageContext(),
      'client': 'mobile',
      'conversationHistory': hist,
      'sources': _sourcesForPayload(),
      'keep_running_on_disconnect': true,
      if (branchFromEdit) 'branch_from_edit': true,
    };
  }

  void _finalizePreviousStepForNext(int index) {
    if (index < 0 || index >= _agentSteps.length) return;
    final step = _agentSteps[index];
    if (step.detailLines.isNotEmpty) return;
    // Only backfill the rewritten-query detail for "Preparing query…"; do not
    // invent a "Done." line — completed steps already show a checkmark.
    if (step.message.trim() == _preparingQueryLabel && _lastPreparingQueryDetail != null) {
      _agentSteps[index] = step.copyWith(detailLines: [_lastPreparingQueryDetail!]);
      _lastPreparingQueryDetail = null;
    }
  }

  void _appendDetailOnStep(int idx, String trimmed) {
    if (idx < 0 || idx >= _agentSteps.length) return;
    final step = _agentSteps[idx];
    final lines = List<String>.from(step.detailLines);
    if (lines.isNotEmpty && lines.last.trim() == trimmed) return;

    if (lines.isNotEmpty) {
      final lastLine = lines.last.trim();
      final lastPipe = _isPipelineProgressDetailLine(lastLine);
      final newPipe = _isPipelineProgressDetailLine(trimmed);
      // In-place: pipeline phase replaces pipeline phase.
      if (newPipe && lastPipe) {
        lines[lines.length - 1] = trimmed;
        _agentSteps[idx] = step.copyWith(detailLines: lines);
        return;
      }
      // Milestone (e.g. “Selected indicator: …”) drops the in-flight spinner line.
      if (!newPipe && lastPipe) {
        lines[lines.length - 1] = trimmed;
        _agentSteps[idx] = step.copyWith(detailLines: lines);
        return;
      }
      // In-flight status after a milestone is a new line.
      if (newPipe && !lastPipe) {
        lines.add(trimmed);
        _agentSteps[idx] = step.copyWith(detailLines: lines);
        return;
      }
    }

    final newP = _progressTickRe.firstMatch(trimmed);
    final lastLine2 = lines.isNotEmpty ? lines.last.trim() : '';
    final lastP = _progressTickRe.firstMatch(lastLine2);
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
      final d = detail.trim();
      _lastPreparingQueryDetail = d;
      _applyLiveTitleFromPreparingQueryDetail(d);
    }

    final last = _agentSteps.isNotEmpty ? _agentSteps.last : null;
    final lastLabel = last?.message ?? '';

    if (last != null && lastLabel.trim() == trimmed) {
      if (detail != null && detail.trim().isNotEmpty) {
        // Server emits "Preparing query…" twice: first with the raw user text (so the
        // row is not empty while rewrite runs), then again with the rewritten query when
        // it differs. Replace detail instead of appending so we do not show both.
        if (trimmed == _preparingQueryLabel) {
          final idx = _agentSteps.length - 1;
          _agentSteps[idx] =
              _agentSteps[idx].copyWith(detailLines: [detail.trim()]);
        } else {
          _appendDetailOnStep(_agentSteps.length - 1, detail.trim());
        }
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

  List<AiChatAgentStep> _stepsFromInflight(Map<String, dynamic> inflight) {
    final steps = inflight['steps'];
    if (steps is! List || steps.isEmpty) return const [];
    final out = <AiChatAgentStep>[];
    for (final s in steps) {
      if (s is! Map) continue;
      final msg = s['message']?.toString() ?? '';
      if (msg.trim().isEmpty) continue;
      final dl = s['detail_lines'];
      final lines = dl is List ? dl.map((e) => e.toString()).toList() : <String>[];
      out.add(AiChatAgentStep(message: msg, detailLines: lines));
    }
    return out;
  }

  void _applyInflightSnapshot(Map<String, dynamic> inflight) {
    final incoming = _stepsFromInflight(inflight);
    final merged = mergeAgentSteps(_agentSteps, incoming);
    _agentSteps = merged.isNotEmpty
        ? merged
        : (_agentSteps.isNotEmpty
            ? _agentSteps
            : [const AiChatAgentStep(message: _preparingQueryLabel)]);
  }

  Map<String, dynamic>? _inflightMapFromConversation(Map<String, dynamic>? getConvResponse) {
    if (getConvResponse == null) return null;
    final conv = getConvResponse['conversation'];
    if (conv is! Map) return null;
    final metaRaw = conv['meta'];
    if (metaRaw is! Map) return null;
    final infRaw = metaRaw['inflight'];
    if (infRaw is! Map || (infRaw['status']?.toString() ?? '') != 'in_progress') return null;
    return Map<String, dynamic>.from(infRaw);
  }

  Future<void> _refreshInflightSnapshot(String conversationId) async {
    try {
      final data = await _service.getConversation(conversationId);
      if (_conversationId != conversationId) return;
      final inflight = _inflightMapFromConversation(data);
      if (inflight == null) return;
      _inflightRestoreActive = true;
      _applyInflightSnapshot(inflight);
      _ensurePlaceholderAssistantForInflight();
      notifyListeners();
    } catch (e) {
      DebugLogger.logWarn('AI', 'Inflight refresh failed: $e');
    }
  }

  /// Pull the in-progress steps back after the app or the chat screen returns.
  ///
  /// A live stream or an `/chat/await` loop keeps its own steps. This only fills
  /// the panel from the server snapshot, and starts a poll when nothing local is
  /// still following the run.
  Future<void> syncInflightAfterResume({required bool isAuthenticated}) async {
    final cid = _conversationId;
    if (!isAuthenticated || cid == null || cid.isEmpty) return;
    if (_isStreaming || _inflightRestoreActive || _storedReplyWaitActive) {
      await _refreshInflightSnapshot(cid);
      return;
    }
    try {
      final data = await _service.getConversation(cid);
      if (_conversationId != cid || _isStreaming || _storedReplyWaitActive) return;
      _maybeRestoreInflight(data, cid, isAuthenticated);
      if (_inflightRestoreActive) notifyListeners();
    } catch (e) {
      DebugLogger.logWarn('AI', 'Resume inflight sync failed: $e');
    }
  }

  void _maybeRestoreInflight(Map<String, dynamic>? getConvResponse, String conversationId, bool isAuthenticated) {
    if (!isAuthenticated || getConvResponse == null) return;
    final inflight = _inflightMapFromConversation(getConvResponse);
    final cached = _detachedAgentStepsByConversationId.remove(conversationId);
    if (inflight == null && (cached == null || cached.isEmpty)) return;
    _inflightRestoreActive = true;
    if (cached != null && cached.isNotEmpty) {
      _agentSteps = cached;
    }
    if (inflight != null) {
      _applyInflightSnapshot(inflight);
    }
    // Match the in-thread layout used while streaming: a trailing empty assistant row
    // holds the progress panel. Without it, [user] is last and the UI only has the
    // column-level inflight bar — which renders *above* the message list.
    _ensurePlaceholderAssistantForInflight();
    _inflightPollEpoch++;
    final epoch = _inflightPollEpoch;
    unawaited(_pollServerInflight(conversationId, epoch, isAuthenticated));
  }

  void _ensurePlaceholderAssistantForInflight() {
    if (_messages.isEmpty) return;
    final last = _messages.last;
    if (last.role == 'assistant' && last.content.isEmpty) return;
    if (last.role == 'user') {
      _messages = [..._messages, AiChatMessage(role: 'assistant', content: '')];
    }
  }

  Future<void> _pollServerInflight(String conversationId, int epoch, bool isAuthenticated) async {
    if (!isAuthenticated) return;
    for (var i = 0; i < _inflightMaxPolls; i++) {
      await Future.delayed(_inflightPollInterval);
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
          // A live stream or /chat/await still owns the panel. One GET without
          // a snapshot must not wipe the steps the user is looking at.
          if (_isStreaming || _storedReplyWaitActive) continue;
          _inflightRestoreActive = false;
          _clearAgentProgress();
          _detachedAgentStepsByConversationId.remove(conversationId);
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
    if (_isStreaming || _storedReplyWaitActive) return;
    _inflightRestoreActive = false;
    _clearAgentProgress();
    _detachedAgentStepsByConversationId.remove(conversationId);
    notifyListeners();
  }

  /// Close the WebSocket and clear streaming UI when the user opens another chat, starts a new
  /// one, or reloads the list. Server generation continues when `keep_running_on_disconnect` is set.
  Future<void> _detachStreamForNavigation() async {
    if (_isStreaming || _inflightRestoreActive) {
      _rememberInflightSteps();
    }
    _inflightPollEpoch++;
    _inflightRestoreActive = false;
    _navigationEpoch++;
    _streamStatusHint = null;
    _turnNarration = null;
    _activeClientMessageId = null;
    await _disconnectWs();
    _isStreaming = false;
    _clearAgentProgress();
    notifyListeners();
  }

  Future<void> _handleWsJson(
    Map<String, dynamic> data, {
    required String outboundMessage,
    required bool isAuthenticated,
  }) async {
    final bound = _wsStreamConversationId;
    final active = _conversationId;
    if (bound != null && active != null && bound != active) {
      return;
    }

    final type = data['type']?.toString();
    if (type == 'meta') {
      final rid = data['request_id']?.toString();
      if (rid != null && rid.isNotEmpty) _streamRequestId = rid;
      final cid = data['conversation_id']?.toString();
      if (cid != null && cid.isNotEmpty && cid != _conversationId) {
        _conversationId = cid;

        // Prefer server `initial_conversation_title` (same as web WS meta) over truncating
        // the first user message locally; both are typically the un-rewritten prompt for now.
        final serverTitle = _truncateConversationTitle(
          data['initial_conversation_title']?.toString(),
        );
        String? title = serverTitle.isNotEmpty ? serverTitle : null;
        if (title == null) {
          final firstUser = (_messages.isNotEmpty && _messages.first.role == 'user')
              ? _messages.first.content
              : null;
          if (firstUser != null) {
            title = _truncateConversationTitle(firstUser);
            if (title.isEmpty) title = null;
          }
        }

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
      _wsStreamConversationId = _conversationId;
      final masked = data['masked_user_message']?.toString().trim() ?? '';
      if (masked.isNotEmpty) {
        _applyMaskedUserMessage(masked);
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

    if (type == 'narration') {
      // Model-written "I'll look up…" — show as normal assistant text; keep progress steps.
      final text = data['text']?.toString().trim() ?? '';
      if (text.isEmpty) return;
      if (_turnNarration == null || _turnNarration!.isEmpty) {
        _turnNarration = text;
      } else if (!_turnNarration!.contains(text)) {
        _turnNarration = '$_turnNarration\n\n$text';
      }
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        final next = last.content.trim().isEmpty
            ? text
            : (last.content.contains(text) ? last.content : '${last.content}\n\n$text');
        _messages[_messages.length - 1] = last.copyWith(content: next);
        _pendingNarrationSeparator = true;
      }
      notifyListeners();
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
        var next = last.content;
        if (delta.isNotEmpty && _pendingNarrationSeparator && next.trim().isNotEmpty) {
          next = '$next\n\n';
          _pendingNarrationSeparator = false;
        }
        _messages[_messages.length - 1] = last.copyWith(content: next + delta);
      }
      return;
    }

    if (type == 'done') {
      _clearAgentProgress();
      _streamStatusHint = null;
      _isStreaming = false;
      _inflightRestoreActive = false;
      _wsStreamConversationId = null;
      final response = data['response']?.toString() ?? '';

      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        final content = composeDoneContent(
          buffer: last.content,
          response: response,
          narration: _turnNarration ?? '',
        );
        final structured = _mergeStructuredPayloads(last.structuredPayloads, coerceStructuredFromEnvelope(data));
        final traceId = _parseTraceId(data['trace_id']) ?? last.traceId;
        var conf = last.confidence;
        var grounding = last.groundingScore;
        final metaMap = data['meta'];
        if (metaMap is Map) {
          final mm = Map<String, dynamic>.from(metaMap);
          conf = _parseDouble(mm['confidence']) ?? conf;
          grounding = _parseDouble(mm['grounding_score']) ?? grounding;
          final masked = mm['masked_user_message']?.toString().trim() ?? '';
          if (masked.isNotEmpty) _applyMaskedUserMessage(masked);
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
      _turnNarration = null;

      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        final last = _messages.last;
        if (last.content.trim().isEmpty && last.structuredPayloads.isEmpty && last.traceId == null) {
          _messages.removeLast();
        }
      }

      if (_conversationId != null && _messages.isNotEmpty) {
        final lastMsg = _messages.last;
        final storedContent = persistedAssistantContent(
          response: response,
          structured: lastMsg.structuredPayloads,
        );
        final contentToStore = storedContent.isNotEmpty ? storedContent : lastMsg.content;
        if (lastMsg.role == 'assistant' &&
            (contentToStore.isNotEmpty || lastMsg.structuredPayloads.isNotEmpty)) {
          await _persistence.saveMessage(
            conversationId: _conversationId!,
            role: 'assistant',
            content: contentToStore,
            localMessageId: _uuid.v4(),
            syncState: AiChatPersistenceService.syncStatePendingServer,
            meta: _assistantPersistMeta(lastMsg),
          );
          final titleIdx = _conversations.indexWhere((c) => c.id == _conversationId);
          final title = titleAfterTurn(
            existingTitle: titleIdx >= 0 ? _conversations[titleIdx].title : null,
            fallback: _firstUserMessageText(),
          );
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
      _activeClientMessageId = null;
      return;
    }

    if (type == 'error') {
      final message = data['message']?.toString() ?? 'Chat failed';
      _turnNarration = null;
      _activeClientMessageId = null;
      if (AiChatHttpException.textDeniesBetaAccess(message)) {
        _clearAgentProgress();
        _isStreaming = false;
        _wsStreamConversationId = null;
        _noteBetaAccessDenial(message);
        return;
      }
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
      _wsStreamConversationId = null;

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

  /// Starts a streamed reply: Server-Sent Events by default, WebSocket when
  /// [AppConfig.aiUseWebSocket] is set (the backend only serves it with `WEBSOCKET_ENABLED=true`).
  Future<void> _runStream({
    required String message,
    required bool isAuthenticated,
    String? clientMessageId,
    bool branchFromEdit = false,
    List<Map<String, dynamic>>? branchConversationHistory,
  }) {
    if (AppConfig.aiUseWebSocket) {
      return _runWebSocketStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: clientMessageId,
        branchFromEdit: branchFromEdit,
        branchConversationHistory: branchConversationHistory,
      );
    }
    return _runSseStream(
      message: message,
      isAuthenticated: isAuthenticated,
      clientMessageId: clientMessageId,
      branchFromEdit: branchFromEdit,
      branchConversationHistory: branchConversationHistory,
    );
  }

  Future<void> _runSseStream({
    required String message,
    required bool isAuthenticated,
    String? clientMessageId,
    bool branchFromEdit = false,
    List<Map<String, dynamic>>? branchConversationHistory,
  }) async {
    await _disconnectWs();
    _wsBranchFromEdit = branchFromEdit;
    _wsBranchConversationHistory = branchConversationHistory;
    _wsStreamConversationId = _conversationId;
    final streamGeneration = _wsConnectionSession;
    var httpFallbackStarted = false;
    var serverAcceptedStream = false;
    var recoveryStarted = false;

    // A stream failure before the server accepted the turn (HTTP status, network, proxy block)
    // retries once over the plain HTTP endpoint, which also renders the backend's error message
    // when the failure is real.
    Future<void> fallbackToHttp() async {
      if (httpFallbackStarted) return;
      httpFallbackStarted = true;
      if (streamGeneration != _wsConnectionSession) return;
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        _messages.removeLast();
      }
      _clearAgentProgress();
      _turnNarration = null;
      await _sendHttpIntoLastAssistant(
        message,
        isAuthenticated: isAuthenticated,
        persistUserMessage: false,
        clientMessageId: clientMessageId,
        branchFromEdit: _wsBranchFromEdit,
        branchConversationHistory: _wsBranchConversationHistory,
      );
    }

    // The request was handed to the network. A timeout or a dropped socket does
    // not mean the server missed it — posting /chat again starts a second agent.
    // Only a failure before the server could accept the socket may resubmit.
    Future<void> recoverOrFallbackToHttp({required bool submitted}) async {
      if (httpFallbackStarted || recoveryStarted) return;
      final cid = _conversationId;
      final turnSubmitted = submitted || serverAcceptedStream;
      if (turnSubmitted) {
        recoveryStarted = true;
        if (streamGeneration != _wsConnectionSession) return;
        if (!isAuthenticated || cid == null || cid.isEmpty || clientMessageId == null || clientMessageId.isEmpty) {
          DebugLogger.logWarn('AI', 'Stream dropped after submit; not starting a second run');
          _isStreaming = false;
          _clearAgentProgress();
          notifyListeners();
          return;
        }
        DebugLogger.logWarn('AI', 'Stream dropped after submit; waiting for the stored reply');
        await _waitForSubmittedTurn(
          message: message,
          isAuthenticated: isAuthenticated,
          conversationId: cid,
          clientMessageId: clientMessageId,
          generation: streamGeneration,
          branchFromEdit: _wsBranchFromEdit,
          branchConversationHistory: _wsBranchConversationHistory,
        );
        return;
      }
      await fallbackToHttp();
    }

    final history = branchFromEdit && branchConversationHistory != null
        ? branchConversationHistory
        : _conversationHistoryPayload();
    final events = _service.streamChatSse(
      message: message,
      conversationId: _conversationId,
      clientMessageId: clientMessageId,
      pageContext: _mobilePageContext(),
      preferredLanguage: _preferredLanguageCode,
      conversationHistory: history,
      sources: _sourcesForPayload(),
      branchFromEdit: branchFromEdit,
      isAuthenticated: isAuthenticated,
    );

    _wsSub = events.listen(
      (data) async {
        try {
          if (streamGeneration != _wsConnectionSession) return;
          if (httpFallbackStarted || recoveryStarted) return;
          if (data['type'] == 'meta') serverAcceptedStream = true;
          await _handleWsJson(data, outboundMessage: message, isAuthenticated: isAuthenticated);
          if (streamGeneration != _wsConnectionSession) return;
          notifyListeners();
        } catch (e) {
          DebugLogger.logWarn('AI', 'Failed to handle SSE event: $e');
        }
      },
      onError: (Object e) async {
        if (streamGeneration != _wsConnectionSession) return;
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        DebugLogger.logWarn('AI', 'SSE stream error: $e');
        if (AiChatHttpException.errorDeniesBetaAccess(e)) {
          _noteBetaAccessDenial(e);
          return;
        }
        final submitted = e is AiChatStreamDisconnected
            ? e.requestMayBeOnServer
            : streamRequestMayBeOnServer(e, handedToNetwork: true);
        await recoverOrFallbackToHttp(submitted: submitted);
      },
      onDone: () async {
        if (streamGeneration != _wsConnectionSession) return;
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        // 'done' / 'error' envelopes clear [_isStreaming]; still streaming means the
        // connection ended without a final envelope. The request was already sent.
        if (!_isStreaming) return;
        DebugLogger.logWarn('AI', 'SSE stream ended before completion');
        await recoverOrFallbackToHttp(submitted: true);
      },
    );
  }

  /// Follows a server-side run that outlived its SSE connection until it persists its reply.
  ///
  /// Returns `false` only when the server confirms the run ended without an assistant reply
  /// (so re-sending is the only way to get an answer). Returns `true` when the reply was loaded,
  /// the user navigated away or cancelled, or the server could not be reached; in the last case
  /// the composer is released without re-sending, since the run may still be going.
  Future<bool> _recoverStreamedTurnFromServer(String conversationId, int generation) async {
    bool superseded() =>
        generation != _wsConnectionSession || _conversationId != conversationId;

    var unreachable = 0;
    for (var i = 0; i < _inflightMaxPolls; i++) {
      if (superseded()) return true;
      Map<String, dynamic> data;
      try {
        data = await _service.getConversation(conversationId);
      } catch (_) {
        if (++unreachable >= 5) break;
        await Future.delayed(_inflightPollInterval);
        continue;
      }
      if (superseded()) return true;
      unreachable = 0;

      Map<String, dynamic>? active;
      final conv = data['conversation'];
      if (conv is Map) {
        final meta = conv['meta'];
        if (meta is Map) {
          final inf = meta['inflight'];
          if (inf is Map && (inf['status']?.toString() ?? '') == 'in_progress') {
            active = Map<String, dynamic>.from(inf);
          }
        }
      }
      if (active != null) {
        _applyInflightSnapshot(active);
        notifyListeners();
        await Future.delayed(_inflightPollInterval);
        continue;
      }

      await _syncConversationFromServer(conversationId);
      if (superseded()) return true;
      final stored = await _persistence.getConversationMessages(conversationId);
      if (superseded()) return true;
      final hasReply = stored.isNotEmpty &&
          stored.last.role == 'assistant' &&
          stored.last.content.trim().isNotEmpty;
      if (!hasReply) return false;
      _messages = stored;
      _isStreaming = false;
      _clearAgentProgress();
      _streamStatusHint = null;
      notifyListeners();
      return true;
    }

    if (superseded()) return true;
    if (_messages.isNotEmpty &&
        _messages.last.role == 'assistant' &&
        _messages.last.content.isEmpty) {
      _messages.removeLast();
    }
    _isStreaming = false;
    _clearAgentProgress();
    _streamStatusHint = null;
    notifyListeners();
    return true;
  }

  Future<void> _runWebSocketStream({
    required String message,
    required bool isAuthenticated,
    String? clientMessageId,
    bool branchFromEdit = false,
    List<Map<String, dynamic>>? branchConversationHistory,
  }) async {
    await _disconnectWs();
    _wsBranchFromEdit = branchFromEdit;
    _wsBranchConversationHistory = branchConversationHistory;
    _wsStreamConversationId = _conversationId;
    final wsListenGeneration = _wsConnectionSession;
    var httpFallbackStarted = false;
    var serverAcceptedStream = false;
    var recoveryStarted = false;
    Future<void> fallbackToHttp() async {
      if (httpFallbackStarted) return;
      httpFallbackStarted = true;
      if (wsListenGeneration != _wsConnectionSession) return;
      // Drop any partial streamed text: the HTTP reply carries the full answer.
      if (_messages.isNotEmpty && _messages.last.role == 'assistant') {
        _messages.removeLast();
      }
      _clearAgentProgress();
      _turnNarration = null;
      await _sendHttpIntoLastAssistant(
        message,
        isAuthenticated: isAuthenticated,
        persistUserMessage: false,
        clientMessageId: clientMessageId,
        branchFromEdit: _wsBranchFromEdit,
        branchConversationHistory: _wsBranchConversationHistory,
      );
    }

    // After the payload is on the socket, a drop must wait for that run.
    // Posting /chat again starts a second agent.
    var payloadSent = false;
    Future<void> recoverOrFallbackToHttp({required bool submitted}) async {
      if (httpFallbackStarted || recoveryStarted) return;
      final cid = _conversationId;
      if (submitted || serverAcceptedStream || payloadSent) {
        recoveryStarted = true;
        if (wsListenGeneration != _wsConnectionSession) return;
        if (!isAuthenticated || cid == null || cid.isEmpty || clientMessageId == null || clientMessageId.isEmpty) {
          DebugLogger.logWarn('AI', 'WebSocket dropped after send; not starting a second run');
          _isStreaming = false;
          _clearAgentProgress();
          notifyListeners();
          return;
        }
        DebugLogger.logWarn('AI', 'WebSocket dropped after send; waiting for the stored reply');
        await _waitForSubmittedTurn(
          message: message,
          isAuthenticated: isAuthenticated,
          conversationId: cid,
          clientMessageId: clientMessageId,
          generation: wsListenGeneration,
          branchFromEdit: _wsBranchFromEdit,
          branchConversationHistory: _wsBranchConversationHistory,
        );
        return;
      }
      await fallbackToHttp();
    }

    _channel = await _service.connectWebSocket();
    _channel!.sink.add(jsonEncode(_webSocketPayload(
      message: message,
      clientMessageId: clientMessageId,
      branchFromEdit: branchFromEdit,
      branchConversationHistory: branchConversationHistory,
    )));
    payloadSent = true;

    _wsSub = _channel!.stream.listen(
      (event) async {
        try {
          if (wsListenGeneration != _wsConnectionSession) return;
          if (httpFallbackStarted || recoveryStarted) return;
          final decoded = jsonDecode(event.toString());
          if (decoded is! Map) return;
          final data = Map<String, dynamic>.from(decoded);
          if (data['type'] == 'meta') serverAcceptedStream = true;

          // When the backend sends auth_required through the WS protocol and the
          // user is authenticated, the bearer token is stale or was never obtained.
          // Mirror the HTTP path's 401/403 retry: clear the stale token and fall
          // back to the HTTP endpoint (which will issue a fresh one automatically).
          if (data['type'] == 'error' &&
              data['error_type'] == 'auth_required' &&
              isAuthenticated) {
            final branchFromEdit = _wsBranchFromEdit;
            final branchHistory = _wsBranchConversationHistory;
            httpFallbackStarted = true;
            _clearAgentProgress();
            _streamStatusHint = null;
            _turnNarration = null;
            notifyListeners();
            unawaited(_disconnectWs());
            await _service.clearToken();
            await _sendHttpIntoLastAssistant(
              message,
              isAuthenticated: isAuthenticated,
              persistUserMessage: false,
              clientMessageId: clientMessageId,
              branchFromEdit: branchFromEdit,
              branchConversationHistory: branchHistory,
            );
            return;
          }

          await _handleWsJson(data, outboundMessage: message, isAuthenticated: isAuthenticated);
          if (wsListenGeneration != _wsConnectionSession) return;
          notifyListeners();
        } catch (e) {
          DebugLogger.logWarn('AI', 'Failed to handle WS message: $e');
        }
      },
      onError: (e) async {
        if (wsListenGeneration != _wsConnectionSession) return;
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        DebugLogger.logWarn('AI', 'WS error: $e');
        if (AiChatHttpException.errorDeniesBetaAccess(e)) {
          _noteBetaAccessDenial(e);
          return;
        }
        await recoverOrFallbackToHttp(submitted: true);
      },
      onDone: () async {
        if (wsListenGeneration != _wsConnectionSession) return;
        if (_wsUserCancelled) {
          _wsUserCancelled = false;
          return;
        }
        // A normal completion ('done' / 'error' envelopes) already cleared [_isStreaming].
        // Still streaming here means the socket closed without a final envelope.
        if (!_isStreaming) return;
        DebugLogger.logWarn('AI', 'WS closed before completion');
        await recoverOrFallbackToHttp(submitted: true);
      },
    );
  }

  Future<void> ensureTokenIfLoggedIn({required bool isAuthenticated}) async {
    if (!isAuthenticated || _betaAccessDenied) return;
    // Best effort: fetch token only if we don't already have one cached.
    // If it fails, cookie auth may still work for HTTP, but WS benefits from token headers.
    try {
      final cached = await _service.getCachedToken();
      if (cached != null && cached.isNotEmpty) return;
      await _service.fetchAndCacheToken();
    } catch (e) {
      _noteBetaAccessDenial(e);
    }
  }

  /// Refreshes the conversation drawer from local DB (and server when online).
  ///
  /// [sessionUserId] should be a stable per-account id (e.g. [User.id]) when [isAuthenticated] is
  /// true. Pass it so we only full-reset when the user actually changed — not on every
  /// [AiChatScreen] rebuild when switching bottom-nav tabs.
  Future<void> loadConversations({
    required bool isAuthenticated,
    String? sessionUserId,
  }) async {
    if (isAuthenticated && (sessionUserId == null || sessionUserId.isEmpty)) {
      return;
    }
    final nextKey = isAuthenticated ? sessionUserId! : 'anon';
    final shouldResetSession = _conversationsListSessionKey == null ||
        _conversationsListSessionKey != nextKey;
    _conversationsListSessionKey = nextKey;

    if (shouldResetSession) {
      await _detachStreamForNavigation();
      // Wipe in-memory state when switching user / auth mode so a previous
      // account's chat never flashes while the new list is loading.
      _conversations = [];
      _conversationId = null;
      _messages = [];
      _pinnedConversationIds = {};
      _error = null;
      _betaAccessDenied = false;
      _detachedAgentStepsByConversationId.clear();
      notifyListeners();
    }

    if (!isAuthenticated) {
      // Logged-out: show locally cached/offline conversations
      _conversations = await _persistence.getAllConversations();
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      _pruneStalePinnedIds();
      notifyListeners();
      return;
    }
    if (_conversations.isEmpty) {
      _isLoading = true;
      notifyListeners();
    }
    try {
      // Load from local DB first (fast). Drop the spinner as soon as there is something to show
      // so the drawer is not blank for the whole server sync.
      _conversations = await _persistence.getAllConversations();
      // Sort by most recent first
      _conversations.sort((a, b) {
        final aTime = a.lastMessageAt ?? a.updatedAt ?? DateTime(0);
        final bTime = b.lastMessageAt ?? b.updatedAt ?? DateTime(0);
        return bTime.compareTo(aTime);
      });
      if (_conversations.isNotEmpty) _isLoading = false;
      notifyListeners();

      // Then sync from server (skip when offline — avoids timeouts)
      if (!shouldDeferRemoteFetch) {
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
          _pruneStalePinnedIds();
        } catch (e) {
          _noteBetaAccessDenial(e);
          DebugLogger.logWarn('AI', 'Failed to sync conversations from server, using local: $e');
          // Keep local conversations if server sync fails
        }
      }
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> openConversation({required bool isAuthenticated, required String conversationId}) async {
    _error = null;
    notifyListeners();
    try {
      await _detachStreamForNavigation();
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
      _noteBetaAccessDenial(e);
      _error = e.toString();
    } finally {
      notifyListeners();
    }
  }

  Future<void> startNewConversation() async {
    await _detachStreamForNavigation();
    _conversationId = null;
    _messages = [];
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;
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
      _detachedAgentStepsByConversationId.remove(conversationId);
      _pinnedConversationIds = {..._pinnedConversationIds}..remove(conversationId);
      await _persistPinnedIds();

      // If this was the current conversation, start a new one
      if (_conversationId == conversationId) {
        await startNewConversation();
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
      _detachedAgentStepsByConversationId.clear();
      _pinnedConversationIds = {};
      await _persistPinnedIds();

      // Start a new conversation
      await startNewConversation();

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
    // Ignore repeat taps while an attempt is still running.
    if (_isStreaming) return;
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

    // Drop the previous failed attempt (error bubbles and empty placeholders) so the
    // retry replaces it instead of stacking another error bubble.
    removeTrailingFailedAttempt(_messages);

    // Add assistant placeholder for streaming
    _messages.add(AiChatMessage(role: 'assistant', content: ''));
    _isStreaming = true;
    _beginAssistantTurn();
    notifyListeners();

    // Anonymous: just use HTTP fallback
    if (!isAuthenticated) {
      await _sendHttpIntoLastAssistant(message, isAuthenticated: false, persistUserMessage: false);
      return;
    }

    _clearAgentProgress();
    _initAgentProgressIfNeeded();
    try {
      await _runStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: null,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'Stream start failed, falling back to HTTP: $e');
      _isStreaming = false;
      _clearAgentProgress();
      notifyListeners();
      await _sendHttpIntoLastAssistant(message, isAuthenticated: isAuthenticated, persistUserMessage: false);
    }
  }

  /// Get message content for editing (doesn't clear messages yet)
  /// Messages will be cleared when sendEditedMessage is called
  String? editMessageAt(int messageIndex, {bool isAuthenticated = true}) {
    if (messageIndex < 0 || messageIndex >= _messages.length) return null;
    final message = _messages[messageIndex];
    if (message.role != 'user') return null;

    // Don't clear messages yet - just return the content for editing
    // Messages will be cleared when sendEditedMessage is called

    // Stop the in-flight server run as well as the local socket. The stream is opened with
    // keep_running_on_disconnect, so dropping the socket alone lets the old worker persist
    // after branch_from_edit has replaced the thread. Bump the navigation epoch so an HTTP
    // fallback already in flight cannot write into this conversation.
    final cid = _conversationId;
    final cancelRequestId = _streamRequestId;
    if (_isStreaming || _inflightRestoreActive) {
      _wsUserCancelled = true;
    }
    _navigationEpoch++;
    _inflightPollEpoch++;
    _inflightRestoreActive = false;
    _isStreaming = false;
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;
    _streamStatusHint = null;
    _turnNarration = null;
    _activeClientMessageId = null;
    _clearAgentProgress();
    if (cancelRequestId != null && cancelRequestId.isNotEmpty) {
      unawaited(_service.cancelChatStream(cancelRequestId));
    }
    unawaited(_disconnectWs());
    if (isAuthenticated && cid != null && cid.isNotEmpty) {
      unawaited(_service.clearConversationInflight(cid));
    }

    notifyListeners();
    return message.content;
  }

  /// Send a message after editing (replaces the message at editIndex and clears all after it).
  ///
  /// When authenticated with a [conversationId], uses the same contract as Backoffice
  /// (`branch_from_edit` + full `conversationHistory` ending with the edited user turn) so
  /// the server replaces rows in place. Logged-out users still fork into a new local chat.
  Future<void> sendEditedMessage({
    required String message,
    required int editIndex,
    required bool isAuthenticated,
  }) async {
    _error = null;
    _errorType = null;
    _retryDelay = null;
    _failedMessage = null;

    final history = <AiChatMessage>[];
    for (int i = 0; i < _messages.length && i < editIndex; i++) {
      final m = _messages[i];
      if (m.role == 'error') continue;
      if (m.role == 'assistant' && m.content.isEmpty) continue;
      history.add(m);
    }

    final branchPayload = <Map<String, dynamic>>[];
    for (final m in history) {
      branchPayload.add({'isUser': m.role == 'user', 'message': m.content});
    }
    branchPayload.add({'isUser': true, 'message': message});

    if (!isAuthenticated || _conversationId == null || _conversationId!.isEmpty) {
      await startNewConversation();
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
          meta: m.role == 'assistant' ? _assistantPersistMeta(m) : null,
        );
      }

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

      await sendMessageStreaming(
        message: message,
        isAuthenticated: isAuthenticated,
        preferredLanguageCode: _preferredLanguageCode,
      );
      return;
    }

    final cid = _conversationId!;
    await _disconnectWs();
    _clearAgentProgress();
    _initAgentProgressIfNeeded();

    await _persistence.deleteAllMessagesForConversation(cid);

    for (final m in history) {
      await _persistence.saveMessage(
        conversationId: cid,
        role: m.role,
        content: m.content,
        localMessageId: _uuid.v4(),
        syncState: AiChatPersistenceService.syncStatePendingServer,
        createdAt: m.createdAt,
        meta: m.role == 'assistant' ? _assistantPersistMeta(m) : null,
      );
    }

    final userLocalId = _uuid.v4();
    await _persistence.saveMessage(
      conversationId: cid,
      role: 'user',
      content: message,
      localMessageId: userLocalId,
      syncState: AiChatPersistenceService.syncStatePendingServer,
    );

    _messages = [
      ...List<AiChatMessage>.from(history),
      AiChatMessage(role: 'user', content: message),
      AiChatMessage(role: 'assistant', content: ''),
    ];
    _isStreaming = true;
    _beginAssistantTurn(clientMessageId: userLocalId);
    notifyListeners();

    try {
      await _runStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: userLocalId,
        branchFromEdit: true,
        branchConversationHistory: branchPayload,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'Stream start failed, falling back to HTTP: $e');
      _isStreaming = false;
      _clearAgentProgress();
      notifyListeners();
      await _sendHttpIntoLastAssistant(
        message,
        isAuthenticated: isAuthenticated,
        persistUserMessage: false,
        clientMessageId: userLocalId,
        branchFromEdit: true,
        branchConversationHistory: branchPayload,
      );
    }
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
    _beginAssistantTurn(clientMessageId: userLocalId);
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
      await _runStream(
        message: message,
        isAuthenticated: isAuthenticated,
        clientMessageId: userLocalId,
      );
    } catch (e) {
      DebugLogger.logWarn('AI', 'Stream start failed, falling back to HTTP: $e');
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

  /// The socket died after the turn was submitted. Keep the steps on screen and
  /// wait for that same run. Do not clear the placeholder or start another agent.
  Future<void> _waitForSubmittedTurn({
    required String message,
    required bool isAuthenticated,
    required String conversationId,
    required String clientMessageId,
    required int generation,
    required bool branchFromEdit,
    required List<Map<String, dynamic>>? branchConversationHistory,
  }) async {
    _rememberInflightSteps(conversationId);
    _inflightRestoreActive = true;
    _isStreaming = true;
    _ensurePlaceholderAssistantForInflight();
    notifyListeners();
    await _sendHttpIntoLastAssistant(
      message,
      isAuthenticated: isAuthenticated,
      persistUserMessage: false,
      clientMessageId: clientMessageId,
      branchFromEdit: branchFromEdit,
      branchConversationHistory: branchConversationHistory,
      preserveProgress: true,
      loadReply: () => _awaitReadyChatResult(
        conversationId: conversationId,
        clientMessageId: clientMessageId,
        generation: generation,
      ),
    );
  }

  /// Blocks until the server delivers the reply for a turn that was already submitted.
  ///
  /// Each call to `/chat/await` returns as soon as the original run finishes, or
  /// after a short wait with `ready: false` so the UI can show progress. This
  /// never starts a second agent run.
  Future<Map<String, dynamic>> _awaitReadyChatResult({
    required String conversationId,
    required String clientMessageId,
    required int generation,
  }) async {
    final deadline = DateTime.now().add(ApiTimeouts.aiChat);
    while (DateTime.now().isBefore(deadline)) {
      if (generation != _wsConnectionSession || _conversationId != conversationId) {
        throw const _TurnSuperseded();
      }
      Map<String, dynamic> data;
      try {
        data = await _service.awaitChatReply(
          conversationId: conversationId,
          clientMessageId: clientMessageId,
        );
      } catch (e) {
        if (e is _TurnSuperseded) rethrow;
        if (generation != _wsConnectionSession || _conversationId != conversationId) {
          throw const _TurnSuperseded();
        }
        DebugLogger.logWarn('AI', 'Waiting for the stored reply failed, retrying: $e');
        await Future.delayed(const Duration(seconds: 2));
        continue;
      }
      if (generation != _wsConnectionSession || _conversationId != conversationId) {
        throw const _TurnSuperseded();
      }
      if (data['ready'] == true) return data;
      if (data['failed'] == true) {
        throw Exception('The assistant could not finish that reply. Please try again.');
      }
      final inf = data['inflight'];
      if (inf is Map) {
        _applyInflightSnapshot(Map<String, dynamic>.from(inf));
        notifyListeners();
      }
    }
    throw TimeoutException('Waiting for the answer timed out');
  }

  Future<void> _sendHttpIntoLastAssistant(
    String message, {
    bool isAuthenticated = false,
    bool persistUserMessage = true,
    String? clientMessageId,
    bool branchFromEdit = false,
    List<Map<String, dynamic>>? branchConversationHistory,
    Future<Map<String, dynamic>> Function()? loadReply,
    bool preserveProgress = false,
  }) async {
    if (!preserveProgress) {
      _clearAgentProgress();
    }
    // Keep an empty assistant row at the tail so the progress panel / typing indicator
    // shows while the HTTP request runs (the WebSocket fallback removes its placeholder).
    if (_messages.isEmpty ||
        _messages.last.role != 'assistant' ||
        _messages.last.content.isNotEmpty) {
      _messages.add(AiChatMessage(role: 'assistant', content: ''));
    }
    if (!preserveProgress || _agentSteps.isEmpty) {
      _initAgentProgressIfNeeded();
    }
    _isStreaming = true;
    if (preserveProgress) _inflightRestoreActive = true;
    if (loadReply != null) _storedReplyWaitActive = true;
    notifyListeners();
    final navEpoch = _navigationEpoch;
    try {
      // For anonymous requests, do not send a conversation_id to the server (server ignores it anyway).
      final serverConversationId = isAuthenticated ? _conversationId : null;
      final hist = isAuthenticated
          ? (branchFromEdit && branchConversationHistory != null
              ? branchConversationHistory
              : _conversationHistoryPayload())
          : null;
      Map<String, dynamic> data;
      try {
        if (loadReply != null) {
          data = await loadReply();
        } else {
          data = await _service.sendMessageHttp(
            message: message,
            conversationId: serverConversationId,
            isAuthenticated: isAuthenticated,
            clientMessageId: isAuthenticated ? clientMessageId : null,
            pageContext: _mobilePageContext(),
            preferredLanguage: _preferredLanguageCode,
            conversationHistory: hist,
            sources: isAuthenticated ? _sourcesForPayload() : null,
            branchFromEdit: branchFromEdit,
          );
        }
      } on AiChatHttpException catch (e) {
        if (loadReply == null &&
            e.backendErrorType == 'turn_in_progress' &&
            serverConversationId != null &&
            serverConversationId.isNotEmpty &&
            clientMessageId != null &&
            clientMessageId.isNotEmpty) {
          DebugLogger.logWarn('AI', 'Chat POST found the turn already running; waiting for that reply');
          data = await _awaitReadyChatResult(
            conversationId: serverConversationId,
            clientMessageId: clientMessageId,
            generation: _wsConnectionSession,
          );
        } else {
          rethrow;
        }
      }
      if (navEpoch != _navigationEpoch) {
        _isStreaming = false;
        notifyListeners();
        return;
      }
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
        final masked = mm['masked_user_message']?.toString().trim() ?? '';
        if (masked.isNotEmpty) _applyMaskedUserMessage(masked);
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
            var userContent = message;
            for (var i = _messages.length - 1; i >= 0; i--) {
              if (_messages[i].role == 'user') {
                userContent = _messages[i].content;
                break;
              }
            }
            await _persistence.saveMessage(
              conversationId: _conversationId!,
              role: 'user',
              content: userContent,
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
          // Keep a rewritten or already-refined title. Only name a chat that has none yet.
          final titleIdx = _conversations.indexWhere((c) => c.id == _conversationId);
          final title = titleAfterTurn(
            existingTitle: titleIdx >= 0 ? _conversations[titleIdx].title : null,
            fallback: _firstUserMessageText() ?? message,
          );
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
      _inflightRestoreActive = false;
      _clearAgentProgress();
      if (_conversationId != null) {
        _detachedAgentStepsByConversationId.remove(_conversationId);
      }
      notifyListeners();
    } catch (e) {
      if (e is _TurnSuperseded || navEpoch != _navigationEpoch) {
        _isStreaming = false;
        notifyListeners();
        return;
      }
      _isStreaming = false; // Stop streaming immediately on error
      _inflightRestoreActive = false;
      _clearAgentProgress();

      if (AiChatHttpException.errorDeniesBetaAccess(e)) {
        _noteBetaAccessDenial(e);
        return;
      }

      // Keep raw string for logging / edge cases; [errorType] drives user-facing copy in the UI.
      String errorMessage = e.toString();
      if (errorMessage.startsWith('Exception: ')) {
        errorMessage = errorMessage.substring(11);
      }

      _error = errorMessage;

      final errorStr = errorMessage.toLowerCase();
      final String? errorType = e is AiChatHttpException
          ? e.chatErrorType
          : _inferChatErrorType(e, errorStr);
      DebugLogger.logWarn(
        'AI',
        'Chat HTTP fallback failed (type=$errorType): $errorMessage',
      );
      if (errorType == 'quota_exceeded') {
        _errorType = 'quota_exceeded';
        final userMessages = _messages.where((m) => m.role == 'user').toList();
        if (userMessages.isNotEmpty) {
          _failedMessage = userMessages.last.content;
        }
      } else {
        _errorType = errorType;
      }

      // Remove the assistant placeholder if it exists
      if (_messages.isNotEmpty && _messages.last.role == 'assistant' && _messages.last.content.isEmpty) {
        _messages.removeLast();
      }

      // Bubble text is resolved in the UI from [errorType] for network/timeout/server.
      _messages.add(AiChatMessage(
        role: 'error',
        content: errorMessage,
        errorType: errorType,
      ));

      notifyListeners();
    } finally {
      _storedReplyWaitActive = false;
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
      if (_conversationId == conversationId) {
        for (final m in _messages) {
          if (m.role != 'assistant' || m.traceId == null) continue;
          final rating = m.userRating;
          if (rating != 'like' && rating != 'dislike') continue;
          await _persistence.updateAssistantRating(
            conversationId: conversationId,
            traceId: m.traceId!,
            userRating: rating!,
          );
        }
      }
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
    _wsConnectionSession++;
    _wsStreamConversationId = null;
    _streamRequestId = null;
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
    bool ok;
    try {
      ok = await _service.submitFeedback(traceId: m.traceId!, rating: r);
    } on AiChatHttpException catch (e) {
      _noteBetaAccessDenial(e);
      return;
    }
    if (!ok) return;
    _messages[messageIndex] = m.copyWith(userRating: r);
    final cid = _conversationId;
    if (cid != null && cid.isNotEmpty) {
      await _persistence.updateAssistantRating(
        conversationId: cid,
        traceId: m.traceId!,
        userRating: r,
      );
    }
    notifyListeners();
  }

  @override
  void dispose() {
    _disconnectWs();
    super.dispose();
  }
}

/// The user left the conversation while `/chat/await` was still open.
class _TurnSuperseded implements Exception {
  const _TurnSuperseded();
}
