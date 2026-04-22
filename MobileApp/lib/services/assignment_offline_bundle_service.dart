import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:html/parser.dart' as html_parser;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../models/shared/assignment.dart';
import '../utils/debug_logger.dart' show DebugLogger, LogLevel;
import '../utils/url_helper.dart';

/// Metadata written alongside [AssignmentOfflineBundleService] disk snapshots.
class AssignmentOfflineBundleMeta {
  const AssignmentOfflineBundleMeta({
    required this.assignmentId,
    this.sourceUrl,
    this.savedAtUtc,
    required this.assetCount,
    this.formDefinitionUpdatedAtIso,
  });

  final int assignmentId;
  final String? sourceUrl;
  final DateTime? savedAtUtc;
  final int assetCount;
  /// ISO-8601 UTC snapshot of [Assignment.formDefinitionUpdatedAt] when the bundle was saved.
  final String? formDefinitionUpdatedAtIso;
}

/// True when the on-disk bundle was captured for an older form definition than the server reports.
bool isAssignmentOfflineBundleStale(
  Assignment assignment,
  AssignmentOfflineBundleMeta? meta,
) {
  final server = assignment.formDefinitionUpdatedAt;
  if (server == null) return false;
  final raw = meta?.formDefinitionUpdatedAtIso;
  if (raw == null || raw.isEmpty) return true;
  final cached = DateTime.tryParse(raw);
  if (cached == null) return true;
  final delta = server.toUtc().millisecondsSinceEpoch -
      cached.toUtc().millisecondsSinceEpoch;
  return delta.abs() > 1500;
}

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
  /// Serialized [savedRelByAbsolute] for post-download / migration HTML rewrites.
  static const String _urlRewriteMapFileName = 'url_rewrite_map.json';
  static const String _offlineRepairStampFile = 'offline_bundle_repair.txt';
  /// Bumped when on-disk layout changes (e.g. flat static paths for ES modules).
  static const String _offlineRepairStampValue = '6';
  /// Legacy flag from earlier builds; removed when v2 repair runs.
  static const String _legacyStaticRootRepairFlag = '.static_root_demoted_v1';
  static const int _maxAssets = 400;
  static const int _maxHtmlBytes = 25 * 1024 * 1024;
  static const int _maxAssetBytes = 12 * 1024 * 1024;

  /// POSIX paths only (URLs in HTML/CSS use forward slashes).
  static final p.Context _posix = p.Context(style: p.Style.posix);

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

  /// Reads [bundle_meta.json] when a valid bundle exists.
  Future<AssignmentOfflineBundleMeta?> readBundleMeta(int assignmentId) async {
    if (!await hasOfflineBundle(assignmentId)) return null;
    final dir = await bundleDirFor(assignmentId);
    final f = File(p.join(dir.path, _metaFileName));
    try {
      final raw = jsonDecode(await f.readAsString());
      if (raw is! Map) return null;
      final savedAtStr = raw['saved_at']?.toString();
      return AssignmentOfflineBundleMeta(
        assignmentId: assignmentId,
        sourceUrl: raw['source_url']?.toString(),
        savedAtUtc: savedAtStr != null
            ? DateTime.tryParse(savedAtStr)?.toLocal()
            : null,
        assetCount: (raw['asset_count'] as num?)?.toInt() ?? 0,
        formDefinitionUpdatedAtIso:
            raw['form_definition_updated_at']?.toString(),
      );
    } catch (_) {
      return null;
    }
  }

  Future<String?> readOfflineIndexHtml(int assignmentId) async {
    if (!await hasOfflineBundle(assignmentId)) return null;
    final dir = await bundleDirFor(assignmentId);
    if (await _bundleUsesFoldedQueryFilenames(dir)) {
      DebugLogger.logWarn(
        'OFFLINE_BUNDLE',
        'Discarding offline bundle assignment=$assignmentId: folded query '
        'filenames break ES module imports; re-download for offline.',
      );
      await deleteBundle(assignmentId);
      return null;
    }
    final stamp = File(p.join(dir.path, _offlineRepairStampFile));
    final stampTxt = (await stamp.exists()) ? (await stamp.readAsString()).trim() : '';
    if (stampTxt != _offlineRepairStampValue) {
      await _rewriteAllCssRootStaticInBundle(dir);
      final indexFile = File(p.join(dir.path, 'index.html'));
      if (await indexFile.exists()) {
        var idx = await indexFile.readAsString();
        final mapFile = File(p.join(dir.path, _urlRewriteMapFileName));
        if (await mapFile.exists()) {
          try {
            final raw = jsonDecode(await mapFile.readAsString());
            if (raw is Map) {
              final m = <String, String>{};
              raw.forEach((k, v) {
                m[k.toString()] = v.toString();
              });
              idx = _rewriteHtmlAssetRefs(idx, m);
            }
          } catch (_) {}
        }
        idx = _demoteHtmlRootStaticPaths(idx);
        idx = _stripStaticUrlCacheQuery(idx);
        await indexFile.writeAsString(idx, flush: true);
      }
      try {
        await File(p.join(dir.path, _legacyStaticRootRepairFlag)).delete();
      } catch (_) {}
      await stamp.writeAsString(_offlineRepairStampValue, flush: true);
      DebugLogger.logInfo(
        'OFFLINE_BUNDLE',
        'Offline bundle repair applied (stamp=$_offlineRepairStampValue) '
        'assignment=$assignmentId',
      );
    }
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
    String? formDefinitionUpdatedAtIso,
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
    final refs = <Uri>{
      ..._collectAssetRefs(doc, pageUri),
      ..._collectStaticRefsFromRawHtml(html, pageUri),
    };

    final sameHostStatic = refs
        .where(
          (u) =>
              u.hasScheme &&
              (u.scheme == 'http' || u.scheme == 'https') &&
              u.host == pageUri.host &&
              u.port == pageUri.port &&
              u.path.startsWith('/static/'),
        )
        .length;
    final otherHostRefs = refs
        .where(
          (u) =>
              u.hasScheme &&
              (u.scheme == 'http' || u.scheme == 'https') &&
              (u.host != pageUri.host || u.port != pageUri.port),
        )
        .length;
    final sameHostNonStatic = refs
        .where(
          (u) =>
              u.hasScheme &&
              (u.scheme == 'http' || u.scheme == 'https') &&
              u.host == pageUri.host &&
              u.port == pageUri.port &&
              !u.path.startsWith('/static/'),
        )
        .length;
    DebugLogger.logInfo(
      'OFFLINE_BUNDLE',
      'HTML refs total=${refs.length} same-host-/static/=$sameHostStatic '
      'same-host-other-path=$sameHostNonStatic other-host=$otherHostRefs '
      'page=${pageUri.host}',
    );

    final dir = await bundleDirFor(assignmentId);
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
    await dir.create(recursive: true);

    final savedRelByAbsolute = <String, String>{};
    var count = 0;

    final pending = ListQueue<Uri>();
    final enqueued = <String>{};

    void enqueue(Uri u) {
      if (!_shouldMirror(u, pageUri)) return;
      final key = u.toString();
      if (enqueued.contains(key)) return;
      enqueued.add(key);
      pending.addLast(u);
    }

    for (final u in refs) {
      enqueue(u);
    }

    while (pending.isNotEmpty && count < _maxAssets) {
      final absolute = pending.removeFirst();
      final absKey = absolute.toString();
      if (savedRelByAbsolute.containsKey(absKey)) {
        continue;
      }

      // Canonical paths so ES module relative imports match on-disk names.
      final relPath = _relativePathForUrl(
        absolute,
        pageUri,
        foldCacheQueryIntoFileName: false,
      );
      final localFile = File(p.join(dir.path, relPath));
      await localFile.parent.create(recursive: true);

      try {
        final r = await _dio.get<List<int>>(
          absKey,
          options: Options(
            responseType: ResponseType.bytes,
            headers: headers,
          ),
        );
        final sc = r.statusCode ?? 0;
        if (sc >= 400 || r.data == null) {
          final isCss = _pathLooksLikeCss(absolute.path);
          if (_mirrorSkipIsBenign404(absolute, sc)) {
            DebugLogger.log(
              'OFFLINE_BUNDLE',
              'Skip optional/missing asset HTTP $sc: $absolute',
              level: LogLevel.debug,
            );
          } else {
            DebugLogger.logWarn(
              'OFFLINE_BUNDLE',
              'Skip asset HTTP $sc${isCss ? ' (CSS)' : ''}: $absolute',
            );
          }
          continue;
        }
        if (r.data!.length > _maxAssetBytes) {
          DebugLogger.logWarn('OFFLINE_BUNDLE', 'Skip large asset: $absolute');
          continue;
        }
        final body = r.data!;
        await localFile.writeAsBytes(body, flush: true);
        final relPosix = relPath.replaceAll(r'\', '/');
        savedRelByAbsolute[absKey] = relPosix;
        _registerMirrorRewriteKeys(absolute, relPosix, savedRelByAbsolute);
        count++;

        if (absolute.path.toLowerCase().endsWith('.css')) {
          final cssText = utf8.decode(body, allowMalformed: true);
          for (final child in _urlsFromCss(cssText, absolute)) {
            enqueue(child);
          }
        }

        final pathLower = absolute.path.toLowerCase();
        if (pathLower.endsWith('.js') || pathLower.endsWith('.mjs')) {
          final jsText = utf8.decode(body, allowMalformed: true);
          for (final child in _urlsFromJavaScript(jsText, absolute)) {
            enqueue(child);
          }
        }

        if (_pathLooksLikeCss(absolute.path)) {
          DebugLogger.logInfo(
            'OFFLINE_BUNDLE',
            'Saved CSS ${body.length}B -> $relPath <= $absolute',
          );
        }
        if (pathLower.endsWith('.js') || pathLower.endsWith('.mjs')) {
          DebugLogger.logInfo(
            'OFFLINE_BUNDLE',
            'Saved JS ${body.length}B -> $relPath <= $absolute',
          );
        }
      } catch (e) {
        final isCss = _pathLooksLikeCss(absolute.path);
        DebugLogger.logWarn(
          'OFFLINE_BUNDLE',
          'Failed asset${isCss ? ' (CSS)' : ''} $absolute: $e',
        );
      }
    }

    if (count >= _maxAssets) {
      DebugLogger.logWarn(
        'OFFLINE_BUNDLE',
        'Stopped after $_maxAssets assets (assignment $assignmentId).',
      );
    }

    await _rewriteAllCssRootStaticInBundle(dir);

    html = _rewriteHtmlAssetRefs(html, savedRelByAbsolute);
    html = _demoteHtmlRootStaticPaths(html);
    html = _stripStaticUrlCacheQuery(html);
    html = _injectOfflineHead(html);

    final indexFile = File(p.join(dir.path, 'index.html'));
    await indexFile.writeAsString(html, flush: true);
    await File(p.join(dir.path, _urlRewriteMapFileName))
        .writeAsString(jsonEncode(savedRelByAbsolute), flush: true);
    await File(p.join(dir.path, _offlineRepairStampFile))
        .writeAsString(_offlineRepairStampValue, flush: true);

    final meta = <String, dynamic>{
      'assignment_id': assignmentId,
      'source_url': resolved,
      'saved_at': DateTime.now().toUtc().toIso8601String(),
      'asset_count': count,
      if (formDefinitionUpdatedAtIso != null &&
          formDefinitionUpdatedAtIso.isNotEmpty)
        'form_definition_updated_at': formDefinitionUpdatedAtIso,
    };
    await File(p.join(dir.path, _metaFileName))
        .writeAsString(jsonEncode(meta), flush: true);

    final cssInIndex =
        RegExp(r'\.css', caseSensitive: false).allMatches(html).length;
    final relStaticCssHrefs = RegExp(
      r'href\s*=\s*"(static/[^"]+\.css[^"]*)"',
      caseSensitive: false,
    ).allMatches(html).length +
        RegExp(
          r"href\s*=\s*'(static/[^']+\.css[^']*)'",
          caseSensitive: false,
        ).allMatches(html).length;
    DebugLogger.logInfo(
      'OFFLINE_BUNDLE',
      'Saved bundle assignment=$assignmentId files=$count '
      'index.html~${html.length}B .css-mentions~$cssInIndex '
      'href=static/*.css~$relStaticCssHrefs dir=${dir.path}',
    );
  }

  bool _pathLooksLikeCss(String path) {
    final lower = path.toLowerCase();
    return lower.endsWith('.css') ||
        lower.contains('output.css') ||
        lower.contains('.css?');
  }

  /// Font Awesome (and similar) reference optional files that are often absent on disk.
  bool _mirrorSkipIsBenign404(Uri u, int statusCode) {
    if (statusCode != 404) return false;
    final lower = u.path.toLowerCase();
    if (lower.contains('fa-v4compatibility')) return true;
    return false;
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

  String _relativePathForUrl(
    Uri absolute,
    Uri pageUri, {
    bool foldCacheQueryIntoFileName = true,
  }) {
    var path = absolute.path;
    if (path.startsWith('/')) path = path.substring(1);
    if (path.isEmpty) path = 'asset.bin';
    if (foldCacheQueryIntoFileName && absolute.hasQuery) {
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

  /// True if any mirrored file used the legacy `name.v_<query>.ext` layout.
  Future<bool> _bundleUsesFoldedQueryFilenames(Directory dir) async {
    try {
      await for (final e in dir.list(recursive: true, followLinks: false)) {
        if (e is! File) continue;
        final name = p.basename(e.path);
        if (name.contains('.v_')) return true;
      }
    } catch (_) {}
    return false;
  }

  /// Strip `?v=…` cache busters from `static/…` URLs so `file://` requests match on-disk names.
  String _stripStaticUrlCacheQuery(String html) {
    return html.replaceAllMapped(
      RegExp(
        r'(static/[\w./-]+\.(?:css|js|mjs|svg|woff2?|map))\?[^">\s\x27\)]*',
        caseSensitive: false,
      ),
      (m) => m[1]!,
    );
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

  /// Picks up `/static/...` URLs embedded in inline scripts (e.g. `static_url(...)` output),
  /// which are not present on `script[src]` / `link[href]` nodes.
  Set<Uri> _collectStaticRefsFromRawHtml(String html, Uri pageUri) {
    final out = <Uri>{};
    final origin = '${pageUri.scheme}://${pageUri.host}'
        '${pageUri.hasPort ? ':${pageUri.port}' : ''}';
    final ext =
        r'(?:js|mjs|css|svg|woff2?|ttf|eot|otf|map|json|ico|wasm|webp|png|jpg|jpeg|gif)';
    final tail = r'/static/[\w./-]+\.' + ext + r'(?:\?[^\s\x22\x27<>]*)?';

    try {
      final absRe = RegExp(RegExp.escape(origin) + tail, caseSensitive: false);
      for (final m in absRe.allMatches(html)) {
        out.add(Uri.parse(m.group(0)!));
      }
    } catch (_) {}

    try {
      final relRe = RegExp(tail, caseSensitive: false);
      for (final m in relRe.allMatches(html)) {
        out.add(pageUri.resolve(m.group(0)!));
      }
    } catch (_) {}

    return out;
  }

  /// Resolves `url(...)` / `@import` references from CSS text (webfonts, nested CSS).
  Set<Uri> _urlsFromCss(String css, Uri cssLocation) {
    final out = <Uri>{};
    void addRaw(String? raw) {
      if (raw == null) return;
      var t = raw.trim();
      if (t.isEmpty ||
          t.startsWith('data:') ||
          t.startsWith('javascript:') ||
          t == '#') {
        return;
      }
      final hash = t.indexOf('#');
      if (hash != -1) t = t.substring(0, hash);
      try {
        if (t.startsWith('//')) {
          out.add(Uri.parse('${cssLocation.scheme}:$t'));
        } else {
          out.add(cssLocation.resolve(t));
        }
      } catch (_) {}
    }

    for (final m in RegExp(
          r'url\(\s*([\x22\x27])([^\x22\x27]+)\1\s*\)',
          caseSensitive: false,
        )
        .allMatches(css)) {
      addRaw(m.group(2));
    }
    for (final m in RegExp(
          r'url\(\s*((?:\.\./|\./|/)[^)\s\x22\x27]+)\s*\)',
          caseSensitive: false,
        )
        .allMatches(css)) {
      addRaw(m.group(1));
    }
    for (final m in RegExp(
          r'@import\s+([\x22\x27])([^\x22\x27]+)\1',
          caseSensitive: false,
        )
        .allMatches(css)) {
      addRaw(m.group(2));
    }
    return out;
  }

  /// Static `import` / `export … from` specifiers in JS modules (not visible in HTML).
  Set<Uri> _urlsFromJavaScript(String js, Uri jsLocation) {
    final out = <Uri>{};
    void addSpec(String? spec) {
      if (spec == null) return;
      var s = spec.trim();
      if (s.isEmpty || s.startsWith('data:')) return;
      if (!s.startsWith('./') &&
          !s.startsWith('../') &&
          !s.startsWith('/static/')) {
        return;
      }
      final hash = s.indexOf('#');
      if (hash != -1) s = s.substring(0, hash);
      final q = s.indexOf('?');
      if (q != -1) s = s.substring(0, q);
      try {
        if (s.startsWith('//')) {
          out.add(Uri.parse('${jsLocation.scheme}:$s'));
        } else {
          out.add(jsLocation.resolve(s));
        }
      } catch (_) {}
    }

    // import … from "…" / '…'
    for (final m in RegExp(
          r'from\s+"(\./[^"]+|\.\./[^"]+|/static/[^"]+)"',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"from\s+'(\./[^']+|\.\./[^']+|/static/[^']+)'",
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    // import "…" / '…' (side-effect)
    for (final m in RegExp(
          r'import\s+"(\./[^"]+|\.\./[^"]+|/static/[^"]+)"',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"import\s+'(\./[^']+|\.\./[^']+|/static/[^']+)'",
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    // import("…") / import('…')
    for (final m in RegExp(
          r'import\s*\(\s*"(\./[^"]+|\.\./[^"]+|/static/[^"]+)"\s*\)',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"import\s*\(\s*'(\./[^']+|\.\./[^']+|/static/[^']+)'\s*\)",
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    return out;
  }

  /// Extra URL strings to rewrite to the on-disk path (query folded into filename).
  void _registerMirrorRewriteKeys(
    Uri absolute,
    String relPosix,
    Map<String, String> map,
  ) {
    if (!absolute.path.startsWith('/static/')) return;
    final rel = relPosix;
    final pathWithQuery =
        absolute.hasQuery ? '${absolute.path}?${absolute.query}' : absolute.path;
    map[pathWithQuery] = rel;

    final tail = absolute.path.startsWith('/static/')
        ? absolute.path.substring('/static/'.length)
        : absolute.path.substring(1);
    final demoted = 'static/$tail';
    if (absolute.hasQuery) {
      map['$demoted?${absolute.query}'] = rel;
    }
    map[demoted] = rel;
  }

  /// Root-relative `/static/` resolves to `file:///static/...` in Android WebView
  /// with a `file://` base URL. Demote to bundle-relative `static/...`.
  String _demoteHtmlRootStaticPaths(String html) {
    var s = html;
    s = s.replaceAllMapped(
      RegExp(
        r'\b(href|src|data-src|data-href|poster)\s*=\s*([\x22\x27])/static/',
        caseSensitive: true,
      ),
      (m) => '${m[1]}=${m[2]}static/',
    );
    s = s.replaceAll('url(/static/', 'url(static/');
    s = s.replaceAll('url("/static/', 'url("static/');
    s = s.replaceAll("url('/static/", "url('static/");
    s = s.replaceAll('@import "/static/', '@import "static/');
    s = s.replaceAll("@import '/static/", "@import 'static/");
    // Inline scripts often build URLs with quoted root-relative paths.
    s = s.replaceAll('"/static/', '"static/');
    s = s.replaceAll("'/static/", "'static/");
    s = s.replaceAll('`/static/', '`static/');
    return s;
  }

  Future<void> _rewriteAllCssRootStaticInBundle(Directory dir) async {
    await for (final entity in dir.list(recursive: true, followLinks: false)) {
      if (entity is! File) continue;
      final lp = entity.path.toLowerCase();
      if (!lp.endsWith('.css')) continue;
      final rel = p.relative(entity.path, from: dir.path).replaceAll(r'\', '/');
      late final String raw;
      try {
        raw = await entity.readAsString(encoding: utf8);
      } catch (_) {
        continue;
      }
      var next = _rewriteCssRootStaticUrls(raw, rel);
      next = _stripStaticUrlCacheQuery(next);
      if (next != raw) {
        await entity.writeAsString(next, flush: true);
        DebugLogger.logInfo(
          'OFFLINE_BUNDLE',
          'Rewrote root /static/ URLs in CSS: $rel',
        );
      }
    }
  }

  /// Rewrites `url(/static/...)` / quoted variants / `@import` to paths relative
  /// to the CSS file (POSIX), so `file://` offline bundles resolve assets correctly.
  String _rewriteCssRootStaticUrls(String css, String fileRelPosix) {
    final relNorm = fileRelPosix.replaceAll(r'\', '/');
    final fromDir =
        relNorm == '.' || relNorm.isEmpty ? '.' : _posix.dirname(relNorm);

    String resolveTargetToUrl(String absStaticPath) {
      final target = absStaticPath.startsWith('/')
          ? absStaticPath.substring(1)
          : absStaticPath;
      if (!target.startsWith('static/')) {
        return absStaticPath;
      }
      var cut = target.length;
      final q = target.indexOf('?');
      final h = target.indexOf('#');
      if (q != -1) cut = q;
      if (h != -1 && h < cut) cut = h;
      final pathOnly = target.substring(0, cut);
      final suffix = cut < target.length ? target.substring(cut) : '';
      try {
        var relUrl = fromDir == '.' || fromDir.isEmpty
            ? pathOnly
            : _posix.relative(pathOnly, from: fromDir);
        relUrl = relUrl.replaceAll(r'\', '/');
        return '$relUrl$suffix';
      } catch (_) {
        return absStaticPath;
      }
    }

    var out = css.replaceAllMapped(
      RegExp(
        r'url\(\s*([\x22\x27])(/static/[^\x22\x27]+)\1\s*\)',
        caseSensitive: false,
      ),
      (m) {
        final quote = m[1]!;
        final path = m[2]!;
        final rel = resolveTargetToUrl(path);
        return 'url($quote$rel$quote)';
      },
    );

    out = out.replaceAllMapped(
      RegExp(r'url\(\s*(/static/[^)\s]+)\s*\)', caseSensitive: false),
      (m) {
        final path = m[1]!;
        final rel = resolveTargetToUrl(path);
        return 'url($rel)';
      },
    );

    out = out.replaceAllMapped(
      RegExp(
        r'@import\s+([\x22\x27])(/static/[^\x22\x27]+)\1',
        caseSensitive: false,
      ),
      (m) {
        final quote = m[1]!;
        final path = m[2]!;
        final rel = resolveTargetToUrl(path);
        return '@import $quote$rel$quote';
      },
    );

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
