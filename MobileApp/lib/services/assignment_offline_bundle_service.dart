import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show ValueNotifier, visibleForTesting;
import 'package:html/parser.dart' as html_parser;
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import '../utils/debug_logger.dart';
import '../utils/url_helper.dart';
import 'offline/offline_asset_scanner.dart';
import 'offline/offline_form_store.dart';

export 'offline/offline_form_store.dart'
    show
        OfflineFormStatus,
        OfflineFormsIndex,
        OfflinePackageMeta,
        OfflinePackageSummary,
        OfflinePageMeta,
        evaluateOfflineForm,
        isOfflinePackageCurrent,
        offlinePackageKey;

/// Everything needed to save one assignment's form for offline use.
class OfflineFormRequest {
  const OfflineFormRequest({
    required this.assignmentId,
    required this.formPath,
    required this.language,
    this.templateId,
    this.sessionCookieHeader,
    this.formDefinitionUpdatedAtIso,
    this.staticVersion,
    this.dataVersion,
    this.title,
    this.submitBlockedMessage =
        'You are offline. Your changes are saved as a draft on this device. '
        'Submit when you are back online; the form is validated before it is submitted.',
    this.recordApiResponses,
    this.cancelToken,
  });

  final int assignmentId;
  final String formPath;
  final String language;
  final int? templateId;
  final String? sessionCookieHeader;
  final String? formDefinitionUpdatedAtIso;
  final String? staticVersion;
  final String? dataVersion;
  final String? title;
  final String submitBlockedMessage;

  /// Loads the form and returns the API responses it fetched. Only used when
  /// the template's shared files are saved.
  final Future<List<Map<String, dynamic>>> Function(String formUrl)?
  recordApiResponses;

  /// Aborts every request of the operation (used for time limits).
  final CancelToken? cancelToken;

  String get packageKey =>
      offlinePackageKey(templateId: templateId, assignmentId: assignmentId);
}

class AssignmentOfflineBundleException implements Exception {
  AssignmentOfflineBundleException(this.message, {this.details = const {}});

  final String message;
  final Map<String, dynamic> details;

  @override
  String toString() => message;
}

/// Runs async operations one at a time per key.
class _KeyedMutex {
  final Map<String, Future<void>> _tails = {};

  Future<T> run<T>(String key, Future<T> Function() action) {
    final previous = _tails[key] ?? Future<void>.value();
    final completer = Completer<T>();
    final tail = previous.then((_) async {
      try {
        completer.complete(await action());
      } catch (e, st) {
        completer.completeError(e, st);
      }
    });
    _tails[key] = tail;
    tail.whenComplete(() {
      if (identical(_tails[key], tail)) _tails.remove(key);
    });
    return completer.future;
  }
}

/// Large inputs are processed in a background isolate so the UI never stalls.
Future<R> _inBackground<A, R>(
  R Function(A) work,
  A input, {
  required int weight,
}) {
  if (weight < 40000) return Future<R>.value(work(input));
  return Isolate.run(() => work(input));
}

({List<String> dom, List<String> all}) _analyzePage((String, String) input) {
  final pageUri = Uri.parse(input.$2);
  final doc = html_parser.parse(input.$1, generateSpans: false);
  final dom = OfflineAssetScanner.collectAssetRefs(doc, pageUri);
  final raw = OfflineAssetScanner.collectStaticRefsFromRawHtml(
    input.$1,
    pageUri,
  );
  return (
    dom: [for (final u in dom) u.toString()],
    all: {
      for (final u in dom) u.toString(),
      for (final u in raw) u.toString(),
    }.toList(),
  );
}

({List<String> refs, List<String> literals}) _scanChildren(
  ({String kind, String text, String location, bool plugin}) input,
) {
  final location = Uri.parse(input.location);
  if (input.kind == 'css') {
    return (
      refs: [
        for (final u in OfflineAssetScanner.urlsFromCss(input.text, location))
          u.toString(),
      ],
      literals: const <String>[],
    );
  }
  return (
    refs: [
      for (final u in OfflineAssetScanner.urlsFromJavaScript(
        input.text,
        location,
      ))
        u.toString(),
    ],
    literals: input.plugin
        ? [
            for (final u in OfflineAssetScanner.staticLiteralsFromJavaScript(
              input.text,
              location,
            ))
              u.toString(),
          ]
        : const <String>[],
  );
}

String _renderPage(
  ({String html, Map<String, String> assets, String message}) input,
) {
  var html = OfflineAssetScanner.rewriteHtmlAssetRefs(input.html, input.assets);
  html = OfflineAssetScanner.demoteHtmlRootStaticPaths(html);
  html = OfflineAssetScanner.stripStaticUrlCacheQuery(html);
  return OfflineAssetScanner.injectOfflineHead(html, input.message);
}

class _FetchedPage {
  _FetchedPage({
    required this.html,
    required this.resolved,
    required this.pageUri,
    required this.headers,
    required this.refs,
    required this.domRefs,
  });

  final String html;
  final String resolved;
  final Uri pageUri;
  final Map<String, String> headers;
  final Set<Uri> refs;
  final Set<String> domRefs;
}

class _CrawlOutcome {
  final List<String> savedPaths = [];
  final List<Uri> missing = [];
  final List<Uri> critical = [];
}

/// Saves entry forms so they open from disk without a connection.
///
/// A form template is saved once as a *package* (scripts, styles, fonts,
/// third-party files and the API data the form loads). Each assignment of that
/// template adds only a small *page* (the server-rendered form with its data).
/// Opening another entity's form of an already saved template therefore never
/// downloads the package again; see [OfflineFormStore] for the layout.
class AssignmentOfflineBundleService {
  /// Bumped when saved forms are removed so open screens can refresh.
  static final ValueNotifier<int> savedCopiesChanged = ValueNotifier<int>(0);

  /// Bumped when the "keep open forms available offline" preference changes.
  static final ValueNotifier<int> autoDownloadChanged = ValueNotifier<int>(0);

  static const String _autoDownloadPrefKey = 'offline_auto_download_open_forms';
  static const int _maxAssets = 1500;
  static const int _crawlWorkers = 6;
  static const int _maxHtmlBytes = 25 * 1024 * 1024;
  static const int _maxAssetBytes = 12 * 1024 * 1024;
  static const int _maxApiEntryBytes = 4 * 1024 * 1024;
  static const int _maxApiCacheBytes = 20 * 1024 * 1024;
  static const Duration _recordingTimeout = Duration(seconds: 60);

  AssignmentOfflineBundleService._internal()
    : _dio = _buildDio(),
      _store = OfflineFormStore();

  /// Test hook: inject the HTTP client, storage directory and user scope.
  @visibleForTesting
  AssignmentOfflineBundleService.forTesting({
    required Dio dio,
    required Directory baseDir,
    String scope = 'user_test',
  }) : _dio = dio,
       _store = OfflineFormStore(baseDir: baseDir, scope: scope);

  factory AssignmentOfflineBundleService() => _instance;
  static final AssignmentOfflineBundleService _instance =
      AssignmentOfflineBundleService._internal();

  static Dio _buildDio() => Dio(
    BaseOptions(
      connectTimeout: const Duration(seconds: 20),
      receiveTimeout: const Duration(seconds: 60),
      followRedirects: true,
      maxRedirects: 8,
      validateStatus: (code) => code != null && code < 500,
      headers: {
        'Accept':
            'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Encoding': 'identity',
        'X-Mobile-App': 'IFRC-Databank-Flutter',
      },
    ),
  );

  final Dio _dio;
  final OfflineFormStore _store;
  final _KeyedMutex _locks = _KeyedMutex();
  final Map<int, List<String>> _traces = {};
  int _epoch = 0;

  // ---------------------------------------------------------------- tracing

  /// Step-by-step record of the latest save attempt for [assignmentId] (paths
  /// and outcomes only; never cookies or tokens). Sent with failure reports.
  List<String> traceFor(int assignmentId) =>
      List.unmodifiable(_traces[assignmentId] ?? const <String>[]);

  void _trace(int assignmentId, String line) {
    final list = _traces.putIfAbsent(assignmentId, () => <String>[]);
    if (list.length >= 120) list.removeAt(0);
    list.add(line.length > 300 ? line.substring(0, 300) : line);
  }

  static String _tracePath(Uri u) => u.path.isEmpty
      ? u.host
      : (u.host.isEmpty ? u.path : '${u.host}${u.path}');

  static String _describeError(Object e) {
    if (e is DioException) {
      final code = e.response?.statusCode;
      return 'dio:${e.type.name}${code != null ? ' HTTP $code' : ''}'
          '${e.message != null ? ' (${e.message})' : ''}';
    }
    return '${e.runtimeType}: $e';
  }

  // ------------------------------------------------------------ preferences

  /// When on, open forms of every template are saved on Wi-Fi, not only of
  /// templates that were downloaded by hand.
  Future<bool> isAutoDownloadEnabled() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return prefs.getBool(_autoDownloadPrefKey) ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<void> setAutoDownloadEnabled(bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_autoDownloadPrefKey, enabled);
    autoDownloadChanged.value++;
  }

  // ---------------------------------------------------------------- reading

  Future<OfflineFormsIndex> readIndex() => _store.readIndex();

  /// Absolute path of the saved page for [assignmentId], or null.
  Future<String?> offlinePagePath(int assignmentId) =>
      _store.pagePath(assignmentId);

  Future<bool> hasOfflineForm(int assignmentId) async =>
      await _store.pagePath(assignmentId) != null;

  Future<List<OfflinePackageSummary>> listPackages() => _store.listPackages();

  // ---------------------------------------------------------------- removal

  /// Removes the saved template of an assignment (its package and every page).
  Future<void> removeForAssignment({
    required int assignmentId,
    int? templateId,
  }) async {
    final key = offlinePackageKey(
      templateId: templateId,
      assignmentId: assignmentId,
    );
    await _locks.run(key, () async {
      if (templateId != null) {
        await _store.deleteTemplate(templateId, alsoAssignmentId: assignmentId);
      } else {
        await _store.deletePackage(key);
      }
    });
    savedCopiesChanged.value++;
  }

  Future<void> removePackage(OfflinePackageSummary summary) async {
    await _locks.run(summary.key, () => _store.deletePackage(summary.key));
    savedCopiesChanged.value++;
  }

  /// Deletes every saved form for every user (used on logout).
  Future<void> clearAll() async {
    _epoch++;
    savedCopiesChanged.value++;
    try {
      await _store.deleteAll();
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_BUNDLE', 'clearAll failed: $e');
    }
  }

  /// Frees storage held by closed assignments and surplus pages.
  Future<int> pruneBundles({
    Set<int> closedAssignmentIds = const {},
    Duration maxAge = const Duration(days: 90),
    int maxPages = 80,
    DateTime? now,
  }) async {
    final index = await _store.readIndex();
    final keys = index.packages.keys.toList();
    var removed = 0;
    Future<void> prune() async {
      removed = await _store.prune(
        closedAssignmentIds: closedAssignmentIds,
        maxAge: maxAge,
        maxPages: maxPages,
        now: now,
      );
    }

    Future<void> chain(int i) =>
        i >= keys.length ? prune() : _locks.run(keys[i], () => chain(i + 1));
    await chain(0);
    if (removed > 0) savedCopiesChanged.value++;
    return removed;
  }

  // ------------------------------------------------------------- API cache

  Map<String, dynamic> _mergeApiEntries(
    Map<String, dynamic> existing,
    List<Map<String, dynamic>> incoming,
  ) {
    final out = Map<String, dynamic>.from(existing);
    final now = DateTime.now().toUtc().toIso8601String();
    for (final e in incoming) {
      final key = e['k']?.toString();
      final body = e['b']?.toString();
      if (key == null || key.isEmpty || body == null) continue;
      if (body.length > _maxApiEntryBytes) continue;
      out[key] = {
        's': (e['s'] as num?)?.toInt() ?? 200,
        't': e['t']?.toString() ?? 'application/json',
        'b': body,
        'at': now,
      };
    }
    var total = out.values.fold<int>(
      0,
      (sum, v) => sum + ((v as Map)['b'] as String).length,
    );
    if (total > _maxApiCacheBytes) {
      final byAge = out.entries.toList()
        ..sort(
          (a, b) => ((a.value as Map)['at'] as String).compareTo(
            (b.value as Map)['at'] as String,
          ),
        );
      for (final entry in byAge) {
        if (total <= _maxApiCacheBytes) break;
        total -= ((entry.value as Map)['b'] as String).length;
        out.remove(entry.key);
      }
    }
    return out;
  }

  Future<void> _writeApiCache(
    Directory dir,
    Map<String, dynamic> entries,
  ) async {
    final json = jsonEncode(entries);
    await File(
      p.join(dir.path, OfflineFormStore.apiCacheJsonFile),
    ).writeAsString(json);
    await File(
      p.join(dir.path, OfflineFormStore.apiCacheScriptFile),
    ).writeAsString('window.__IFRC_OFFLINE_API__=$json;');
  }

  Future<Map<String, dynamic>> _readApiCache(Directory dir) async =>
      await _store.readJson(
        File(p.join(dir.path, OfflineFormStore.apiCacheJsonFile)),
      ) ??
      <String, dynamic>{};

  /// Adds API responses seen while a saved form was open online (lookup lists,
  /// plugin data, resolved variables ...) to its template's package, so every
  /// assignment of the template can use them offline. Returns false when the
  /// assignment has no saved page.
  Future<bool> mergeApiCache(
    int assignmentId,
    List<Map<String, dynamic>> entries,
  ) async {
    if (entries.isEmpty) return false;
    final pagePath = await _store.pagePath(assignmentId);
    if (pagePath == null) return false;
    final dir = Directory(p.dirname(pagePath));
    final key = p.basename(dir.path);
    return _locks.run(key, () async {
      if (!await dir.exists()) return false;
      final merged = _mergeApiEntries(await _readApiCache(dir), entries);
      await _writeApiCache(dir, merged);
      final meta = await _store.readPackageMeta(key);
      if (meta != null) {
        await _store.writePackageMeta(
          dir,
          meta.copyWith(apiEntryCount: merged.length),
        );
      }
      return true;
    });
  }

  // ---------------------------------------------------------------- saving

  /// Saves the template's shared files (replacing any previous package of it)
  /// and the assignment's page. Existing pages of other assignments are kept
  /// and refreshed later. A failed attempt never damages the previous copy.
  Future<void> savePackageAndPage(OfflineFormRequest request) =>
      _locks.run(request.packageKey, () => _savePackageAndPage(request));

  /// Saves only the assignment's page, using the template's saved package.
  /// Throws when the package is missing or no longer matches the server.
  Future<void> savePage(OfflineFormRequest request) =>
      _locks.run(request.packageKey, () => _savePage(request));

  Future<_FetchedPage> _fetchPage(OfflineFormRequest r) async {
    final id = r.assignmentId;
    final resolved = UrlHelper.resolveWebViewInitialUrl(r.formPath, r.language);
    final pageUri = Uri.parse(resolved);
    final headers = <String, String>{
      ..._dio.options.headers.map((k, v) => MapEntry(k, v.toString())),
      if (r.sessionCookieHeader != null && r.sessionCookieHeader!.isNotEmpty)
        'Cookie': r.sessionCookieHeader!,
    };

    final resp = await _dio.get<List<int>>(
      resolved,
      options: Options(responseType: ResponseType.bytes, headers: headers),
      cancelToken: r.cancelToken,
    );
    final status = resp.statusCode ?? 0;
    final bytes = resp.data;
    _trace(
      id,
      'page ${_tracePath(pageUri)} HTTP $status bytes=${bytes?.length ?? 0}',
    );
    if (status >= 400) {
      throw AssignmentOfflineBundleException(
        'Failed to load form page (HTTP $status).',
      );
    }
    if (bytes == null || bytes.isEmpty) {
      throw AssignmentOfflineBundleException('Empty response from server.');
    }
    if (bytes.length > _maxHtmlBytes) {
      throw AssignmentOfflineBundleException(
        'Form page is too large to save offline.',
      );
    }

    final html = utf8.decode(bytes, allowMalformed: true);
    final analysis = await _inBackground(_analyzePage, (
      html,
      resolved,
    ), weight: html.length);
    final refs = {for (final s in analysis.all) Uri.parse(s)};
    final other = refs
        .where(
          (u) =>
              u.hasScheme && (u.host != pageUri.host || u.port != pageUri.port),
        )
        .length;
    _trace(
      id,
      'refs total=${refs.length} dom=${analysis.dom.length} other-host=$other',
    );
    return _FetchedPage(
      html: html,
      resolved: resolved,
      pageUri: pageUri,
      headers: headers,
      refs: refs,
      domRefs: analysis.dom.toSet(),
    );
  }

  /// Downloads the files [page] references into [dir] (skipping what [assets]
  /// already maps) and everything those files import in turn.
  ///
  /// Only files the page itself loads (script and style tags and what they
  /// import) must arrive. Paths merely spotted in inline script text or plugin
  /// code are best-effort; a miss is traced but never fails the save.
  Future<_CrawlOutcome> _crawl({
    required OfflineFormRequest request,
    required _FetchedPage page,
    required Directory dir,
    required Map<String, String> assets,
  }) async {
    final id = request.assignmentId;
    final pageUri = page.pageUri;
    final outcome = _CrawlOutcome();
    final pending = ListQueue<Uri>();
    final enqueued = <String>{...assets.keys};
    final speculative = <String>{};

    void markMissing(Uri u, String reason) {
      outcome.missing.add(u);
      final lower = u.path.toLowerCase();
      final key = u.toString();
      final critical =
          OfflineAssetScanner.isSameOrigin(u, pageUri) &&
          !u.path.startsWith('/plugins/static/') &&
          !speculative.contains(key) &&
          (lower.endsWith('.js') ||
              lower.endsWith('.mjs') ||
              lower.endsWith('.css'));
      if (critical) outcome.critical.add(u);
      _trace(
        id,
        'missing ${_tracePath(u)} $reason'
        '${critical
            ? ' CRITICAL'
            : speculative.contains(key)
            ? ' (guessed)'
            : ''}',
      );
    }

    void enqueue(Uri u, {bool isSpeculative = false}) {
      if (!OfflineAssetScanner.shouldMirror(u, pageUri)) return;
      final key = u.toString();
      if (enqueued.contains(key)) {
        if (!isSpeculative) speculative.remove(key);
        return;
      }
      enqueued.add(key);
      if (isSpeculative) speculative.add(key);
      pending.addLast(u);
    }

    for (final u in page.refs) {
      enqueue(u, isSpeculative: !page.domRefs.contains(u.toString()));
    }

    Future<void> fetchOne(Uri absolute) async {
      final absKey = absolute.toString();
      final external = !OfflineAssetScanner.isSameOrigin(absolute, pageUri);
      final relPath = external
          ? OfflineAssetScanner.externalRelativePath(absolute)
          : OfflineAssetScanner.relativePathForUrl(
              absolute,
              pageUri,
              foldCacheQueryIntoFileName: false,
            );
      try {
        final r = await _dio.get<List<int>>(
          absKey,
          options: Options(
            responseType: ResponseType.bytes,
            headers: external
                ? _headersWithoutCredentials(page.headers)
                : page.headers,
          ),
          cancelToken: request.cancelToken,
        );
        final sc = r.statusCode ?? 0;
        final body = r.data;
        if (sc >= 400 || body == null) {
          if (!OfflineAssetScanner.mirrorSkipIsBenign404(absolute, sc)) {
            markMissing(absolute, 'HTTP $sc');
          }
          return;
        }
        if (body.length > _maxAssetBytes) {
          markMissing(absolute, 'too large (${body.length}B)');
          return;
        }
        final file = File(p.join(dir.path, relPath));
        await file.parent.create(recursive: true);
        await file.writeAsBytes(body);
        final relPosix = relPath.replaceAll(r'\', '/');
        assets[absKey] = relPosix;
        outcome.savedPaths.add(relPosix);

        final lower = absolute.path.toLowerCase();
        final isCss = relPath.toLowerCase().endsWith('.css');
        final isJs =
            !external && (lower.endsWith('.js') || lower.endsWith('.mjs'));
        if (!isCss && !isJs) return;
        final parentSpeculative = speculative.contains(absKey);
        final found = await _inBackground(_scanChildren, (
          kind: isCss ? 'css' : 'js',
          text: utf8.decode(body, allowMalformed: true),
          location: absKey,
          plugin: isJs && absolute.path.startsWith('/plugins/static/'),
        ), weight: body.length);
        for (final child in found.refs) {
          enqueue(Uri.parse(child), isSpeculative: parentSpeculative);
        }
        for (final child in found.literals) {
          enqueue(Uri.parse(child), isSpeculative: true);
        }
      } catch (e) {
        if (e is DioException && CancelToken.isCancel(e)) rethrow;
        markMissing(absolute, _describeError(e));
      }
    }

    var inFlight = 0;
    Future<void> worker() async {
      while (true) {
        if (outcome.savedPaths.length >= _maxAssets) return;
        if (pending.isEmpty) {
          if (inFlight == 0) return;
          await Future<void>.delayed(const Duration(milliseconds: 8));
          continue;
        }
        final next = pending.removeFirst();
        inFlight++;
        try {
          await fetchOne(next);
        } finally {
          inFlight--;
        }
      }
    }

    await Future.wait([for (var i = 0; i < _crawlWorkers; i++) worker()]);

    if (pending.isNotEmpty) {
      _trace(id, 'stopped at $_maxAssets assets');
    }
    if (outcome.critical.isNotEmpty) {
      throw AssignmentOfflineBundleException(
        'Offline copy is incomplete: ${outcome.critical.length} script/style '
        'file(s) could not be saved (first: ${outcome.critical.first.path}).',
        details: {
          'critical_missing': [
            for (final u in outcome.critical.take(40)) _tracePath(u),
          ],
        },
      );
    }
    return outcome;
  }

  Future<void> _rewriteSaved(
    Directory dir,
    Iterable<String> relPaths,
    Map<String, String> assets,
    int id,
  ) async {
    final list = relPaths.toList();
    if (list.isEmpty) return;
    try {
      await Isolate.run(
        () => rewriteSavedFilesSync(
          OfflineRewriteJob(
            dirPath: dir.path,
            relPaths: list,
            mirroredExternal: {
              for (final e in assets.entries)
                if (e.value.startsWith(
                  '${OfflineAssetScanner.externalDirName}/',
                ))
                  e.key: e.value,
            },
          ),
        ),
      );
    } catch (e, st) {
      _trace(id, 'rewrite failed ${_describeError(e)}');
      DebugLogger.logWarn(
        'OFFLINE_BUNDLE',
        'Path rewriting failed for assignment $id: $e\n$st',
      );
    }
  }

  /// Turns the downloaded markup into the offline page of [request].
  Future<void> _writePage({
    required Directory dir,
    required OfflineFormRequest request,
    required _FetchedPage page,
    required Map<String, String> assets,
    required String? packageStaticVersion,
  }) async {
    final pageAssets = <String, String>{};
    for (final ref in page.refs) {
      final key = ref.toString();
      final rel = assets[key];
      if (rel == null) continue;
      pageAssets[key] = rel;
      if (OfflineAssetScanner.isSameOrigin(ref, page.pageUri)) {
        OfflineAssetScanner.registerMirrorRewriteKeys(ref, rel, pageAssets);
      }
    }
    final html = await _inBackground(_renderPage, (
      html: page.html,
      assets: pageAssets,
      message: request.submitBlockedMessage,
    ), weight: page.html.length);
    final id = request.assignmentId;
    final htmlFile = File(p.join(dir.path, OfflineFormStore.pageHtmlName(id)));
    final tmp = File('${htmlFile.path}.tmp');
    await tmp.writeAsString(html);
    await tmp.rename(htmlFile.path);
    await _store.writeJson(
      File(p.join(dir.path, OfflineFormStore.pageMetaName(id))),
      OfflinePageMeta(
        assignmentId: id,
        packageKey: request.packageKey,
        templateId: request.templateId,
        title: request.title,
        sourceUrl: page.resolved,
        savedAtUtc: DateTime.now().toUtc(),
        formDefinitionUpdatedAtIso: request.formDefinitionUpdatedAtIso,
        dataVersion: request.dataVersion,
        staticVersion: packageStaticVersion,
        language: request.language,
      ).toJson(),
    );
  }

  Future<void> _savePackageAndPage(OfflineFormRequest request) async {
    final id = request.assignmentId;
    final key = request.packageKey;
    final epoch = _epoch;
    _traces[id] = <String>[];
    _trace(
      id,
      'package+page template=${request.templateId} '
      'static=${request.staticVersion} lang=${request.language}',
    );

    final page = await _fetchPage(request);
    final finalDir = await _store.packageDir(key);
    final dir = await _store.stagingDir(key);
    if (await dir.exists()) await dir.delete(recursive: true);
    await dir.create(recursive: true);

    try {
      final assets = <String, String>{};
      final outcome = await _crawl(
        request: request,
        page: page,
        dir: dir,
        assets: assets,
      );
      await _rewriteSaved(dir, outcome.savedPaths, assets, id);

      var apiEntries = <String, dynamic>{};
      final previousCache = await _readApiCache(finalDir);
      final recorder = request.recordApiResponses;
      List<Map<String, dynamic>> recorded = const [];
      if (recorder != null) {
        try {
          recorded = await recorder(page.resolved).timeout(_recordingTimeout);
          _trace(id, 'recorder entries=${recorded.length}');
        } catch (e, st) {
          if (e is DioException && CancelToken.isCancel(e)) rethrow;
          _trace(id, 'recorder failed ${_describeError(e)}');
          DebugLogger.logWarn(
            'OFFLINE_BUNDLE',
            'Could not record form API data for assignment $id: $e\n$st',
          );
        }
      }
      apiEntries = _mergeApiEntries(previousCache, recorded);
      await _writeApiCache(dir, apiEntries);
      await _store.writeAssets(dir, assets);

      await _writePage(
        dir: dir,
        request: request,
        page: page,
        assets: assets,
        packageStaticVersion: request.staticVersion,
      );
      await _carryOverPages(from: finalDir, to: dir, except: id);

      final unmirrored = page.refs
          .where(
            (u) =>
                u.hasScheme &&
                (u.scheme == 'http' || u.scheme == 'https') &&
                !OfflineAssetScanner.isSameOrigin(u, page.pageUri) &&
                !assets.containsKey(u.toString()),
          )
          .length;
      await _store.writePackageMeta(
        dir,
        OfflinePackageMeta(
          key: key,
          templateId: request.templateId,
          title: request.title,
          staticVersion: request.staticVersion,
          formDefinitionUpdatedAtIso: request.formDefinitionUpdatedAtIso,
          savedAtUtc: DateTime.now().toUtc(),
          assetCount: assets.length,
          missingAssetCount: outcome.missing.length,
          externalRefCount: unmirrored,
          apiEntryCount: apiEntries.length,
        ),
      );

      if (epoch != _epoch) {
        throw AssignmentOfflineBundleException('Offline storage was cleared.');
      }
      if (await finalDir.exists()) await finalDir.delete(recursive: true);
      await dir.rename(finalDir.path);
      _trace(
        id,
        'saved files=${assets.length} missing=${outcome.missing.length}',
      );
    } catch (e) {
      _trace(id, 'build failed ${_describeError(e)}');
      if (await dir.exists()) await dir.delete(recursive: true);
      if (epoch != _epoch && e is! AssignmentOfflineBundleException) {
        throw AssignmentOfflineBundleException('Offline storage was cleared.');
      }
      rethrow;
    }
  }

  /// Keeps the pages of other assignments when a package is rebuilt. They are
  /// marked outdated (their static release no longer matches) and refreshed
  /// afterwards, but stay openable offline in the meantime.
  Future<void> _carryOverPages({
    required Directory from,
    required Directory to,
    required int except,
  }) async {
    if (!await from.exists()) return;
    await for (final f in from.list(followLinks: false)) {
      if (f is! File) continue;
      final name = p.basename(f.path);
      final m = RegExp(r'^page_(\d+)\.(html|json)$').firstMatch(name);
      if (m == null || int.parse(m.group(1)!) == except) continue;
      try {
        await f.copy(p.join(to.path, name));
      } catch (_) {}
    }
  }

  Future<void> _savePage(OfflineFormRequest request) async {
    final epoch = _epoch;
    try {
      await _savePageUnchecked(request, epoch);
    } catch (e) {
      if (epoch != _epoch && e is! AssignmentOfflineBundleException) {
        throw AssignmentOfflineBundleException('Offline storage was cleared.');
      }
      rethrow;
    }
  }

  Future<void> _savePageUnchecked(OfflineFormRequest request, int epoch) async {
    final id = request.assignmentId;
    final key = request.packageKey;
    _traces[id] = <String>[];
    _trace(
      id,
      'page only template=${request.templateId} lang=${request.language}',
    );

    final meta = await _store.readPackageMeta(key);
    final dir = await _store.packageDir(key);
    if (meta == null || !await dir.exists()) {
      throw AssignmentOfflineBundleException(
        'The form template is not saved on this device.',
      );
    }
    final staticOk =
        request.staticVersion != null && request.staticVersion!.isNotEmpty
        ? meta.staticVersion == request.staticVersion
        : true;
    if (!staticOk) {
      throw AssignmentOfflineBundleException(
        'The saved form files are out of date.',
      );
    }

    final page = await _fetchPage(request);
    final assets = await _store.readAssets(dir);
    final outcome = await _crawl(
      request: request,
      page: page,
      dir: dir,
      assets: assets,
    );
    if (outcome.savedPaths.isNotEmpty) {
      await _rewriteSaved(dir, outcome.savedPaths, assets, id);
      await _store.writeAssets(dir, assets);
      await _store.writePackageMeta(
        dir,
        meta.copyWith(
          assetCount: assets.length,
          missingAssetCount: meta.missingAssetCount + outcome.missing.length,
        ),
      );
    }
    if (epoch != _epoch || !await dir.exists()) {
      throw AssignmentOfflineBundleException('Offline storage was cleared.');
    }
    await _writePage(
      dir: dir,
      request: request,
      page: page,
      assets: assets,
      packageStaticVersion: meta.staticVersion,
    );
    _trace(id, 'saved page new-files=${outcome.savedPaths.length}');
  }

  static Map<String, String> _headersWithoutCredentials(
    Map<String, String> headers,
  ) => {
    for (final e in headers.entries)
      if (e.key.toLowerCase() != 'cookie' &&
          e.key.toLowerCase() != 'authorization')
        e.key: e.value,
  };
}
