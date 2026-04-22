/// One row in the agent/tool progress list (Backoffice `chatbot.js` / `chat-progress-step`).
class AiChatAgentStep {
  final String message;
  final List<String> detailLines;

  const AiChatAgentStep({
    required this.message,
    this.detailLines = const [],
  });

  AiChatAgentStep copyWith({
    String? message,
    List<String>? detailLines,
  }) {
    return AiChatAgentStep(
      message: message ?? this.message,
      detailLines: detailLines ?? List<String>.from(this.detailLines),
    );
  }
}

class AiChatMessage {
  final String role; // 'user' | 'assistant' | 'error'
  final String content;
  final DateTime createdAt;
  final String? errorType; // 'quota_exceeded' | 'server_error' | 'network_error'
  final double? retryDelay; // seconds
  /// Server reasoning trace id (WS `done` / message `meta`) for feedback API.
  final int? traceId;
  /// Local or restored rating: `like` | `dislike`.
  final String? userRating;
  final List<Map<String, dynamic>> structuredPayloads;
  final double? confidence;
  final double? groundingScore;

  AiChatMessage({
    required this.role,
    required this.content,
    DateTime? createdAt,
    this.errorType,
    this.retryDelay,
    this.traceId,
    this.userRating,
    this.structuredPayloads = const [],
    this.confidence,
    this.groundingScore,
  }) : createdAt = createdAt ?? DateTime.now();

  AiChatMessage copyWith({
    String? role,
    String? content,
    DateTime? createdAt,
    String? errorType,
    double? retryDelay,
    int? traceId,
    String? userRating,
    List<Map<String, dynamic>>? structuredPayloads,
    double? confidence,
    double? groundingScore,
    bool clearTraceId = false,
    bool clearUserRating = false,
    bool clearConfidence = false,
    bool clearGroundingScore = false,
  }) {
    return AiChatMessage(
      role: role ?? this.role,
      content: content ?? this.content,
      createdAt: createdAt ?? this.createdAt,
      errorType: errorType ?? this.errorType,
      retryDelay: retryDelay ?? this.retryDelay,
      traceId: clearTraceId ? null : (traceId ?? this.traceId),
      userRating: clearUserRating ? null : (userRating ?? this.userRating),
      structuredPayloads: structuredPayloads ?? List<Map<String, dynamic>>.from(this.structuredPayloads),
      confidence: clearConfidence ? null : (confidence ?? this.confidence),
      groundingScore: clearGroundingScore ? null : (groundingScore ?? this.groundingScore),
    );
  }
}

class AiConversationSummary {
  final String id;
  final String? title;
  final DateTime? updatedAt;
  final DateTime? lastMessageAt;
  /// From GET `/api/ai/v2/conversations` when [meta.inflight.status] is `in_progress` server-side.
  final bool inflightInProgress;

  AiConversationSummary({
    required this.id,
    this.title,
    this.updatedAt,
    this.lastMessageAt,
    this.inflightInProgress = false,
  });

  AiConversationSummary copyWith({
    String? id,
    String? title,
    DateTime? updatedAt,
    DateTime? lastMessageAt,
    bool? inflightInProgress,
  }) {
    return AiConversationSummary(
      id: id ?? this.id,
      title: title ?? this.title,
      updatedAt: updatedAt ?? this.updatedAt,
      lastMessageAt: lastMessageAt ?? this.lastMessageAt,
      inflightInProgress: inflightInProgress ?? this.inflightInProgress,
    );
  }

  factory AiConversationSummary.fromJson(Map<String, dynamic> json) {
    DateTime? dt(String? s) => s == null ? null : DateTime.tryParse(s);
    final inflight = json['inflight'];
    var running = false;
    if (inflight is Map) {
      running = (inflight['status']?.toString() ?? '') == 'in_progress';
    }
    return AiConversationSummary(
      id: json['id']?.toString() ?? '',
      title: json['title']?.toString(),
      updatedAt: dt(json['updated_at']?.toString()),
      lastMessageAt: dt(json['last_message_at']?.toString()),
      inflightInProgress: running,
    );
  }
}
