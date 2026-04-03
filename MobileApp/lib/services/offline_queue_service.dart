import 'dart:convert';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../utils/debug_logger.dart';

/// Represents a queued API request to be retried when online
class QueuedRequest {
  final int? id;
  final String method; // GET, POST, PUT, DELETE
  final String endpoint;
  final Map<String, String>? queryParams;
  final Map<String, dynamic>? body;
  final bool includeAuth;
  final String? contentType;
  final String ownerKey;
  final DateTime createdAt;
  final int retryCount;
  final String? errorMessage;

  QueuedRequest({
    this.id,
    required this.method,
    required this.endpoint,
    this.queryParams,
    this.body,
    this.includeAuth = true,
    this.contentType,
    required this.ownerKey,
    DateTime? createdAt,
    this.retryCount = 0,
    this.errorMessage,
  }) : createdAt = createdAt ?? DateTime.now();

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'method': method,
      'endpoint': endpoint,
      'query_params': queryParams != null ? jsonEncode(queryParams) : null,
      'body': body != null ? jsonEncode(body) : null,
      'include_auth': includeAuth ? 1 : 0,
      'content_type': contentType,
      'owner_key': ownerKey,
      'created_at': createdAt.toIso8601String(),
      'retry_count': retryCount,
      'error_message': errorMessage,
    };
  }

  factory QueuedRequest.fromMap(Map<String, dynamic> map) {
    return QueuedRequest(
      id: map['id'] as int?,
      method: map['method'] as String,
      endpoint: map['endpoint'] as String,
      queryParams: map['query_params'] != null
          ? Map<String, String>.from(jsonDecode(map['query_params'] as String))
          : null,
      body: map['body'] != null
          ? Map<String, dynamic>.from(jsonDecode(map['body'] as String))
          : null,
      includeAuth: (map['include_auth'] as int) == 1,
      contentType: map['content_type'] as String?,
      ownerKey: map['owner_key'] as String? ?? 'global',
      createdAt: DateTime.parse(map['created_at'] as String),
      retryCount: map['retry_count'] as int,
      errorMessage: map['error_message'] as String?,
    );
  }
}

/// Service for managing offline request queue
class OfflineQueueService {
  static final OfflineQueueService _instance = OfflineQueueService._internal();
  factory OfflineQueueService() => _instance;
  OfflineQueueService._internal();

  static Database? _database;
  static const String _tableName = 'queued_requests';
  static const int _maxRetries = 3;
  static const Duration _retryDelay = Duration(minutes: 5);

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, 'offline_queue.db');

    return await openDatabase(
      path,
      version: 2,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE $_tableName (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            query_params TEXT,
            body TEXT,
            include_auth INTEGER NOT NULL DEFAULT 1,
            content_type TEXT,
            owner_key TEXT NOT NULL DEFAULT 'global',
            created_at TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0,
            error_message TEXT
          )
        ''');

        // Index for faster queries
        await db.execute('''
          CREATE INDEX idx_created_at ON $_tableName(created_at)
        ''');
      },
      onUpgrade: (db, oldVersion, newVersion) async {
        if (oldVersion < 2) {
          await db.execute(
              "ALTER TABLE $_tableName ADD COLUMN owner_key TEXT NOT NULL DEFAULT 'global'");
        }
      },
    );
  }

  /// Queue a failed request for later retry
  Future<int> queueRequest(QueuedRequest request) async {
    try {
      final db = await database;
      final id = await db.insert(_tableName, request.toMap());
      DebugLogger.logInfo('OFFLINE_QUEUE',
          'Queued request: ${request.method} ${request.endpoint} (ID: $id)');
      return id;
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to queue request: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      rethrow;
    }
  }

  /// Get all queued requests
  Future<List<QueuedRequest>> getQueuedRequests(
      {int? limit, String? ownerKey}) async {
    try {
      final db = await database;
      final maps = await db.query(
        _tableName,
        orderBy: 'created_at ASC',
        limit: limit,
        where: ownerKey != null ? 'owner_key = ?' : null,
        whereArgs: ownerKey != null ? [ownerKey] : null,
      );
      return maps.map((map) => QueuedRequest.fromMap(map)).toList();
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to get queued requests: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return [];
    }
  }

  /// Get count of queued requests
  Future<int> getQueuedCount({String? ownerKey}) async {
    try {
      final db = await database;
      final result = await db.rawQuery(
        ownerKey != null
            ? 'SELECT COUNT(*) as count FROM $_tableName WHERE owner_key = ?'
            : 'SELECT COUNT(*) as count FROM $_tableName',
        ownerKey != null ? [ownerKey] : null,
      );
      return Sqflite.firstIntValue(result) ?? 0;
    } catch (e) {
      DebugLogger.logError('Failed to get queued count: $e');
      return 0;
    }
  }

  /// Remove a queued request (after successful retry)
  Future<void> removeRequest(int id) async {
    try {
      final db = await database;
      await db.delete(_tableName, where: 'id = ?', whereArgs: [id]);
      DebugLogger.logInfo('OFFLINE_QUEUE', 'Removed queued request ID: $id');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to remove queued request: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Update retry count for a request
  Future<void> updateRetryCount(int id, int retryCount,
      {String? errorMessage}) async {
    try {
      final db = await database;
      await db.update(
        _tableName,
        {
          'retry_count': retryCount,
          if (errorMessage != null) 'error_message': errorMessage,
        },
        where: 'id = ?',
        whereArgs: [id],
      );
      DebugLogger.logInfo('OFFLINE_QUEUE',
          'Updated retry count for request ID: $id (count: $retryCount)');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to update retry count: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Clear all queued requests
  Future<void> clearAll() async {
    try {
      final db = await database;
      await db.delete(_tableName);
      DebugLogger.logInfo('OFFLINE_QUEUE', 'Cleared all queued requests');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to clear queued requests: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Clear old requests that have exceeded max retries
  Future<void> clearOldRequests() async {
    try {
      final db = await database;
      await db.delete(
        _tableName,
        where: 'retry_count >= ?',
        whereArgs: [_maxRetries],
      );
      DebugLogger.logInfo(
          'OFFLINE_QUEUE', 'Cleared old requests exceeding max retries');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to clear old requests: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Check if a request should be retried
  bool shouldRetry(QueuedRequest request) {
    if (request.retryCount >= _maxRetries) {
      return false;
    }

    // Don't retry too soon after last attempt
    final timeSinceCreation = DateTime.now().difference(request.createdAt);
    if (timeSinceCreation < _retryDelay) {
      return false;
    }

    return true;
  }

  /// Get max retries constant
  int get maxRetries => _maxRetries;
}
