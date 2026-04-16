import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:html/parser.dart' as html_parser;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../utils/debug_logger.dart';
import '../utils/url_helper.dart';

/// Persists a crawlable snapshot of an assignment entry form (HTML + same-origin
/// static assets) so the form can open from disk when the device is offline.
class AssignmentOfflineBundleService {
  AssignmentOfflineBundleService._internal();
  factory AssignmentOfflineBundleService() => _instance;
  static final AssignmentOfflineBundleService _instance =
      AssignmentOfflineBundleService._internal();

  final Dio _dio = Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 30),
      receiveTimeout: const Duration(seconds: 120),
      followRedirects: true,
      maxRedirects: 8,
      validateStatus: (code) => code != null && code < 500,
      headers: {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'identity',
        'X-Mobile-App': 'IFRC-Databank-Flutter',
      },
    ),
  );

  static const String _metaFileName = 'bundle_meta.json';
  static const int _maxAssets = 400;
  static const int _maxHtmlBytes = 25 * 1024 * 1024;
  static const int _maxAssetBytes = 12 * 1024 * 1024;

  Future<Directory> _rootDir() async {
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory(p.join(base.path, 'offline_assignment_bundles'));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  Future<Directory> bundleDirFor(int assignmentId) async {
    final root = await _rootDir();
    return Directory(p.join(root.path, 'assignment_$assignmentId'));
  }

  Future<bool> hasOfflineBundle(int assignmentId) async {
    final dir = await bundleDirFor(assignmentId);
    final index = File(p.join(dir.path, 'index.html'));
    final meta = File(p.join(dir.path, _metaFileName));
    return index.existsSync() && meta.existsSync();
  }

  Future<String?> readOfflineIndexHtml(int assignmentId) async {
    if (!await hasOfflineBundle(assignmentId)) return null;
    final dir = await bundleDirFor(assignmentId);
    final f = File(p.join(dir.path, 'index.html'));
    return f.readAsString();
  }

  Future<String> offlineBundleDirectoryPath(int assignmentId) async {
    final dir = await bundleDirFor(assignmentId);
    return dir.path;
  }

  /// Downloads HTML and same-origin `/static/...` assets referenced in markup.
  Future<void> downloadAndSave({
    required int assignmentId,
    required String formPath,
    required String language,
    String? sessionCookieHeader,
  }) async {
    final resolved = UrlHelper.resolveWebViewInitialUrl(formPath, language);
    final pageUri = Uri.parse(resolved);

    final headers = <String, String>{
      ..._dio.options.headers.map((k, v) => MapEntry(k, v.toString())),
    };
    if (sessionCookieHeader != null && sessionCookieHeader.isNotEmpty) {
      headers['Cookie'] = sessionCookieHeader;
    }

    final htmlResp = await _dio.get<List<int>>(
      resolved,
      options: Options(
        responseType: ResponseType.bytes,
        headers: headers,
      ),
    );

    final status = htmlResp.statusCode ?? 0;
    if (status >= 400) {
      throw AssignmentOfflineBundleException(
        'Failed to load form page (HTTP $status).',
      );
    }

    final bytes = htmlResp.data;
    if (bytes == null || bytes.isEmpty) {
      throw AssignmentOfflineBundleException('Empty response from server.');
    }
    if (bytes.length > _maxHtmlBytes) {
      throw AssignmentOfflineBundleException('Form page is too large to cache offline.');
    }

    var html = utf8.decode(bytes, allowMalformed: true);
    final doc = html_parser.parse(html, generateSpans: false);
    final refs = _collectAssetRefs(doc, pageUri);

    final dir = await bundleDirFor(assignmentId);
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
    await dir.create(recursive: true);

    final savedRelByAbsolute = <String, String>{};
    var count = 0;

    for (final absolute in refs) {
      if (count >= _maxAssets) {
        DebugLogger.logWarn(
          'OFFLINE_BUNDLE',
          'Stopped after $_maxAssets assets (assignment $assignmentId).',
        );
        break;
      }
      if (!_shouldMirror(absolute, pageUri)) continue;

      final relPath = _relativePathForUrl(absolute, pageUri);
      final localFile = File(p.join(dir.path, relPath));
      await localFile.parent.create(recursive: true);

      try {
        final r = await _dio.get<List<int>>(
          absolute.toString(),
          options: Options(
            responseType: ResponseType.bytes,
            headers: headers,
          ),
        );
        final sc = r.statusCode ?? 0;
        if (sc >= 400 || r.data == null) {
          DebugLogger.logWarn(
            'OFFLINE_BUNDLE',
            'Skip asset HTTP $sc: $absolute',
          );
          continue;
        }
        if (r.data!.length > _maxAssetBytes) {
          DebugLogger.logWarn('OFFLINE_BUNDLE', 'Skip large asset: $absolute');
          continue;
        }
        await localFile.writeAsBytes(r.data!, flush: true);
        savedRelByAbsolute[absolute.toString()] = relPath.replaceAll(r'\', '/');
        count++;
      } catch (e) {
        DebugLogger.logWarn('OFFLINE_BUNDLE', 'Failed asset $absolute: $e');
      }
    }

    html = _rewriteHtmlAssetRefs(html, savedRelByAbsolute);
    html = _injectOfflineHead(html);

    final indexFile = File(p.join(dir.path, 'index.html'));
    await indexFile.writeAsString(html, flush: true);

    final meta = <String, dynamic>{
      'assignment_id': assignmentId,
      'source_url': resolved,
      'saved_at': DateTime.now().toUtc().toIso8601String(),
      'asset_count': count,
    };
    await File(p.join(dir.path, _metaFileName))
        .writeAsString(jsonEncode(meta), flush: true);

    DebugLogger.logInfo(
      'OFFLINE_BUNDLE',
      'Saved offline bundle for assignment $assignmentId ($count assets).',
    );
  }

  Future<void> deleteBundle(int assignmentId) async {
    final dir = await bundleDirFor(assignmentId);
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
  }

  bool _shouldMirror(Uri asset, Uri pageUri) {
    if (!asset.hasScheme || (asset.scheme != 'http' && asset.scheme != 'https')) {
      return false;
    }
    if (asset.host != pageUri.host || asset.port != pageUri.port) {
      return false;
    }
    final path = asset.path;
    return path.startsWith('/static/');
  }

  String _relativePathForUrl(Uri absolute, Uri pageUri) {
    var path = absolute.path;
    if (path.startsWith('/')) path = path.substring(1);
    if (path.isEmpty) path = 'asset.bin';
    if (absolute.hasQuery) {
      final ext = p.extension(path);
      final baseName =
          ext.isNotEmpty ? path.substring(0, path.length - ext.length) : path;
      final safeQ = absolute.query.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
      final short =
          safeQ.length > 40 ? safeQ.substring(0, 40) : safeQ;
      path = ext.isNotEmpty ? '$baseName.$short$ext' : '${baseName}_$short';
    }
    return path;
  }

  Set<Uri> _collectAssetRefs(dynamic doc, Uri pageUri) {
    final out = <Uri>{};
    void addRaw(String? raw) {
      if (raw == null) return;
      final t = raw.trim();
      if (t.isEmpty) return;
      if (t.startsWith('data:') ||
          t.startsWith('javascript:') ||
          t.startsWith('mailto:') ||
          t == '#') {
        return;
      }
      try {
        if (t.startsWith('//')) {
          out.add(Uri.parse('${pageUri.scheme}:$t'));
        } else {
          out.add(pageUri.resolve(t));
        }
      } catch (_) {}
    }

    for (final n in doc.querySelectorAll('script[src]')) {
      addRaw(n.attributes['src']);
    }
    for (final n in doc.querySelectorAll('link[href]')) {
      addRaw(n.attributes['href']);
    }
    for (final n in doc.querySelectorAll('img[src]')) {
      addRaw(n.attributes['src']);
    }
    for (final n in doc.querySelectorAll('source[src]')) {
      addRaw(n.attributes['src']);
    }
    return out;
  }

  /// Rewrites occurrences of mirrored absolute URLs to relative paths.
  String _rewriteHtmlAssetRefs(
    String html,
    Map<String, String> savedRelByAbsolute,
  ) {
    var s = html;
    final keys = savedRelByAbsolute.keys.toList()
      ..sort((a, b) => b.length.compareTo(a.length));
    for (final abs in keys) {
      final rel = savedRelByAbsolute[abs]!;
      final uri = Uri.parse(abs);
      final withoutQuery =
          Uri(scheme: uri.scheme, userInfo: uri.userInfo, host: uri.host, port: uri.port, path: uri.path)
              .toString();
      for (final candidate in <String>{abs, withoutQuery}) {
        s = s.split(candidate).join(rel);
        final esc = const HtmlEscape().convert(candidate);
        if (esc != candidate) {
          s = s.split(esc).join(rel);
        }
      }
    }
    return s;
  }

  /// Disables service worker registration and stubs `getStaticUrl` for disk layout.
  String _injectOfflineHead(String html) {
    const patch = r'''
<script>
(function () {
  try {
    if (navigator.serviceWorker && navigator.serviceWorker.register) {
      navigator.serviceWorker.register = function () { return Promise.resolve({}); };
    }
  } catch (e) {}
  try {
    window.getStaticUrl = function (filename) {
      filename = String(filename || '').replace(/^\/+/, '').replace(/^static\/+/, '');
      return 'static/' + filename;
    };
  } catch (e) {}
})();
</script>
''';
    final lower = html.toLowerCase();
    final idx = lower.indexOf('</head>');
    if (idx != -1) {
      return html.substring(0, idx) + patch + html.substring(idx);
    }
    return patch + html;
  }
}

class AssignmentOfflineBundleException implements Exception {
  final String message;
  AssignmentOfflineBundleException(this.message);

  @override
  String toString() => message;
}
