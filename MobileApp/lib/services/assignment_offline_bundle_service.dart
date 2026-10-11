import 'dart:collection';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show ValueNotifier, visibleForTesting;
import 'package:html/parser.dart' as html_parser;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/shared/assignment.dart';
import '../utils/debug_logger.dart' show DebugLogger, LogLevel;
import '../utils/url_helper.dart';
import 'offline_form_scripts.dart';
import 'user_scope_service.dart';

/// Metadata written alongside [AssignmentOfflineBundleService] disk snapshots.
class AssignmentOfflineBundleMeta {
  const AssignmentOfflineBundleMeta({
    required this.assignmentId,
    this.sourceUrl,
    this.savedAtUtc,
    required this.assetCount,
    this.formDefinitionUpdatedAtIso,
    this.templateId,
    this.staticVersion,
    this.dataVersion,
    this.language,
    this.apiEntryCount = 0,
    this.missingAssetCount = 0,
    this.externalRefCount = 0,
    this.title,
  });

  final int assignmentId;
  /// Human-readable form name captured at download time (for storage screens).
  final String? title;
  /// Form template the saved page belongs to (null for bundles saved by older builds).
  final int? templateId;
  /// Server static-files release the copy was captured from.
  final String? staticVersion;
  /// [Assignment.dataVersion] at capture time.
  final String? dataVersion;
  /// Language of the saved page markup.
  final String? language;
  /// Number of recorded API responses (lookup lists, plugin data, …) saved with the form.
  final int apiEntryCount;
  /// Same-origin assets referenced by the page that could not be saved.
  final int missingAssetCount;
  /// Third-party URLs referenced by the page (not saved; need a connection).
  final int externalRefCount;
  final String? sourceUrl;
  final DateTime? savedAtUtc;
  final int assetCount;
  /// ISO-8601 UTC snapshot of [Assignment.formDefinitionUpdatedAt] when the bundle was saved.
  final String? formDefinitionUpdatedAtIso;
}

/// One saved offline copy, as listed on the storage screen.
class OfflineCopySummary {
  const OfflineCopySummary({
    required this.assignmentId,
    this.templateId,
    this.title,
    this.savedAt,
    required this.sizeBytes,
  });

  final int assignmentId;
  final int? templateId;
  final String? title;
  final DateTime? savedAt;
  final int sizeBytes;
}

/// True when the on-disk copy no longer matches what the server (or the app)
/// would produce today: a newer form definition, a new static-files release,
/// changed assignment data, or a different display language.
bool isAssignmentOfflineBundleStale(
  Assignment assignment,
  AssignmentOfflineBundleMeta? meta, {
  String? language,
}) {
  bool differs(DateTime? server, String? cachedIso) {
    if (server == null) return false;
    if (cachedIso == null || cachedIso.isEmpty) return true;
    final cached = DateTime.tryParse(cachedIso);
    if (cached == null) return true;
    final delta = server.toUtc().millisecondsSinceEpoch -
        cached.toUtc().millisecondsSinceEpoch;
    return delta.abs() > 1500;
  }

  if (differs(assignment.formDefinitionUpdatedAt,
      meta?.formDefinitionUpdatedAtIso)) {
    return true;
  }

  final server = assignment.staticVersion;
  if (server != null && server.isNotEmpty && meta?.staticVersion != server) {
    return true;
  }

  final serverData = assignment.dataVersion;
  if (serverData != null && serverData.isNotEmpty) {
    final cachedData = meta?.dataVersion;
    if (cachedData == null || cachedData.isEmpty) return true;
    final a = DateTime.tryParse(serverData);
    final b = DateTime.tryParse(cachedData);
    if (a != null && b != null) {
      if ((a.toUtc().millisecondsSinceEpoch - b.toUtc().millisecondsSinceEpoch)
              .abs() >
          1500) {
        return true;
      }
    } else if (serverData != cachedData) {
      return true;
    }
  }

  final metaLanguage = meta?.language;
  if (language != null &&
      language.isNotEmpty &&
      metaLanguage != null &&
      metaLanguage.isNotEmpty &&
      metaLanguage != language) {
    return true;
  }
  return false;
}

/// Persists a crawlable snapshot of an assignment entry form (HTML + same-origin
/// static assets) so the form can open from disk when the device is offline.
class AssignmentOfflineBundleService {
  /// Bumped whenever saved copies are removed so open screens can refresh.
  static final ValueNotifier<int> savedCopiesChanged = ValueNotifier<int>(0);

  /// Bumped when the "keep open forms available offline" preference changes.
  static final ValueNotifier<int> autoDownloadChanged = ValueNotifier<int>(0);

  static const String _autoDownloadPrefKey = 'offline_auto_download_open_forms';

  /// When on, every open assignment on the dashboard gets an offline copy while
  /// on Wi-Fi, instead of only templates that were downloaded by hand.
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

  AssignmentOfflineBundleService._internal()
      : _dio = _buildDio(),
        _baseDirOverride = null,
        _scopeOverride = null;

  /// Test hook: inject the HTTP client, storage directory and user scope.
  @visibleForTesting
  AssignmentOfflineBundleService.forTesting({
    required Dio dio,
    required Directory baseDir,
    String scope = 'user_test',
  })  : _dio = dio,
        _baseDirOverride = baseDir,
        _scopeOverride = scope;

  factory AssignmentOfflineBundleService() => _instance;
  static final AssignmentOfflineBundleService _instance =
      AssignmentOfflineBundleService._internal();

  static Dio _buildDio() => Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 120),
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
  final Directory? _baseDirOverride;
  final String? _scopeOverride;
  String? _housekeptScope;

  static const String _apiCacheJsonFile = 'offline_api_cache.json';
  static const String _apiCacheScriptFile = 'offline_api_cache.js';
  static const int _maxApiEntryBytes = 4 * 1024 * 1024;
  static const int _maxApiCacheBytes = 20 * 1024 * 1024;

  static const String _metaFileName = 'bundle_meta.json';
  /// Serialized [savedRelByAbsolute] for post-download / migration HTML rewrites.
  static const String _urlRewriteMapFileName = 'url_rewrite_map.json';
  static const String _offlineRepairStampFile = 'offline_bundle_repair.txt';
  /// Bumped when on-disk layout changes (e.g. flat static paths for ES modules).
  static const String _offlineRepairStampValue = '6';
  /// Legacy flag from earlier builds; removed when v2 repair runs.
  static const String _legacyStaticRootRepairFlag = '.static_root_demoted_v1';
  static const int _maxAssets = 1500;
  static const int _maxHtmlBytes = 25 * 1024 * 1024;
  static const int _maxAssetBytes = 12 * 1024 * 1024;

  /// POSIX paths only (URLs in HTML/CSS use forward slashes).
  static final p.Context _posix = p.Context(style: p.Style.posix);

  Future<Directory> _bundlesBase() async {
    final override = _baseDirOverride;
    if (override != null) {
      if (!await override.exists()) await override.create(recursive: true);
      return override;
    }
    final base = await getApplicationDocumentsDirectory();
    final dir = Directory(p.join(base.path, 'offline_assignment_bundles'));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  static String _safeScope(String scope) =>
      scope.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');

  /// Saved forms contain a user's data, so they live under a per-user folder.
  /// Folders from earlier builds (shared, unscoped) and other users' folders
  /// are removed the first time a stable user scope is seen.
  Future<Directory> _rootDir() async {
    final base = await _bundlesBase();
    final scope = _safeScope(
      _scopeOverride ?? await UserScopeService().getScope(includeAuth: true),
    );
    final dir = Directory(p.join(base.path, scope));
    if (!await dir.exists()) {
      await dir.create(recursive: true);
    }
    if (_housekeptScope != scope) {
      _housekeptScope = scope;
      try {
        await for (final e in base.list(followLinks: false)) {
          final name = p.basename(e.path);
          if (e is Directory && name == scope) continue;
          if (e is Directory && name.startsWith('assignment_')) {
            await e.delete(recursive: true);
          } else if (e is Directory && scope.startsWith('user_')) {
            await e.delete(recursive: true);
          }
        }
      } catch (e) {
        DebugLogger.logWarn('OFFLINE_BUNDLE', 'Housekeeping failed: $e');
      }
    }
    return dir;
  }

  /// Deletes every saved form for every user (used on logout).
  Future<void> clearAll() async {
    savedCopiesChanged.value++;
    try {
      final base = await _bundlesBase();
      await for (final e in base.list(followLinks: false)) {
        await e.delete(recursive: true);
      }
      _housekeptScope = null;
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_BUNDLE', 'clearAll failed: $e');
    }
  }

  /// Deletes copies that are very old, beyond [maxBundles] (oldest first), or for
  /// assignments in [closedAssignmentIds] (they can no longer be edited).
  Future<int> pruneBundles({
    Duration maxAge = const Duration(days: 45),
    int maxBundles = 60,
    Set<int> closedAssignmentIds = const {},
    DateTime? now,
  }) async {
    final clock = (now ?? DateTime.now()).toUtc();
    final entries = <({Directory dir, int id, DateTime savedAt})>[];
    var removed = 0;
    for (final dir in await _bundleDirs()) {
      final id = int.tryParse(p.basename(dir.path).substring('assignment_'.length));
      if (id == null) continue;
      final meta = await _readMetaJson(dir);
      final savedAt =
          DateTime.tryParse(meta?['saved_at']?.toString() ?? '')?.toUtc() ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
      if (closedAssignmentIds.contains(id) ||
          clock.difference(savedAt) > maxAge) {
        await dir.delete(recursive: true);
        removed++;
        continue;
      }
      entries.add((dir: dir, id: id, savedAt: savedAt));
    }
    if (entries.length > maxBundles) {
      entries.sort((a, b) => a.savedAt.compareTo(b.savedAt));
      for (final e in entries.take(entries.length - maxBundles)) {
        await e.dir.delete(recursive: true);
        removed++;
      }
    }
    if (removed > 0) savedCopiesChanged.value++;
    return removed;
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
        templateId: (raw['template_id'] as num?)?.toInt(),
        staticVersion: raw['static_version']?.toString(),
        dataVersion: raw['data_version']?.toString(),
        language: raw['language']?.toString(),
        apiEntryCount: (raw['api_entry_count'] as num?)?.toInt() ?? 0,
        missingAssetCount: (raw['missing_asset_count'] as num?)?.toInt() ?? 0,
        externalRefCount: (raw['external_ref_count'] as num?)?.toInt() ?? 0,
        title: raw['title']?.toString(),
      );
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> _readMetaJson(Directory dir) async {
    final f = File(p.join(dir.path, _metaFileName));
    try {
      if (!await f.exists()) return null;
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  Future<List<Directory>> _bundleDirs() async {
    final root = await _rootDir();
    final out = <Directory>[];
    await for (final e in root.list(followLinks: false)) {
      if (e is Directory && p.basename(e.path).startsWith('assignment_')) {
        out.add(e);
      }
    }
    return out;
  }

  /// Every saved copy for the current user with its disk footprint, newest first.
  Future<List<OfflineCopySummary>> listSavedCopies() async {
    final out = <OfflineCopySummary>[];
    for (final dir in await _bundleDirs()) {
      if (!File(p.join(dir.path, 'index.html')).existsSync()) continue;
      final id = int.tryParse(p.basename(dir.path).replaceFirst('assignment_', ''));
      if (id == null) continue;
      final meta = await _readMetaJson(dir);
      var size = 0;
      try {
        await for (final e in dir.list(recursive: true, followLinks: false)) {
          if (e is File) size += await e.length();
        }
      } catch (_) {}
      out.add(
        OfflineCopySummary(
          assignmentId: id,
          templateId: (meta?['template_id'] as num?)?.toInt(),
          title: meta?['title']?.toString(),
          savedAt: DateTime.tryParse(meta?['saved_at']?.toString() ?? '')
              ?.toLocal(),
          sizeBytes: size,
        ),
      );
    }
    out.sort((a, b) => (b.savedAt ?? DateTime.fromMillisecondsSinceEpoch(0))
        .compareTo(a.savedAt ?? DateTime.fromMillisecondsSinceEpoch(0)));
    return out;
  }

  /// Template ids that have at least one saved offline form on this device.
  ///
  /// The package (form markup + `/static/` assets) is template-wide, so any
  /// assignment — for any entity — that uses one of these templates can be
  /// prepared from it without re-downloading the shared files.
  Future<Set<int>> templateIdsWithBundles() async {
    final ids = <int>{};
    for (final dir in await _bundleDirs()) {
      if (!File(p.join(dir.path, 'index.html')).existsSync()) continue;
      final id = ((await _readMetaJson(dir))?['template_id'] as num?)?.toInt();
      if (id != null) ids.add(id);
    }
    return ids;
  }

  /// Records [templateId] on a bundle saved before template ids were tracked.
  Future<void> backfillTemplateId(int assignmentId, int templateId) async {
    final dir = await bundleDirFor(assignmentId);
    final meta = await _readMetaJson(dir);
    if (meta == null || meta['template_id'] != null) return;
    meta['template_id'] = templateId;
    await File(p.join(dir.path, _metaFileName))
        .writeAsString(jsonEncode(meta), flush: true);
  }

  /// Removes every saved form that belongs to [templateId], plus
  /// [alsoAssignmentId]'s own copy.
  Future<void> deleteBundlesForTemplate(
    int templateId, {
    int? alsoAssignmentId,
  }) async {
    for (final dir in await _bundleDirs()) {
      final id = ((await _readMetaJson(dir))?['template_id'] as num?)?.toInt();
      if (id == templateId) {
        await dir.delete(recursive: true);
      }
    }
    if (alsoAssignmentId != null) {
      await deleteBundle(alsoAssignmentId);
    }
    savedCopiesChanged.value++;
  }

  bool _staticFilesCompatible(
    Map<String, dynamic> meta, {
    required String? staticVersion,
    required String? formDefinitionUpdatedAtIso,
  }) {
    if (staticVersion != null && staticVersion.isNotEmpty) {
      return meta['static_version']?.toString() == staticVersion;
    }
    // Older servers do not report a static release; fall back to requiring the
    // same published form definition.
    final wanted = DateTime.tryParse(formDefinitionUpdatedAtIso ?? '');
    final cached =
        DateTime.tryParse(meta['form_definition_updated_at']?.toString() ?? '');
    if (wanted == null || cached == null) return false;
    return (cached.toUtc().millisecondsSinceEpoch -
                wanted.toUtc().millisecondsSinceEpoch)
            .abs() <=
        1500;
  }

  /// A saved copy whose `/static/` files can be copied locally instead of
  /// downloaded again: the assignment's own previous copy first, otherwise the
  /// newest copy of the same template. Both must come from the same static release.
  Future<Directory?> _findReusableBundleDir({
    required int assignmentId,
    required int? templateId,
    required String? staticVersion,
    required String? formDefinitionUpdatedAtIso,
  }) async {
    Directory? best;
    DateTime? bestSavedAt;
    for (final dir in await _bundleDirs()) {
      if (!File(p.join(dir.path, 'index.html')).existsSync()) continue;
      final meta = await _readMetaJson(dir);
      if (meta == null) continue;
      final isOwn = p.basename(dir.path) == 'assignment_$assignmentId';
      final sameTemplate = templateId != null &&
          (meta['template_id'] as num?)?.toInt() == templateId;
      if (!isOwn && !sameTemplate) continue;
      if (!_staticFilesCompatible(
        meta,
        staticVersion: staticVersion,
        formDefinitionUpdatedAtIso: formDefinitionUpdatedAtIso,
      )) {
        continue;
      }
      if (isOwn) return dir;
      final savedAt =
          DateTime.tryParse(meta['saved_at']?.toString() ?? '') ??
          DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
      if (bestSavedAt == null || savedAt.isAfter(bestSavedAt)) {
        best = dir;
        bestSavedAt = savedAt;
      }
    }
    return best;
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
    int? templateId,
    String? staticVersion,
    String? dataVersion,
    String? title,
    String submitBlockedMessage =
        'You are offline. Your changes are saved as a draft on this device. '
        'Submit when you are back online; the form is validated before it is submitted.',
    Future<List<Map<String, dynamic>>> Function(String formUrl)?
        recordApiResponses,
  }) async {
    final reuseDir = await _findReusableBundleDir(
      assignmentId: assignmentId,
      templateId: templateId,
      staticVersion: staticVersion,
      formDefinitionUpdatedAtIso: formDefinitionUpdatedAtIso,
    );
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

    final html = utf8.decode(bytes, allowMalformed: true);
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

    // Build next to the live copy and swap at the end so a failed refresh never
    // destroys a working offline copy.
    final finalDir = await bundleDirFor(assignmentId);
    final dir = Directory(p.join(finalDir.parent.path, 'tmp_assignment_$assignmentId'));
    if (await dir.exists()) {
      await dir.delete(recursive: true);
    }
    await dir.create(recursive: true);

    try {
      await _buildBundleInto(
        dir: dir,
        finalDir: finalDir,
        assignmentId: assignmentId,
        resolved: resolved,
        pageUri: pageUri,
        html: html,
        refs: refs,
        otherHostRefs: otherHostRefs,
        headers: headers,
        reuseDir: reuseDir,
        templateId: templateId,
        staticVersion: staticVersion,
        dataVersion: dataVersion,
        title: title,
        language: language,
        formDefinitionUpdatedAtIso: formDefinitionUpdatedAtIso,
        submitBlockedMessage: submitBlockedMessage,
        recordApiResponses: recordApiResponses,
      );
    } catch (_) {
      if (await dir.exists()) {
        await dir.delete(recursive: true);
      }
      rethrow;
    }
  }

  Future<void> _buildBundleInto({
    required Directory dir,
    required Directory finalDir,
    required int assignmentId,
    required String resolved,
    required Uri pageUri,
    required String html,
    required Set<Uri> refs,
    required int otherHostRefs,
    required Map<String, String> headers,
    required Directory? reuseDir,
    required int? templateId,
    required String? staticVersion,
    required String? dataVersion,
    required String? title,
    required String language,
    required String? formDefinitionUpdatedAtIso,
    required String submitBlockedMessage,
    required Future<List<Map<String, dynamic>>> Function(String formUrl)?
        recordApiResponses,
  }) async {
    final savedRelByAbsolute = <String, String>{};
    var count = 0;

    final pending = ListQueue<Uri>();
    final enqueued = <String>{};
    final missingAssets = <Uri>[];
    final criticalMissing = <Uri>[];

    void markMissing(Uri u) {
      missingAssets.add(u);
      final lower = u.path.toLowerCase();
      if (_isSameOrigin(u, pageUri) &&
          (lower.endsWith('.js') ||
              lower.endsWith('.mjs') ||
              lower.endsWith('.css'))) {
        criticalMissing.add(u);
      }
    }

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
      final external = !_isSameOrigin(absolute, pageUri);
      final relPath = external
          ? _externalRelativePath(absolute)
          : _relativePathForUrl(
              absolute,
              pageUri,
              foldCacheQueryIntoFileName: false,
            );
      final localFile = File(p.join(dir.path, relPath));
      await localFile.parent.create(recursive: true);

      try {
        final reusable =
            reuseDir == null ? null : File(p.join(reuseDir.path, relPath));
        final List<int> body;
        if (reusable != null && await reusable.exists()) {
          body = await reusable.readAsBytes();
        } else {
          final r = await _dio.get<List<int>>(
            absKey,
            options: Options(
              responseType: ResponseType.bytes,
              headers: external ? _headersWithoutCredentials(headers) : headers,
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
              markMissing(absolute);
            }
            continue;
          }
          if (r.data!.length > _maxAssetBytes) {
            DebugLogger.logWarn('OFFLINE_BUNDLE', 'Skip large asset: $absolute');
            markMissing(absolute);
            continue;
          }
          body = r.data!;
        }
        await localFile.writeAsBytes(body, flush: true);
        final relPosix = relPath.replaceAll(r'\', '/');
        savedRelByAbsolute[absKey] = relPosix;
        if (!external) {
          _registerMirrorRewriteKeys(absolute, relPosix, savedRelByAbsolute);
        }
        count++;

        if (relPath.toLowerCase().endsWith('.css')) {
          final cssText = utf8.decode(body, allowMalformed: true);
          for (final child in _urlsFromCss(cssText, absolute)) {
            enqueue(child);
          }
        }

        final pathLower = absolute.path.toLowerCase();
        if (!external && (pathLower.endsWith('.js') || pathLower.endsWith('.mjs'))) {
          final jsText = utf8.decode(body, allowMalformed: true);
          for (final child in _urlsFromJavaScript(jsText, absolute)) {
            enqueue(child);
          }
          if (absolute.path.startsWith('/plugins/static/')) {
            for (final child in _staticLiteralsFromJavaScript(jsText, absolute)) {
              enqueue(child);
            }
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
        markMissing(absolute);
      }
    }

    if (criticalMissing.isNotEmpty) {
      throw AssignmentOfflineBundleException(
        'Offline copy is incomplete: ${criticalMissing.length} script/style '
        'file(s) could not be saved (first: ${criticalMissing.first.path}).',
      );
    }

    if (count >= _maxAssets) {
      DebugLogger.logWarn(
        'OFFLINE_BUNDLE',
        'Stopped after $_maxAssets assets (assignment $assignmentId).',
      );
    }

    await _rewriteAllCssRootStaticInBundle(dir);
    await _rewriteRootStaticInBundleScripts(dir);
    await _rewriteExternalUrlsInCss(dir, savedRelByAbsolute);
    final unmirroredExternalRefs = refs
        .where(
          (u) =>
              u.hasScheme &&
              (u.scheme == 'http' || u.scheme == 'https') &&
              !_isSameOrigin(u, pageUri) &&
              !savedRelByAbsolute.containsKey(u.toString()),
        )
        .length;

    html = _rewriteHtmlAssetRefs(html, savedRelByAbsolute);
    html = _demoteHtmlRootStaticPaths(html);
    html = _stripStaticUrlCacheQuery(html);
    html = _injectOfflineHead(html, submitBlockedMessage);

    var apiEntries = <String, dynamic>{};
    if (recordApiResponses != null) {
      try {
        final recorded = await recordApiResponses(resolved);
        apiEntries = _mergeApiEntries(const {}, recorded);
      } catch (e, st) {
        DebugLogger.logWarn(
          'OFFLINE_BUNDLE',
          'Could not record form API data for assignment $assignmentId: $e\n$st',
        );
      }
    }
    await _writeApiCache(dir, apiEntries);

    final indexFile = File(p.join(dir.path, 'index.html'));
    await indexFile.writeAsString(html, flush: true);
    await File(p.join(dir.path, _urlRewriteMapFileName))
        .writeAsString(jsonEncode(savedRelByAbsolute), flush: true);
    await File(p.join(dir.path, _offlineRepairStampFile))
        .writeAsString(_offlineRepairStampValue, flush: true);

    final meta = <String, dynamic>{
      'assignment_id': assignmentId,
      'template_id': ?templateId,
      'source_url': resolved,
      'saved_at': DateTime.now().toUtc().toIso8601String(),
      'asset_count': count,
      'api_entry_count': apiEntries.length,
      'missing_asset_count': missingAssets.length,
      'external_ref_count': unmirroredExternalRefs,
      'language': language,
      if (title != null && title.isNotEmpty) 'title': title,
      if (staticVersion != null && staticVersion.isNotEmpty)
        'static_version': staticVersion,
      if (dataVersion != null && dataVersion.isNotEmpty)
        'data_version': dataVersion,
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
    if (await finalDir.exists()) {
      await finalDir.delete(recursive: true);
    }
    await dir.rename(finalDir.path);

    DebugLogger.logInfo(
      'OFFLINE_BUNDLE',
      'Saved bundle assignment=$assignmentId files=$count '
      'missing=${missingAssets.length} api=${apiEntries.length} '
      'index.html~${html.length}B .css-mentions~$cssInIndex '
      'href=static/*.css~$relStaticCssHrefs dir=${finalDir.path}',
    );
  }

  /// Merges recorded `{k, s, t, b}` entries into [existing], keeping the newest
  /// and dropping oversized entries.
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
          (a, b) => ((a.value as Map)['at'] as String)
              .compareTo((b.value as Map)['at'] as String),
        );
      for (final entry in byAge) {
        if (total <= _maxApiCacheBytes) break;
        total -= ((entry.value as Map)['b'] as String).length;
        out.remove(entry.key);
      }
    }
    return out;
  }

  Future<void> _writeApiCache(Directory dir, Map<String, dynamic> entries) async {
    final json = jsonEncode(entries);
    await File(p.join(dir.path, _apiCacheJsonFile))
        .writeAsString(json, flush: true);
    await File(p.join(dir.path, _apiCacheScriptFile))
        .writeAsString('window.__IFRC_OFFLINE_API__=$json;', flush: true);
  }

  Future<Map<String, dynamic>> _readApiCache(Directory dir) async {
    final f = File(p.join(dir.path, _apiCacheJsonFile));
    try {
      if (!await f.exists()) return <String, dynamic>{};
      final raw = jsonDecode(await f.readAsString());
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return <String, dynamic>{};
  }

  /// Adds API responses seen while the form was open online (lookup lists,
  /// plugin data, resolved variables …) to this assignment's saved copy.
  /// Returns false when there is no saved copy to add them to.
  Future<bool> mergeApiCache(
    int assignmentId,
    List<Map<String, dynamic>> entries,
  ) async {
    if (entries.isEmpty || !await hasOfflineBundle(assignmentId)) return false;
    final dir = await bundleDirFor(assignmentId);
    final merged = _mergeApiEntries(await _readApiCache(dir), entries);
    await _writeApiCache(dir, merged);
    final meta = await _readMetaJson(dir);
    if (meta != null) {
      meta['api_entry_count'] = merged.length;
      await File(p.join(dir.path, _metaFileName))
          .writeAsString(jsonEncode(meta), flush: true);
    }
    return true;
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
    savedCopiesChanged.value++;
  }

  static const Set<String> _externalMirrorExtensions = {
    '.js', '.mjs', '.css', '.woff', '.woff2', '.ttf', '.otf', '.eot',
    '.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico',
  };

  static const List<String> _externalSkipHosts = [
    'google-analytics.com',
    'googletagmanager.com',
    'doubleclick.net',
    'sentry.io',
    'hotjar.com',
    'clarity.ms',
  ];

  static const String _externalDirName = 'static/ext';

  bool _isSameOrigin(Uri asset, Uri pageUri) =>
      asset.host == pageUri.host && asset.port == pageUri.port;

  /// Third-party styles, scripts and fonts the form needs (CDN libraries, web
  /// fonts). Pages and API endpoints are never mirrored.
  bool _isMirrorableExternal(Uri asset) {
    final host = asset.host.toLowerCase();
    if (host.isEmpty) return false;
    for (final skip in _externalSkipHosts) {
      if (host == skip || host.endsWith('.$skip')) return false;
    }
    if (host == 'www.gstatic.com' && asset.path.startsWith('/charts/')) {
      return false;
    }
    if (host == 'fonts.googleapis.com' && asset.path.startsWith('/css')) {
      return true;
    }
    final ext = p.extension(asset.path).toLowerCase();
    return _externalMirrorExtensions.contains(ext);
  }

  bool _shouldMirror(Uri asset, Uri pageUri) {
    if (!asset.hasScheme || (asset.scheme != 'http' && asset.scheme != 'https')) {
      return false;
    }
    if (!_isSameOrigin(asset, pageUri)) {
      return _isMirrorableExternal(asset);
    }
    return _isBundledPath(asset.path);
  }

  static bool _isBundledPath(String path) =>
      path.startsWith('/static/') || path.startsWith('/plugins/static/');

  /// Stable on-disk path for a third-party file, kept under its host so relative
  /// references inside CDN stylesheets keep resolving.
  String _externalRelativePath(Uri absolute) {
    final host = absolute.hasPort
        ? '${absolute.host}_${absolute.port}'
        : absolute.host;
    var path = absolute.path;
    if (path.isEmpty || path.endsWith('/')) path = '${path}index';
    var ext = p.extension(path);
    if (ext.isEmpty && absolute.host == 'fonts.googleapis.com') ext = '.css';
    final base = p.extension(path).isEmpty
        ? path
        : path.substring(0, path.length - p.extension(path).length);
    var queryTag = '';
    if (absolute.hasQuery) {
      var h = 5381;
      for (final c in absolute.query.codeUnits) {
        h = ((h * 33) ^ c) & 0xFFFFFFFF;
      }
      queryTag = '.${h.toRadixString(36)}';
    }
    final safe = '$base$queryTag$ext'.replaceAll(RegExp(r'[^a-zA-Z0-9._/@-]'), '_');
    return '$_externalDirName/$host${safe.startsWith('/') ? safe : '/$safe'}';
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
      final relRe = RegExp(r'(?<!/plugins)' + tail, caseSensitive: false);
      for (final m in relRe.allMatches(html)) {
        out.add(pageUri.resolve(m.group(0)!));
      }
    } catch (_) {}

    // Plugin field modules/styles (/plugins/static/…) are named in the page's
    // data-entry-form-config JSON and are imported at runtime.
    try {
      final pluginRe = RegExp(
        r'/plugins/static/[\w./-]+\.' + ext,
        caseSensitive: false,
      );
      for (final m in pluginRe.allMatches(html)) {
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
          r'url\(\s*((?:\.\./|\./|/|https?:)[^)\s\x22\x27]+)\s*\)',
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

  static final RegExp _jsStaticLiteral = RegExp(
    r'''(["'`])(/(?:plugins/)?static/[\w./@-]*)\1''',
  );

  /// `'/static/…'` / `'/plugins/static/…'` string literals in plugin scripts
  /// (e.g. vendor libraries added with `script.src = …` at runtime).
  Set<Uri> _staticLiteralsFromJavaScript(String js, Uri jsLocation) {
    final out = <Uri>{};
    for (final m in _jsStaticLiteral.allMatches(js)) {
      final path = m.group(2)!;
      if (!RegExp(r'\.[A-Za-z0-9]{2,5}$').hasMatch(path)) continue;
      try {
        out.add(jsLocation.resolve(path));
      } catch (_) {}
    }
    return out;
  }

  /// `file://` has no site root, so root-absolute asset paths inside saved
  /// scripts must be made relative: module specifiers (which resolve against the
  /// importing file) and, for plugin scripts, other string literals (which
  /// resolve against the page).
  String _rewriteRootStaticInJs(String js, String fileRelPosix) {
    final fromDir = _posix.dirname(fileRelPosix);
    final isPlugin = fileRelPosix.startsWith('plugins/static/');

    String fileRelative(String rootPath) {
      var q = rootPath.indexOf('?');
      final hash = rootPath.indexOf('#');
      if (hash != -1 && (q == -1 || hash < q)) q = hash;
      final pathOnly = q == -1 ? rootPath : rootPath.substring(0, q);
      final suffix = q == -1 ? '' : rootPath.substring(q);
      var rel = _posix.relative(pathOnly.substring(1), from: fromDir);
      if (!rel.startsWith('.')) rel = './$rel';
      return '$rel$suffix';
    }

    var out = js.replaceAllMapped(
      RegExp(
        r'''(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(["'])(/(?:plugins/)?static/[^"'\s]+)\2''',
      ),
      (m) => '${m[1]}${m[2]}${fileRelative(m[3]!)}${m[2]}',
    );
    if (isPlugin) {
      out = out.replaceAllMapped(
        _jsStaticLiteral,
        (m) => '${m[1]}${m[2]!.substring(1)}${m[1]}',
      );
    }
    return out;
  }

  Future<void> _rewriteRootStaticInBundleScripts(Directory dir) async {
    await for (final entity in dir.list(recursive: true, followLinks: false)) {
      if (entity is! File) continue;
      final lower = entity.path.toLowerCase();
      if (!lower.endsWith('.js') && !lower.endsWith('.mjs')) continue;
      final rel = p.relative(entity.path, from: dir.path).replaceAll(r'\', '/');
      if (rel.startsWith('$_externalDirName/')) continue;
      late final String raw;
      try {
        raw = await entity.readAsString(encoding: utf8);
      } catch (_) {
        continue;
      }
      if (!raw.contains('/static/')) continue;
      final next = _rewriteRootStaticInJs(raw, rel);
      if (next != raw) await entity.writeAsString(next, flush: true);
    }
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
          !s.startsWith('/static/') &&
          !s.startsWith('/plugins/static/')) {
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
          r'from\s+"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"from\s+'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'",
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    // import "…" / '…' (side-effect)
    for (final m in RegExp(
          r'import\s+"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"import\s+'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'",
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    // import("…") / import('…')
    for (final m in RegExp(
          r'import\s*\(\s*"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"\s*\)',
          caseSensitive: false,
        )
        .allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
          r"import\s*\(\s*'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'\s*\)",
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
    s = s.replaceAllMapped(
      RegExp(
        r'\b(href|src)\s*=\s*([\x22\x27])/plugins/static/',
        caseSensitive: true,
      ),
      (m) => '${m[1]}=${m[2]}plugins/static/',
    );
    s = s.replaceAllMapped(
      RegExp(
        r'(<script\b[^>]*\btype\s*=\s*[\x22\x27]module[\x22\x27][^>]*>)([\s\S]*?)(</script>)',
        caseSensitive: false,
      ),
      (m) =>
          '${m[1]}${m[2]!.replaceAll('"/plugins/static/', '"./plugins/static/').replaceAll("'/plugins/static/", "'./plugins/static/")}${m[3]}',
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

  Map<String, String> _headersWithoutCredentials(Map<String, String> headers) {
    return {
      for (final e in headers.entries)
        if (e.key.toLowerCase() != 'cookie' &&
            e.key.toLowerCase() != 'authorization')
          e.key: e.value,
    };
  }

  /// Points absolute third-party URLs inside saved stylesheets (web font files,
  /// nested imports) at their mirrored copies.
  Future<void> _rewriteExternalUrlsInCss(
    Directory dir,
    Map<String, String> savedRelByAbsolute,
  ) async {
    final mirrored = <String, String>{
      for (final e in savedRelByAbsolute.entries)
        if (e.value.startsWith('$_externalDirName/')) e.key: e.value,
    };
    if (mirrored.isEmpty) return;
    final keys = mirrored.keys.toList()
      ..sort((a, b) => b.length.compareTo(a.length));
    await for (final entity in dir.list(recursive: true, followLinks: false)) {
      if (entity is! File || !entity.path.toLowerCase().endsWith('.css')) {
        continue;
      }
      late final String raw;
      try {
        raw = await entity.readAsString(encoding: utf8);
      } catch (_) {
        continue;
      }
      final fileRel =
          p.relative(entity.path, from: dir.path).replaceAll(r'\', '/');
      final fromDir = _posix.dirname(fileRel);
      var next = raw;
      for (final abs in keys) {
        if (!next.contains(abs) && !next.contains(abs.substring(abs.indexOf('//')))) {
          continue;
        }
        final target = _posix.relative(mirrored[abs]!, from: fromDir);
        next = next.split(abs).join(target);
        next = next.split(abs.substring(abs.indexOf('//'))).join(target);
      }
      if (next != raw) {
        await entity.writeAsString(next, flush: true);
      }
    }
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
      final candidates = <String>{abs};
      if (!uri.hasQuery || uri.path.startsWith('/static/')) {
        candidates.add(withoutQuery);
      }
      for (final c in List<String>.of(candidates)) {
        final i = c.indexOf('//');
        if (i != -1) candidates.add(c.substring(i));
      }
      for (final candidate in candidates) {
        s = s.split(candidate).join(rel);
        for (final esc in <String>{
          const HtmlEscape().convert(candidate),
          const HtmlEscape(HtmlEscapeMode.attribute).convert(candidate),
        }) {
          if (esc != candidate) s = s.split(esc).join(rel);
        }
      }
    }
    return s;
  }

  /// Adds the offline runtime (API replay, online-only actions, static URL stub).
  String _injectOfflineHead(String html, String submitBlockedMessage) {
    final patch = buildOfflineHeadPatch(
      submitBlockedMessage: submitBlockedMessage,
    );
    final lower = html.toLowerCase();
    final idx = lower.indexOf('</head>');
    final withHead = idx != -1
        ? html.substring(0, idx) + patch + html.substring(idx)
        : patch + html;
    final bodyEnd = withHead.toLowerCase().lastIndexOf('</body>');
    if (bodyEnd == -1) return withHead + kOfflinePluginPathsScript;
    return withHead.substring(0, bodyEnd) +
        kOfflinePluginPathsScript +
        withHead.substring(bodyEnd);
  }
}

class AssignmentOfflineBundleException implements Exception {
  final String message;
  AssignmentOfflineBundleException(this.message);

  @override
  String toString() => message;
}
