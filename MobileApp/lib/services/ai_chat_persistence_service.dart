import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'dart:convert';

import '../models/shared/ai_chat.dart';
import '../utils/ai_chat_structured_coerce.dart';
import '../utils/debug_logger.dart';

/// Local SQLite persistence for AI chat conversations and messages.
/// Extends the existing database pattern used by OfflineCacheService.
class AiChatPersistenceService {
  static final AiChatPersistenceService _instance = AiChatPersistenceService._internal();
  factory AiChatPersistenceService() => _instance;
  AiChatPersistenceService._internal();

  static Map<String, dynamic>? _metaMapFromServerField(dynamic raw) {
    if (raw == null) return null;
    if (raw is Map) return Map<String, dynamic>.from(raw);
    if (raw is String && raw.trim().isNotEmpty) {
      try {
        final d = jsonDecode(raw);
        if (d is Map) return Map<String, dynamic>.from(d);
      } catch (_) {}
    }
    return null;
  }

  static AiChatMessage _messageFromRow(Map<String, Object?> map) {
    final meta = _metaMapFromServerField(map['meta']);
    int? traceId;
    if (meta != null) {
      final t = meta['trace_id'];
      if (t is int) {
        traceId = t;
      } else if (t != null) {
        traceId = int.tryParse(t.toString());
      }
    }
    final ur = meta?['user_rating']?.toString();
    final userRating = (ur == 'like' || ur == 'dislike') ? ur : null;

    List<Map<String, dynamic>> structured = [];
    if (meta != null) {
      final sp = meta['structured_payloads'];
      if (sp is List) {
        for (final e in sp) {
          if (e is Map) structured.add(Map<String, dynamic>.from(e));
        }
      }
      if (structured.isEmpty) {
        structured = coerceStructuredFromEnvelope(meta);
      }
    }

    double? conf;
    double? grounding;
    if (meta != null) {
      conf = _parseDouble(meta['confidence']);
      grounding = _parseDouble(meta['grounding_score']);
    }

    return AiChatMessage(
      role: map['role'] as String,
      content: map['content'] as String,
      createdAt: DateTime.tryParse(map['created_at'] as String? ?? '') ?? DateTime.now(),
      traceId: traceId,
      userRating: userRating,
      structuredPayloads: structured,
      confidence: conf,
      groundingScore: grounding,
    );
  }

  static double? _parseDouble(dynamic v) {
    if (v == null) return null;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString());
  }

  static Database? _database;
  static const String _dbName = 'ai_chat.db';
  static const int _dbVersion = 2;

  // Message sync states (SQLite only; UI doesn't need these directly)
  static const String syncStateServer = 'server'; // fetched from server snapshot
  static const String syncStatePendingServer = 'pending_server'; // created while authed, not yet reconciled with server snapshot
  static const String syncStateLocalOnly = 'local_only'; // created while logged-out / anonymous; never sent to server unless imported

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, _dbName);

    return await openDatabase(
      path,
      version: _dbVersion,
      onConfigure: (db) async {
        // Ensure foreign key constraints are enforced (CASCADE deletes)
        await db.execute('PRAGMA foreign_keys = ON');
      },
      onCreate: (db, version) async {
        // Conversations table
        await db.execute('''
          CREATE TABLE ai_conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_message_at TEXT,
            synced_at TEXT,
            meta TEXT
          )
        ''');

        // Messages table
        await db.execute('''
          CREATE TABLE ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            local_message_id TEXT,
            server_message_id INTEGER,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            synced_at TEXT,
            sync_state TEXT NOT NULL DEFAULT 'local_only',
            meta TEXT,
            FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id) ON DELETE CASCADE
          )
        ''');

        // Indexes for faster queries
        await db.execute('''
          CREATE INDEX idx_conversations_updated_at ON ai_conversations(updated_at DESC)
        ''');
        await db.execute('''
          CREATE INDEX idx_messages_conversation_id ON ai_messages(conversation_id)
        ''');
        await db.execute('''
          CREATE INDEX idx_messages_created_at ON ai_messages(created_at)
        ''');
        await db.execute('''
          CREATE INDEX idx_messages_conversation_created_at ON ai_messages(conversation_id, created_at)
        ''');
        await db.execute('''
          CREATE UNIQUE INDEX idx_messages_local_message_id_unique ON ai_messages(local_message_id)
        ''');
        await db.execute('''
          CREATE UNIQUE INDEX idx_messages_server_message_unique
          ON ai_messages(conversation_id, server_message_id)
          WHERE server_message_id IS NOT NULL
        ''');

        DebugLogger.logInfo('AI_CHAT_DB', 'Created AI chat database tables');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          // Add message sync tracking columns (idempotent best-effort)
          try { await db.execute('ALTER TABLE ai_messages ADD COLUMN local_message_id TEXT'); } catch (_) {}
          try { await db.execute('ALTER TABLE ai_messages ADD COLUMN server_message_id INTEGER'); } catch (_) {}
          try { await db.execute("ALTER TABLE ai_messages ADD COLUMN sync_state TEXT NOT NULL DEFAULT 'local_only'"); } catch (_) {}

          // Create additional indexes (best-effort)
          try { await db.execute('CREATE INDEX idx_messages_conversation_created_at ON ai_messages(conversation_id, created_at)'); } catch (_) {}
          try { await db.execute('CREATE UNIQUE INDEX idx_messages_local_message_id_unique ON ai_messages(local_message_id)'); } catch (_) {}
          try {
            await db.execute('''
              CREATE UNIQUE INDEX idx_messages_server_message_unique
              ON ai_messages(conversation_id, server_message_id)
              WHERE server_message_id IS NOT NULL
            ''');
          } catch (_) {}
        }
      },
    );
  }

  /// Save or update a conversation
  Future<void> saveConversation(AiConversationSummary conversation, {Map<String, dynamic>? meta}) async {
    try {
      final db = await database;

      // Preserve created_at if the conversation already exists (avoid rewriting history)
      String? createdAt;
      try {
        final existing = await db.query(
          'ai_conversations',
          columns: ['created_at'],
          where: 'id = ?',
          whereArgs: [conversation.id],
          limit: 1,
        );
        if (existing.isNotEmpty) {
          createdAt = existing.first['created_at'] as String?;
        }
      } catch (_) {}

      await db.insert(
        'ai_conversations',
        {
          'id': conversation.id,
          'title': conversation.title,
          'created_at': createdAt ?? DateTime.now().toIso8601String(),
          'updated_at': conversation.updatedAt?.toIso8601String() ?? DateTime.now().toIso8601String(),
          'last_message_at': conversation.lastMessageAt?.toIso8601String(),
          'synced_at': DateTime.now().toIso8601String(),
          'meta': meta != null ? jsonEncode(meta) : null,
        },
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      DebugLogger.logInfo('AI_CHAT_DB', 'Saved conversation: ${conversation.id}');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to save conversation: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Deletes all locally stored messages for a conversation (all sync states).
  Future<void> deleteAllMessagesForConversation(String conversationId) async {
    try {
      final db = await database;
      await db.delete(
        'ai_messages',
        where: 'conversation_id = ?',
        whereArgs: [conversationId],
      );
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to delete messages for conversation: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Save a message to a conversation
  Future<void> saveMessage({
    required String conversationId,
    required String role,
    required String content,
    String? localMessageId,
    int? serverMessageId,
    String syncState = syncStateLocalOnly,
    DateTime? createdAt,
    Map<String, dynamic>? meta,
  }) async {
    try {
      final db = await database;
      await db.insert(
        'ai_messages',
        {
          'conversation_id': conversationId,
          'local_message_id': localMessageId,
          'server_message_id': serverMessageId,
          'role': role,
          'content': content,
          'created_at': (createdAt ?? DateTime.now()).toIso8601String(),
          'synced_at': DateTime.now().toIso8601String(),
          'sync_state': syncState,
          'meta': meta != null ? jsonEncode(meta) : null,
        },
        // If local_message_id or (conversation_id, server_message_id) hits a unique index, replace is fine.
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      DebugLogger.logInfo('AI_CHAT_DB', 'Saved message to conversation: $conversationId');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to save message: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Replace the server snapshot for a conversation while keeping local-only/pending messages.
  /// This prevents duplicate server messages on repeated sync.
  Future<void> replaceServerMessages({
    required String conversationId,
    required List<Map<String, dynamic>> serverMessages,
  }) async {
    try {
      final db = await database;
      await db.transaction((txn) async {
        await txn.delete(
          'ai_messages',
          where: 'conversation_id = ? AND sync_state = ?',
          whereArgs: [conversationId, syncStateServer],
        );

        for (final m in serverMessages) {
          final serverId = m['id'];
          final role = m['role']?.toString() ?? 'assistant';
          final content = m['content']?.toString() ?? '';
          final createdAtStr = m['created_at']?.toString();
          final createdAt = createdAtStr != null ? DateTime.tryParse(createdAtStr) : null;
          final clientMessageId = m['client_message_id']?.toString();
          // Preserve full server message meta (map_payload / chart_payload / table_payload, trace_id, …)
          // so charts/maps resolve after re-opening a conversation. Previously only
          // client_message_id was stored, so structured UI disappeared after sync.
          var metaMap = <String, dynamic>{};
          final rawMeta = m['meta'];
          if (rawMeta is Map && rawMeta.isNotEmpty) {
            try {
              final decoded = jsonDecode(jsonEncode(rawMeta));
              if (decoded is Map) {
                metaMap = Map<String, dynamic>.from(decoded);
              }
            } catch (_) {
              metaMap = {};
            }
          } else if (rawMeta is String && rawMeta.trim().isNotEmpty) {
            try {
              final decoded = jsonDecode(rawMeta);
              if (decoded is Map) {
                metaMap = Map<String, dynamic>.from(decoded);
              }
            } catch (_) {}
          }
          if (clientMessageId != null && clientMessageId.isNotEmpty) {
            metaMap['client_message_id'] = clientMessageId;
          }
          await txn.insert(
            'ai_messages',
            {
              'conversation_id': conversationId,
              'local_message_id': null,
              'server_message_id': (serverId is int) ? serverId : int.tryParse(serverId?.toString() ?? ''),
              'role': role,
              'content': content,
              'created_at': (createdAt ?? DateTime.now()).toIso8601String(),
              'synced_at': DateTime.now().toIso8601String(),
              'sync_state': syncStateServer,
              'meta': metaMap.isNotEmpty ? jsonEncode(metaMap) : null,
            },
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
        }
      });
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to replace server messages: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Remove pending-server local messages that match a server snapshot (role+content exact match).
  /// This de-dupes messages after the server eventually persists them.
  Future<void> reconcilePendingMessages({
    required String conversationId,
    required List<Map<String, dynamic>> serverMessages,
  }) async {
    try {
      final db = await database;
      final serverKeySet = <String>{};
      final serverClientIds = <String>{};
      for (final m in serverMessages) {
        final role = m['role']?.toString() ?? '';
        final content = m['content']?.toString() ?? '';
        serverKeySet.add('$role\u0000$content');
        final cmid = m['client_message_id']?.toString();
        if (cmid != null && cmid.isNotEmpty) {
          serverClientIds.add(cmid);
        }
      }

      final pending = await db.query(
        'ai_messages',
        columns: ['id', 'local_message_id', 'role', 'content'],
        where: 'conversation_id = ? AND sync_state = ?',
        whereArgs: [conversationId, syncStatePendingServer],
      );

      for (final row in pending) {
        final role = row['role']?.toString() ?? '';
        final content = row['content']?.toString() ?? '';
        final key = '$role\u0000$content';
        final localId = row['local_message_id']?.toString();

        // Prefer strong idempotency match (client_message_id) when available.
        if (localId != null && localId.isNotEmpty && serverClientIds.contains(localId)) {
          await db.delete('ai_messages', where: 'local_message_id = ?', whereArgs: [localId]);
          continue;
        }

        // Fallback: role+content match (best-effort; can be ambiguous).
        if (serverKeySet.contains(key)) {
          if (localId != null && localId.isNotEmpty) {
            await db.delete('ai_messages', where: 'local_message_id = ?', whereArgs: [localId]);
          } else {
            final id = row['id'];
            await db.delete('ai_messages', where: 'id = ?', whereArgs: [id]);
          }
        }
      }
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to reconcile pending messages: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Offline-only messages that have never been sent to the server (useful for import after login).
  Future<List<Map<String, dynamic>>> getLocalOnlyMessagesForImport(String conversationId, {int limit = 200}) async {
    try {
      final db = await database;
      return await db.query(
        'ai_messages',
        columns: ['local_message_id', 'role', 'content', 'created_at'],
        where: 'conversation_id = ? AND sync_state = ?',
        whereArgs: [conversationId, syncStateLocalOnly],
        orderBy: 'created_at ASC',
        limit: limit,
      );
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to get local-only messages: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return [];
    }
  }

  /// Update sync_state for all messages in a conversation (used to prevent repeated imports).
  Future<void> updateConversationMessagesSyncState({
    required String conversationId,
    required String from,
    required String to,
  }) async {
    try {
      final db = await database;
      await db.update(
        'ai_messages',
        {'sync_state': to, 'synced_at': DateTime.now().toIso8601String()},
        where: 'conversation_id = ? AND sync_state = ?',
        whereArgs: [conversationId, from],
      );
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to update message sync_state: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Get all conversations, ordered by most recent
  Future<List<AiConversationSummary>> getAllConversations({int limit = 50}) async {
    try {
      final db = await database;
      final maps = await db.query(
        'ai_conversations',
        orderBy: 'updated_at DESC',
        limit: limit,
      );

      return maps.map((map) {
        DateTime? parseOptionalDateTime(String? s) =>
            s == null ? null : DateTime.tryParse(s);
        return AiConversationSummary(
          id: map['id'] as String,
          title: map['title'] as String?,
          updatedAt: parseOptionalDateTime(map['updated_at'] as String?),
          lastMessageAt: parseOptionalDateTime(map['last_message_at'] as String?),
        );
      }).toList();
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to get conversations: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return [];
    }
  }

  /// Get all messages for a conversation, ordered chronologically
  Future<List<AiChatMessage>> getConversationMessages(String conversationId) async {
    try {
      final db = await database;
      final maps = await db.query(
        'ai_messages',
        where: 'conversation_id = ?',
        whereArgs: [conversationId],
        orderBy: 'created_at ASC',
      );

      return maps.map((map) => _messageFromRow(map)).toList();
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to get messages: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return [];
    }
  }

  /// Delete a conversation and all its messages
  Future<void> deleteConversation(String conversationId) async {
    try {
      final db = await database;
      await db.delete('ai_messages', where: 'conversation_id = ?', whereArgs: [conversationId]);
      await db.delete('ai_conversations', where: 'id = ?', whereArgs: [conversationId]);
      DebugLogger.logInfo('AI_CHAT_DB', 'Deleted conversation: $conversationId');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to delete conversation: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Clear all local conversations (useful for logout or reset)
  Future<void> clearAllConversations() async {
    try {
      final db = await database;
      await db.delete('ai_messages');
      await db.delete('ai_conversations');
      DebugLogger.logInfo('AI_CHAT_DB', 'Cleared all conversations');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to clear conversations: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Mark a conversation as synced (useful for tracking server sync status)
  Future<void> markConversationSynced(String conversationId) async {
    try {
      final db = await database;
      await db.update(
        'ai_conversations',
        {'synced_at': DateTime.now().toIso8601String()},
        where: 'id = ?',
        whereArgs: [conversationId],
      );
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to mark conversation as synced: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }
}
