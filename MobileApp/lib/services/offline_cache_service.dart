import 'dart:convert';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import '../utils/debug_logger.dart';

/// Cached API response
class CachedResponse {
  final String key;
  final String data;
  final DateTime cachedAt;
  final Duration? ttl;
  final Map<String, String>? headers;

  CachedResponse({
    required this.key,
    required this.data,
    DateTime? cachedAt,
    this.ttl,
    this.headers,
  }) : cachedAt = cachedAt ?? DateTime.now();

  bool get isExpired {
    if (ttl == null) return false;
    final age = DateTime.now().difference(cachedAt);
    return age > ttl!;
  }

  Map<String, dynamic> toMap() {
    return {
      'key': key,
      'data': data,
      'cached_at': cachedAt.toIso8601String(),
      'ttl_seconds': ttl?.inSeconds,
      'headers': headers != null ? jsonEncode(headers) : null,
    };
  }

  factory CachedResponse.fromMap(Map<String, dynamic> map) {
    return CachedResponse(
      key: map['key'] as String,
      data: map['data'] as String,
      cachedAt: DateTime.parse(map['cached_at'] as String),
      ttl: map['ttl_seconds'] != null
          ? Duration(seconds: map['ttl_seconds'] as int)
          : null,
      headers: map['headers'] != null
          ? Map<String, String>.from(jsonDecode(map['headers'] as String))
          : null,
    );
  }
}

/// Service for caching API responses for offline access
class OfflineCacheService {
  static final OfflineCacheService _instance = OfflineCacheService._internal();
  factory OfflineCacheService() => _instance;
  OfflineCacheService._internal();

  static Database? _database;
  static const String _tableName = 'api_cache';
  static const Duration _defaultTtl = Duration(hours: 1);

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    final dbPath = await getDatabasesPath();
    final path = join(dbPath, 'offline_cache.db');

    return await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE $_tableName (
            key TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            cached_at TEXT NOT NULL,
            ttl_seconds INTEGER,
            headers TEXT
          )
        ''');

        // Index for faster queries
        await db.execute('''
          CREATE INDEX idx_cached_at ON $_tableName(cached_at)
        ''');
      },
    );
  }

  /// Cache an API response
  Future<void> cacheResponse(
    String key,
    String data, {
    Duration? ttl,
    Map<String, String>? headers,
  }) async {
    try {
      final db = await database;
      final cache = CachedResponse(
        key: key,
        data: data,
        ttl: ttl ?? _defaultTtl,
        headers: headers,
      );

      await db.insert(
        _tableName,
        cache.toMap(),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );

      final previewLength = key.length < 50 ? key.length : 50;
      DebugLogger.logInfo(
        'OFFLINE_CACHE',
        'Cached response for key: ${key.substring(0, previewLength)}...',
      );
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to cache response: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Get cached response if available and not expired
  Future<CachedResponse?> getCachedResponse(String key) async {
    try {
      final db = await database;
      final maps = await db.query(
        _tableName,
        where: 'key = ?',
        whereArgs: [key],
      );

      if (maps.isEmpty) {
        return null;
      }

      final cache = CachedResponse.fromMap(maps.first);

      if (cache.isExpired) {
        // Remove expired cache
        await db.delete(_tableName, where: 'key = ?', whereArgs: [key]);
        DebugLogger.logInfo(
            'OFFLINE_CACHE', 'Expired cache removed for key: $key');
        return null;
      }

      DebugLogger.logInfo('OFFLINE_CACHE', 'Cache hit for key: $key');
      return cache;
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to get cached response: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      return null;
    }
  }

  /// Check if a key is cached and valid
  Future<bool> hasCachedResponse(String key) async {
    final cached = await getCachedResponse(key);
    return cached != null;
  }

  /// Remove a cached response
  Future<void> removeCache(String key) async {
    try {
      final db = await database;
      await db.delete(_tableName, where: 'key = ?', whereArgs: [key]);
      DebugLogger.logInfo('OFFLINE_CACHE', 'Removed cache for key: $key');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to remove cache: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Clear all expired caches
  Future<void> clearExpiredCaches() async {
    try {
      final db = await database;
      final maps = await db.query(_tableName);
      final now = DateTime.now();

      for (final map in maps) {
        final cache = CachedResponse.fromMap(map);
        if (cache.isExpired) {
          await db.delete(_tableName, where: 'key = ?', whereArgs: [cache.key]);
        }
      }

      DebugLogger.logInfo('OFFLINE_CACHE', 'Cleared expired caches');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to clear expired caches: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Clear all caches
  Future<void> clearAll() async {
    try {
      final db = await database;
      await db.delete(_tableName);
      DebugLogger.logInfo('OFFLINE_CACHE', 'Cleared all caches');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to clear all caches: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Get cache size (number of entries)
  Future<int> getCacheSize() async {
    try {
      final db = await database;
      final result =
          await db.rawQuery('SELECT COUNT(*) as count FROM $_tableName');
      return Sqflite.firstIntValue(result) ?? 0;
    } catch (e) {
      DebugLogger.logError('Failed to get cache size: $e');
      return 0;
    }
  }

  /// Generate cache key from endpoint and query params
  static String generateCacheKey(
      String endpoint, Map<String, String>? queryParams,
      {String scope = 'global'}) {
    final key = endpoint;
    if (queryParams != null && queryParams.isNotEmpty) {
      final sortedParams = Map.fromEntries(
          queryParams.entries.toList()..sort((a, b) => a.key.compareTo(b.key)));
      final queryString =
          sortedParams.entries.map((e) => '${e.key}=${e.value}').join('&');
      return '$scope::$key?$queryString';
    }
    return '$scope::$key';
  }
}
