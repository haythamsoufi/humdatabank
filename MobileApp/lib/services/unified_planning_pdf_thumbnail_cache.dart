import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../config/app_config.dart';
import '../utils/debug_logger.dart';

/// JPEG thumbnails for unified-planning PDF URLs (IFRC GO).
///
/// Loads a small server-rendered image from the Backoffice mobile API instead of
/// downloading full PDFs and rendering them on-device. The Backoffice must have
/// ``IFRC_API_USER`` / ``IFRC_API_PASSWORD`` (same IFRC basic auth as document import);
/// the app’s IFRC credentials used for the appeals list are not sent to this endpoint.
///
/// Caches bytes in memory for the session and on disk under the application cache
/// directory (survives app restarts; pruned by LRU when file count grows large).
/// Web builds skip disk (no `dart:io`).
///
/// Local JPEGs (e.g. rendered after opening [PdfViewerScreen]) are merged via
/// [ingestLocalJpeg]; subscribers use [thumbnailReady].
class UnifiedPlanningPdfThumbnailCache {
  UnifiedPlanningPdfThumbnailCache._();
  static final UnifiedPlanningPdfThumbnailCache instance =
      UnifiedPlanningPdfThumbnailCache._();

  /// When false, [getThumbnail] never calls the Backoffice (IFRC creds missing there).
  /// Set from unified-planning-config ``pdf_thumbnail_enabled`` after each config fetch.
  bool _serverThumbnailsEnabled = true;

  set serverThumbnailsEnabled(bool enabled) => _serverThumbnailsEnabled = enabled;

  /// Upper bound on JPEG body size (server renders ~280px wide).
  static const int _maxBytes = 512 * 1024;

  /// Max JPEG files on disk; oldest modified files are removed when over budget.
  static const int _maxDiskFiles = 400;

  /// Success-only memory cache (failed server fetches are not stored).
  final Map<String, Uint8List> _cache = {};
  final Map<String, Future<Uint8List?>> _inFlight = {};

  final StreamController<String> _thumbnailReadyController =
      StreamController<String>.broadcast();

  /// Fires [url] (trimmed) after a JPEG is stored from server or [ingestLocalJpeg].
  Stream<String> get thumbnailReady => _thumbnailReadyController.stream;

  int _activeLoads = 0;
  static const int _maxConcurrent = 4;
  final Queue<Completer<void>> _slotWaiters = Queue<Completer<void>>();

  http.Client? _httpClient;

  Directory? _diskDir;
  Future<Directory?>? _diskDirFuture;
  bool _diskInitFailed = false;

  static String _normKey(String url) => url.trim();

  /// Resolves the on-disk cache folder early (e.g. from [loadUnifiedPlanningDocuments])
  /// so the first thumbnail reads do not pay [getApplicationCacheDirectory] latency alone.
  Future<void> warmCacheDirectory() async {
    await _cacheDir();
  }

  /// Store a JPEG produced on-device (e.g. first page render). Updates memory, disk, and [thumbnailReady].
  Future<void> ingestLocalJpeg(String url, Uint8List jpeg) async {
    final key = _normKey(url);
    if (key.isEmpty) return;
    if (!_isJpeg(jpeg) || jpeg.length > _maxBytes) {
      DebugLogger.logErrorWithTag(
        'PDF_THUMB',
        'ingestLocalJpeg: invalid JPEG or over max (${jpeg.length} bytes)',
      );
      return;
    }
    _cache[key] = jpeg;
    await _writeDisk(key, jpeg);
    if (!_thumbnailReadyController.isClosed) {
      _thumbnailReadyController.add(key);
    }
  }

  /// Synchronous read from memory or disk when [warmCacheDirectory] has already run
  /// (no server I/O). Use from card [initState] so the first frame can show cached JPEGs.
  Uint8List? readThumbnailSync(String url) {
    final key = _normKey(url);
    if (_cache.containsKey(key)) {
      return _cache[key];
    }
    if (kIsWeb || _diskInitFailed) return null;
    final dir = _diskDir;
    if (dir == null) return null;
    try {
      final file = File(p.join(dir.path, '${_urlKey(key)}.jpg'));
      if (!file.existsSync()) return null;
      final bytes = file.readAsBytesSync();
      if (!_isJpeg(bytes)) return null;
      _cache[key] = bytes;
      return bytes;
    } catch (_) {
      return null;
    }
  }

  /// Cached JPEG bytes, or `null` if unavailable.
  ///
  /// Order: **memory → disk → server** (server only on miss).
  Future<Uint8List?> getThumbnail(String url) {
    final key = _normKey(url);
    if (_cache.containsKey(key)) {
      return Future<Uint8List?>.value(_cache[key]);
    }
    return _inFlight.putIfAbsent(
      key,
      () => _load(key).whenComplete(() => _inFlight.remove(key)),
    );
  }

  Future<void> _acquireNetworkSlot() async {
    while (_activeLoads >= _maxConcurrent) {
      final c = Completer<void>();
      _slotWaiters.addLast(c);
      await c.future;
    }
    _activeLoads++;
  }

  void _releaseNetworkSlot() {
    _activeLoads--;
    if (_slotWaiters.isNotEmpty) {
      _slotWaiters.removeFirst().complete();
    }
  }

  Future<Uint8List?> _load(String key) async {
    // Disk hits must not wait on the network semaphore — otherwise a grid of
    // thumbnails after cold start queues 4-at-a-time and feels sluggish.
    final fromDisk = await _readDisk(key);
    if (fromDisk != null) {
      _cache[key] = fromDisk;
      return fromDisk;
    }

    if (!_serverThumbnailsEnabled) {
      // Do not cache null — server may gain IFRC env after deploy without app restart.
      return null;
    }

    await _acquireNetworkSlot();
    try {
      final bytes = await _fetchServerThumbnail(key);
      if (bytes != null && bytes.isNotEmpty) {
        _cache[key] = bytes;
        await _writeDisk(key, bytes);
        if (!_thumbnailReadyController.isClosed) {
          _thumbnailReadyController.add(key);
        }
        return bytes;
      }
      // Do not store failure — allows later retries (reconnect, refresh, etc.).
      return null;
    } finally {
      _releaseNetworkSlot();
    }
  }

  static String _urlKey(String url) =>
      sha256.convert(utf8.encode(url.trim())).toString();

  static bool _isJpeg(Uint8List out) =>
      out.length >= 3 && out[0] == 0xff && out[1] == 0xd8 && out[2] == 0xff;

  Future<Directory?> _cacheDir() async {
    if (kIsWeb || _diskInitFailed) return null;
    if (_diskDir != null) return _diskDir;
    _diskDirFuture ??= _initDiskDir();
    final d = await _diskDirFuture!;
    return d;
  }

  Future<Directory?> _initDiskDir() async {
    try {
      final base = await getApplicationCacheDirectory();
      final dir = Directory(p.join(base.path, 'unified_planning_thumbnails'));
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      _diskDir = dir;
      return dir;
    } catch (e, st) {
      _diskInitFailed = true;
      _diskDirFuture = null;
      DebugLogger.logErrorWithTag('PDF_THUMB', 'Disk cache init: $e\n$st');
      return null;
    }
  }

  Future<Uint8List?> _readDisk(String url) async {
    final dir = await _cacheDir();
    if (dir == null) return null;
    final file = File(p.join(dir.path, '${_urlKey(url)}.jpg'));
    if (!await file.exists()) return null;
    try {
      final bytes = await file.readAsBytes();
      if (!_isJpeg(bytes)) {
        await file.delete();
        return null;
      }
      return bytes;
    } catch (e, st) {
      DebugLogger.logErrorWithTag('PDF_THUMB', 'Disk read: $e\n$st');
      return null;
    }
  }

  Future<void> _writeDisk(String url, Uint8List bytes) async {
    final dir = await _cacheDir();
    if (dir == null) return;
    final file = File(p.join(dir.path, '${_urlKey(url)}.jpg'));
    try {
      await file.writeAsBytes(bytes, flush: true);
      await _pruneDiskCache(dir);
    } catch (e, st) {
      DebugLogger.logErrorWithTag('PDF_THUMB', 'Disk write: $e\n$st');
    }
  }

  Future<void> _pruneDiskCache(Directory dir) async {
    try {
      final files = <File>[];
      await for (final entity in dir.list()) {
        if (entity is File && entity.path.toLowerCase().endsWith('.jpg')) {
          files.add(entity);
        }
      }
      if (files.length <= _maxDiskFiles) return;

      final times = <File, DateTime>{};
      for (final f in files) {
        try {
          times[f] = (await f.stat()).modified;
        } catch (_) {}
      }
      files.sort((a, b) {
        final ta = times[a];
        final tb = times[b];
        if (ta == null) return 1;
        if (tb == null) return -1;
        return ta.compareTo(tb);
      });

      final removeCount = files.length - _maxDiskFiles;
      for (var i = 0; i < removeCount && i < files.length; i++) {
        try {
          await files[i].delete();
        } catch (_) {}
      }
    } catch (_) {}
  }

  Future<Uint8List?> _fetchServerThumbnail(String pdfUrl) async {
    if (pdfUrl.trim().isEmpty) return null;

    // POST JSON with base64url-encoded URL — Azure WAF often still blocks POST bodies
    // that contain raw IFRC SAS/query strings; encoding avoids those signatures.
    final uri = Uri.parse(
      '${AppConfig.baseApiUrl}${AppConfig.mobileUnifiedPlanningThumbnailEndpoint}',
    );

    final headers = <String, String>{
      'Accept': 'image/jpeg',
      'Content-Type': 'application/json; charset=utf-8',
      'User-Agent': 'hum-databank-mobile/1.0',
    };
    final key = AppConfig.apiKey.trim();
    if (key.isNotEmpty) {
      headers['Authorization'] = 'Bearer $key';
    }

    _httpClient ??= http.Client();
    final client = _httpClient!;
    try {
      final req = http.Request('POST', uri)
        ..headers.addAll(headers)
        ..body = jsonEncode(<String, String>{
          'url_b64': base64Url.encode(utf8.encode(pdfUrl)),
        });
      final streamed =
          await client.send(req).timeout(const Duration(seconds: 45));
      if (streamed.statusCode != 200) {
        final errBody = await _readErrorBodyForLog(streamed.stream);
        DebugLogger.logErrorWithTag(
          'PDF_THUMB',
          'HTTP ${streamed.statusCode} for thumbnail${errBody == null ? '' : ': $errBody'}',
        );
        return null;
      }
      final len = streamed.contentLength;
      if (len != null && len > _maxBytes) {
        await streamed.stream.drain();
        return null;
      }
      final chunks = <int>[];
      await for (final chunk in streamed.stream
          .timeout(const Duration(seconds: 45))) {
        chunks.addAll(chunk);
        if (chunks.length > _maxBytes) {
          return null;
        }
      }
      final out = Uint8List.fromList(chunks);
      if (!_isJpeg(out)) {
        DebugLogger.logErrorWithTag(
          'PDF_THUMB',
          'Thumbnail response is not JPEG (${out.length} bytes)',
        );
        return null;
      }
      return out;
    } catch (e, st) {
      DebugLogger.logErrorWithTag('PDF_THUMB', '$e\n$st');
      return null;
    }
  }

  /// Small UTF-8 snippet from a failed JSON (mobile envelope) or raw body for logs.
  static Future<String?> _readErrorBodyForLog(Stream<List<int>> stream) async {
    try {
      final chunks = <int>[];
      await for (final chunk in stream.timeout(const Duration(seconds: 5))) {
        chunks.addAll(chunk);
        if (chunks.length >= 400) break;
      }
      if (chunks.isEmpty) return null;
      final s = utf8.decode(chunks, allowMalformed: true).trim();
      if (s.length > 300) return '${s.substring(0, 300)}…';
      return s.isEmpty ? null : s;
    } catch (_) {
      return null;
    }
  }
}
