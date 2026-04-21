import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../utils/debug_logger.dart';

/// Persists auth form drafts outside the WebView so the same draft is visible
/// across origins (`file://` offline bundle vs `https://` Enter Data). IndexedDB
/// is per-origin; the mobile app bridges via this JSON file in app documents.
class WebViewAuthDraftHostStore {
  WebViewAuthDraftHostStore._();

  static const int _maxFileBytes = 6 * 1024 * 1024;
  static const int _maxPayloadBytes = 2 * 1024 * 1024;

  static Future<File> _file() async {
    final dir = await getApplicationDocumentsDirectory();
    return File(p.join(dir.path, 'webview_auth_drafts.json'));
  }

  static Future<Map<String, dynamic>> _readMap() async {
    final f = await _file();
    if (!await f.exists()) return <String, dynamic>{};
    final s = await f.readAsString();
    if (s.isEmpty) return <String, dynamic>{};
    final decoded = jsonDecode(s);
    if (decoded is Map<String, dynamic>) return decoded;
    if (decoded is Map) {
      return decoded.map((k, v) => MapEntry(k.toString(), v));
    }
    return <String, dynamic>{};
  }

  static Future<void> _writeMap(Map<String, dynamic> map) async {
    final encoded = jsonEncode(map);
    final bytes = utf8.encode(encoded);
    if (bytes.length > _maxFileBytes) {
      DebugLogger.logWarn(
        'AUTH_DRAFT_HOST',
        'store too large (${bytes.length} bytes), not writing',
      );
      throw StateError('draft store exceeds limit');
    }
    final f = await _file();
    await f.writeAsString(encoded, flush: true);
  }

  /// [payloadJson] is a JSON object string: `{ "key", "data", "updatedAt" }`.
  static Future<void> pushPayloadJson(String payloadJson) async {
    final raw = utf8.encode(payloadJson);
    if (raw.length > _maxPayloadBytes) {
      DebugLogger.logWarn(
        'AUTH_DRAFT_HOST',
        'draft payload too large (${raw.length} bytes), ignored',
      );
      return;
    }
    final decoded = jsonDecode(payloadJson);
    if (decoded is! Map) {
      throw ArgumentError('invalid draft payload');
    }
    final key = decoded['key']?.toString();
    if (key == null || key.isEmpty) {
      throw ArgumentError('draft payload missing key');
    }
    if (!key.startsWith('auth:')) {
      throw ArgumentError('unexpected draft key prefix');
    }
    final map = await _readMap();
    map[key] = decoded;
    await _writeMap(map);
  }

  /// Returns JSON string for the record `{ key, data, updatedAt }` or empty string.
  static Future<String> pullByKey(String key) async {
    if (key.isEmpty || !key.startsWith('auth:')) return '';
    final map = await _readMap();
    final v = map[key];
    if (v == null) return '';
    return jsonEncode(v);
  }
}
