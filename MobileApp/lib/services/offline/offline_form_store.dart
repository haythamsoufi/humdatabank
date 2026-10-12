import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import '../../models/shared/assignment.dart';
import '../../utils/debug_logger.dart';
import '../user_scope_service.dart';

/// Folder name for the package that holds a form template's saved files.
///
/// All assignments of one template (for any entity) share one package: the
/// markup-independent files (`/static/`, plugin and third-party assets) and the
/// recorded API data. Only the small per-assignment page differs.
String offlinePackageKey({
  required int? templateId,
  required int assignmentId,
}) => templateId != null ? 'template_$templateId' : 'solo_$assignmentId';

/// What a saved template package was captured from.
class OfflinePackageMeta {
  const OfflinePackageMeta({
    required this.key,
    this.templateId,
    this.title,
    this.staticVersion,
    this.formDefinitionUpdatedAtIso,
    this.savedAtUtc,
    this.assetCount = 0,
    this.missingAssetCount = 0,
    this.externalRefCount = 0,
    this.apiEntryCount = 0,
  });

  final String key;
  final int? templateId;
  final String? title;

  /// Server static-files release the files were copied from.
  final String? staticVersion;

  /// Published form definition the package was captured with. Only compared
  /// when the server does not report a static release.
  final String? formDefinitionUpdatedAtIso;
  final DateTime? savedAtUtc;
  final int assetCount;
  final int missingAssetCount;
  final int externalRefCount;

  /// Number of recorded API responses (lookup lists, plugin data, ...).
  final int apiEntryCount;

  Map<String, dynamic> toJson() => {
    'layout': OfflineFormStore.layoutVersion,
    'key': key,
    'template_id': ?templateId,
    if (title != null && title!.isNotEmpty) 'title': title,
    if (staticVersion != null && staticVersion!.isNotEmpty)
      'static_version': staticVersion,
    if (formDefinitionUpdatedAtIso != null &&
        formDefinitionUpdatedAtIso!.isNotEmpty)
      'form_definition_updated_at': formDefinitionUpdatedAtIso,
    'saved_at': (savedAtUtc ?? DateTime.now().toUtc()).toIso8601String(),
    'asset_count': assetCount,
    'missing_asset_count': missingAssetCount,
    'external_ref_count': externalRefCount,
    'api_entry_count': apiEntryCount,
  };

  static OfflinePackageMeta? fromJson(String key, Map<String, dynamic> json) {
    if ((json['layout'] as num?)?.toInt() != OfflineFormStore.layoutVersion) {
      return null;
    }
    return OfflinePackageMeta(
      key: key,
      templateId: (json['template_id'] as num?)?.toInt(),
      title: json['title']?.toString(),
      staticVersion: json['static_version']?.toString(),
      formDefinitionUpdatedAtIso: json['form_definition_updated_at']
          ?.toString(),
      savedAtUtc: DateTime.tryParse(
        json['saved_at']?.toString() ?? '',
      )?.toUtc(),
      assetCount: (json['asset_count'] as num?)?.toInt() ?? 0,
      missingAssetCount: (json['missing_asset_count'] as num?)?.toInt() ?? 0,
      externalRefCount: (json['external_ref_count'] as num?)?.toInt() ?? 0,
      apiEntryCount: (json['api_entry_count'] as num?)?.toInt() ?? 0,
    );
  }

  OfflinePackageMeta copyWith({
    int? assetCount,
    int? missingAssetCount,
    int? apiEntryCount,
  }) => OfflinePackageMeta(
    key: key,
    templateId: templateId,
    title: title,
    staticVersion: staticVersion,
    formDefinitionUpdatedAtIso: formDefinitionUpdatedAtIso,
    savedAtUtc: savedAtUtc,
    assetCount: assetCount ?? this.assetCount,
    missingAssetCount: missingAssetCount ?? this.missingAssetCount,
    externalRefCount: externalRefCount,
    apiEntryCount: apiEntryCount ?? this.apiEntryCount,
  );
}

/// One assignment's saved page (the server-rendered form with its data).
class OfflinePageMeta {
  const OfflinePageMeta({
    required this.assignmentId,
    required this.packageKey,
    this.templateId,
    this.title,
    this.sourceUrl,
    this.savedAtUtc,
    this.formDefinitionUpdatedAtIso,
    this.dataVersion,
    this.staticVersion,
    this.language,
  });

  final int assignmentId;
  final String packageKey;
  final int? templateId;
  final String? title;
  final String? sourceUrl;
  final DateTime? savedAtUtc;
  final String? formDefinitionUpdatedAtIso;

  /// [Assignment.dataVersion] at capture time.
  final String? dataVersion;

  /// Static release of the package the page was written against.
  final String? staticVersion;

  /// Language of the saved markup.
  final String? language;

  Map<String, dynamic> toJson() => {
    'assignment_id': assignmentId,
    'package_key': packageKey,
    'template_id': ?templateId,
    if (title != null && title!.isNotEmpty) 'title': title,
    'source_url': ?sourceUrl,
    'saved_at': (savedAtUtc ?? DateTime.now().toUtc()).toIso8601String(),
    if (formDefinitionUpdatedAtIso != null &&
        formDefinitionUpdatedAtIso!.isNotEmpty)
      'form_definition_updated_at': formDefinitionUpdatedAtIso,
    if (dataVersion != null && dataVersion!.isNotEmpty)
      'data_version': dataVersion,
    if (staticVersion != null && staticVersion!.isNotEmpty)
      'static_version': staticVersion,
    if (language != null && language!.isNotEmpty) 'language': language,
  };

  static OfflinePageMeta? fromJson(
    String packageKey,
    Map<String, dynamic> json,
  ) {
    final id = (json['assignment_id'] as num?)?.toInt();
    if (id == null) return null;
    return OfflinePageMeta(
      assignmentId: id,
      packageKey: packageKey,
      templateId: (json['template_id'] as num?)?.toInt(),
      title: json['title']?.toString(),
      sourceUrl: json['source_url']?.toString(),
      savedAtUtc: DateTime.tryParse(
        json['saved_at']?.toString() ?? '',
      )?.toUtc(),
      formDefinitionUpdatedAtIso: json['form_definition_updated_at']
          ?.toString(),
      dataVersion: json['data_version']?.toString(),
      staticVersion: json['static_version']?.toString(),
      language: json['language']?.toString(),
    );
  }
}

/// Snapshot of everything saved for the signed-in user, read in one pass.
class OfflineFormsIndex {
  const OfflineFormsIndex({this.packages = const {}, this.pages = const {}});

  static const OfflineFormsIndex empty = OfflineFormsIndex();

  final Map<String, OfflinePackageMeta> packages;
  final Map<int, OfflinePageMeta> pages;

  bool hasPage(int assignmentId) => pages.containsKey(assignmentId);

  /// Template ids that have a saved package on this device.
  Set<int> get templateIds => {
    for (final p in packages.values)
      if (p.templateId != null) p.templateId!,
  };

  List<OfflinePageMeta> pagesOf(String packageKey) => [
    for (final page in pages.values)
      if (page.packageKey == packageKey) page,
  ];
}

/// One saved template as listed on the storage screen.
class OfflinePackageSummary {
  const OfflinePackageSummary({
    required this.key,
    this.templateId,
    this.title,
    this.savedAt,
    required this.sizeBytes,
    required this.assignmentIds,
  });

  final String key;
  final int? templateId;
  final String? title;
  final DateTime? savedAt;
  final int sizeBytes;
  final List<int> assignmentIds;
}

/// Whether the saved files of an assignment can still be used as they are.
class OfflineFormStatus {
  const OfflineFormStatus({
    this.hasPackage = false,
    this.packageCurrent = false,
    this.hasPage = false,
    this.pageCurrent = false,
  });

  static const OfflineFormStatus none = OfflineFormStatus();

  /// A package for the assignment's template exists on this device.
  final bool hasPackage;

  /// The package matches the server's current static release.
  final bool packageCurrent;

  /// The assignment has its own saved page, so it opens offline.
  final bool hasPage;

  /// The page matches the server's data, form definition and language.
  final bool pageCurrent;

  /// Opens offline.
  bool get available => hasPage;

  /// A cheap refresh (one page request) is enough to bring this up to date.
  bool get needsPage => packageCurrent && !pageCurrent;

  /// The shared files must be downloaded again (large).
  bool get needsPackage => hasPackage && !packageCurrent;

  /// Saved, but no longer matching the server.
  bool get outdated => hasPage && (!packageCurrent || !pageCurrent);

  @override
  bool operator ==(Object other) =>
      other is OfflineFormStatus &&
      other.hasPackage == hasPackage &&
      other.packageCurrent == packageCurrent &&
      other.hasPage == hasPage &&
      other.pageCurrent == pageCurrent;

  @override
  int get hashCode =>
      Object.hash(hasPackage, packageCurrent, hasPage, pageCurrent);
}

bool _isoDiffers(DateTime? server, String? cachedIso) {
  if (server == null) return false;
  if (cachedIso == null || cachedIso.isEmpty) return true;
  final cached = DateTime.tryParse(cachedIso);
  if (cached == null) return true;
  final delta =
      server.toUtc().millisecondsSinceEpoch -
      cached.toUtc().millisecondsSinceEpoch;
  return delta.abs() > 1500;
}

/// True when [package]'s files come from the release the server serves now.
bool isOfflinePackageCurrent(
  OfflinePackageMeta package, {
  String? staticVersion,
  DateTime? formDefinitionUpdatedAt,
}) {
  if (staticVersion != null && staticVersion.isNotEmpty) {
    return package.staticVersion == staticVersion;
  }
  // Older servers report no static release: fall back to the form definition.
  if (formDefinitionUpdatedAt == null) return true;
  return !_isoDiffers(
    formDefinitionUpdatedAt,
    package.formDefinitionUpdatedAtIso,
  );
}

/// Compares an assignment with what is saved for it.
OfflineFormStatus evaluateOfflineForm(
  Assignment assignment,
  OfflineFormsIndex index, {
  String? language,
}) {
  final page = index.pages[assignment.id];
  final key =
      page?.packageKey ??
      offlinePackageKey(
        templateId: assignment.templateId,
        assignmentId: assignment.id,
      );
  final package = index.packages[key];
  if (package == null) return OfflineFormStatus.none;

  final packageCurrent = isOfflinePackageCurrent(
    package,
    staticVersion: assignment.staticVersion,
    formDefinitionUpdatedAt: assignment.formDefinitionUpdatedAt,
  );
  if (page == null) {
    return OfflineFormStatus(hasPackage: true, packageCurrent: packageCurrent);
  }

  var pageCurrent = page.staticVersion == package.staticVersion;
  if (pageCurrent &&
      _isoDiffers(
        assignment.formDefinitionUpdatedAt,
        page.formDefinitionUpdatedAtIso,
      )) {
    pageCurrent = false;
  }
  final serverData = assignment.dataVersion;
  if (pageCurrent && serverData != null && serverData.isNotEmpty) {
    final cachedData = page.dataVersion;
    if (cachedData == null || cachedData.isEmpty) {
      pageCurrent = false;
    } else {
      final a = DateTime.tryParse(serverData);
      final b = DateTime.tryParse(cachedData);
      if (a != null && b != null) {
        pageCurrent =
            (a.toUtc().millisecondsSinceEpoch -
                    b.toUtc().millisecondsSinceEpoch)
                .abs() <=
            1500;
      } else {
        pageCurrent = serverData == cachedData;
      }
    }
  }
  final pageLanguage = page.language;
  if (pageCurrent &&
      language != null &&
      language.isNotEmpty &&
      pageLanguage != null &&
      pageLanguage.isNotEmpty &&
      pageLanguage != language) {
    pageCurrent = false;
  }
  return OfflineFormStatus(
    hasPackage: true,
    packageCurrent: packageCurrent,
    hasPage: true,
    pageCurrent: pageCurrent,
  );
}

/// On-disk layout of the saved forms of one signed-in user:
///
/// ```
/// <documents>/offline_assignment_bundles/<user scope>/
///   template_<id>/            one package per form template
///     package.json            what the package was captured from
///     assets.json             absolute URL -> saved file
///     offline_api_cache.js    recorded API data, replayed by every page
///     static/ plugins/static/ saved scripts, styles, fonts, images
///     page_<assignment>.html  one server-rendered page per assignment
///     page_<assignment>.json
/// ```
///
/// Pages sit next to the shared files so that their relative `static/...`
/// references resolve unchanged from `file://`.
class OfflineFormStore {
  OfflineFormStore({Directory? baseDir, String? scope})
    : _baseDirOverride = baseDir,
      _scopeOverride = scope;

  /// Bumped when the layout above changes. Packages with another value are
  /// ignored and removed.
  static const int layoutVersion = 2;
  static const String packageFile = 'package.json';
  static const String assetsFile = 'assets.json';
  static const String apiCacheJsonFile = 'offline_api_cache.json';
  static const String apiCacheScriptFile = 'offline_api_cache.js';

  static final RegExp _pageFileName = RegExp(r'^page_(\d+)\.json$');

  final Directory? _baseDirOverride;
  final String? _scopeOverride;

  String? _scopeCache;
  DateTime _scopeCheckedAt = DateTime.fromMillisecondsSinceEpoch(0);
  String? _housekeptScope;

  static String pageHtmlName(int assignmentId) => 'page_$assignmentId.html';
  static String pageMetaName(int assignmentId) => 'page_$assignmentId.json';

  Future<Directory> _baseDir() async {
    final override = _baseDirOverride;
    final dir =
        override ??
        Directory(
          p.join(
            (await getApplicationDocumentsDirectory()).path,
            'offline_assignment_bundles',
          ),
        );
    if (!await dir.exists()) await dir.create(recursive: true);
    return dir;
  }

  static String _safeScope(String scope) =>
      scope.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');

  /// The signed-in user's folder name. Once a stable `user_` scope has been
  /// seen it is kept for a minute at a time, so a briefly missing profile cache
  /// can neither hide saved forms nor read the profile on every call.
  Future<String> _scope() async {
    final override = _scopeOverride;
    if (override != null) return _safeScope(override);
    final cached = _scopeCache;
    if (cached != null &&
        DateTime.now().difference(_scopeCheckedAt) <
            const Duration(minutes: 1)) {
      return cached;
    }
    final fresh = _safeScope(
      await UserScopeService().getScope(includeAuth: true),
    );
    if (fresh.startsWith('user_') || cached == null) {
      _scopeCache = fresh;
    }
    _scopeCheckedAt = DateTime.now();
    return _scopeCache ?? fresh;
  }

  /// Forgets the remembered user (after sign-out).
  void resetScope() {
    _scopeCache = null;
    _housekeptScope = null;
  }

  /// The signed-in user's folder. Folders of other users and of the previous
  /// layout are removed the first time a stable user scope is seen.
  Future<Directory> root() async {
    final base = await _baseDir();
    final scope = await _scope();
    final dir = Directory(p.join(base.path, scope));
    if (!await dir.exists()) await dir.create(recursive: true);
    if (_housekeptScope != scope) {
      _housekeptScope = scope;
      try {
        await for (final e in base.list(followLinks: false)) {
          final name = p.basename(e.path);
          if (e is Directory && name == scope) continue;
          if (e is Directory &&
              (name.startsWith('assignment_') || scope.startsWith('user_'))) {
            await e.delete(recursive: true);
          }
        }
        await for (final e in dir.list(followLinks: false)) {
          final name = p.basename(e.path);
          if (e is Directory &&
              (name.startsWith('assignment_') ||
                  name.startsWith('tmp_') ||
                  name.startsWith('tmp-'))) {
            await e.delete(recursive: true);
          }
        }
      } catch (e) {
        DebugLogger.logWarn('OFFLINE_STORE', 'Housekeeping failed: $e');
      }
    }
    return dir;
  }

  Future<Directory> packageDir(String key) async =>
      Directory(p.join((await root()).path, key));

  Future<Directory> stagingDir(String key) async =>
      Directory(p.join((await root()).path, 'tmp_$key'));

  Future<List<Directory>> _packageDirs() async {
    final out = <Directory>[];
    await for (final e in (await root()).list(followLinks: false)) {
      if (e is! Directory) continue;
      final name = p.basename(e.path);
      if (name.startsWith('template_') || name.startsWith('solo_')) out.add(e);
    }
    return out;
  }

  Future<Map<String, dynamic>?> readJson(File file) async {
    try {
      if (!await file.exists()) return null;
      final raw = jsonDecode(await file.readAsString());
      if (raw is Map) return Map<String, dynamic>.from(raw);
    } catch (_) {}
    return null;
  }

  /// Writes through a temporary file so a reader never sees half a file.
  Future<void> writeJson(File file, Object value) async {
    final tmp = File('${file.path}.tmp');
    await tmp.writeAsString(jsonEncode(value), flush: true);
    await tmp.rename(file.path);
  }

  Future<OfflinePackageMeta?> readPackageMeta(String key) async {
    final dir = await packageDir(key);
    final json = await readJson(File(p.join(dir.path, packageFile)));
    return json == null ? null : OfflinePackageMeta.fromJson(key, json);
  }

  Future<void> writePackageMeta(Directory dir, OfflinePackageMeta meta) =>
      writeJson(File(p.join(dir.path, packageFile)), meta.toJson());

  Future<Map<String, String>> readAssets(Directory dir) async {
    final json = await readJson(File(p.join(dir.path, assetsFile)));
    return {
      if (json != null)
        for (final e in json.entries) e.key: e.value.toString(),
    };
  }

  Future<void> writeAssets(Directory dir, Map<String, String> assets) =>
      writeJson(File(p.join(dir.path, assetsFile)), assets);

  /// Reads every package and page in one pass. Packages written by another
  /// layout version are deleted; pages without their markup are ignored.
  Future<OfflineFormsIndex> readIndex() async {
    final packages = <String, OfflinePackageMeta>{};
    final pages = <int, OfflinePageMeta>{};
    for (final dir in await _packageDirs()) {
      final key = p.basename(dir.path);
      final meta = OfflinePackageMeta.fromJson(
        key,
        await readJson(File(p.join(dir.path, packageFile))) ?? const {},
      );
      if (meta == null) {
        try {
          await dir.delete(recursive: true);
        } catch (_) {}
        continue;
      }
      packages[key] = meta;
      await for (final f in dir.list(followLinks: false)) {
        if (f is! File) continue;
        final m = _pageFileName.firstMatch(p.basename(f.path));
        if (m == null) continue;
        final id = int.parse(m.group(1)!);
        if (!File(p.join(dir.path, pageHtmlName(id))).existsSync()) continue;
        final page = OfflinePageMeta.fromJson(
          key,
          await readJson(f) ?? const {},
        );
        if (page != null) pages[id] = page;
      }
    }
    return OfflineFormsIndex(packages: packages, pages: pages);
  }

  /// Absolute path of an assignment's saved page, or null when it has none.
  Future<String?> pagePath(int assignmentId) async {
    for (final dir in await _packageDirs()) {
      final file = File(p.join(dir.path, pageHtmlName(assignmentId)));
      if (file.existsSync() &&
          File(p.join(dir.path, packageFile)).existsSync()) {
        return file.path;
      }
    }
    return null;
  }

  /// Every saved template with its disk footprint, newest first.
  Future<List<OfflinePackageSummary>> listPackages() async {
    final index = await readIndex();
    final out = <OfflinePackageSummary>[];
    for (final meta in index.packages.values) {
      var size = 0;
      try {
        final dir = await packageDir(meta.key);
        await for (final e in dir.list(recursive: true, followLinks: false)) {
          if (e is File) size += await e.length();
        }
      } catch (_) {}
      out.add(
        OfflinePackageSummary(
          key: meta.key,
          templateId: meta.templateId,
          title: meta.title,
          savedAt: meta.savedAtUtc?.toLocal(),
          sizeBytes: size,
          assignmentIds: [
            for (final page in index.pagesOf(meta.key)) page.assignmentId,
          ]..sort(),
        ),
      );
    }
    out.sort(
      (a, b) => (b.savedAt ?? DateTime.fromMillisecondsSinceEpoch(0)).compareTo(
        a.savedAt ?? DateTime.fromMillisecondsSinceEpoch(0),
      ),
    );
    return out;
  }

  Future<void> deletePackage(String key) async {
    final dir = await packageDir(key);
    if (await dir.exists()) await dir.delete(recursive: true);
  }

  /// Removes every package of [templateId] and the solo package of
  /// [alsoAssignmentId]. Returns whether anything was removed.
  Future<bool> deleteTemplate(int templateId, {int? alsoAssignmentId}) async {
    var removed = false;
    for (final dir in await _packageDirs()) {
      final key = p.basename(dir.path);
      final meta = await readPackageMeta(key);
      final matches =
          meta?.templateId == templateId ||
          (alsoAssignmentId != null && key == 'solo_$alsoAssignmentId');
      if (matches) {
        await dir.delete(recursive: true);
        removed = true;
      }
    }
    return removed;
  }

  Future<void> deleteAll() async {
    final base = await _baseDir();
    await for (final e in base.list(followLinks: false)) {
      await e.delete(recursive: true);
    }
    resetScope();
  }

  Future<void> deletePage(OfflinePageMeta page) async {
    final dir = await packageDir(page.packageKey);
    for (final name in [
      pageHtmlName(page.assignmentId),
      pageMetaName(page.assignmentId),
    ]) {
      final f = File(p.join(dir.path, name));
      if (await f.exists()) await f.delete();
    }
  }

  /// Frees storage held by pages of closed assignments, pages that have not
  /// been refreshed for [maxAge], and the oldest pages beyond [maxPages].
  /// Packages left without any page are removed.
  Future<int> prune({
    Set<int> closedAssignmentIds = const {},
    Duration maxAge = const Duration(days: 90),
    int maxPages = 80,
    DateTime? now,
  }) async {
    final clock = (now ?? DateTime.now()).toUtc();
    final index = await readIndex();
    final epoch = DateTime.fromMillisecondsSinceEpoch(0, isUtc: true);
    final keep = <OfflinePageMeta>[];
    var removed = 0;
    for (final page in index.pages.values) {
      final savedAt = page.savedAtUtc ?? epoch;
      if (closedAssignmentIds.contains(page.assignmentId) ||
          clock.difference(savedAt) > maxAge) {
        await deletePage(page);
        removed++;
      } else {
        keep.add(page);
      }
    }
    if (keep.length > maxPages) {
      keep.sort(
        (a, b) => (a.savedAtUtc ?? epoch).compareTo(b.savedAtUtc ?? epoch),
      );
      final surplus = keep.take(keep.length - maxPages).toList();
      for (final page in surplus) {
        await deletePage(page);
        keep.remove(page);
        removed++;
      }
    }
    final liveKeys = {for (final page in keep) page.packageKey};
    for (final key in index.packages.keys) {
      if (!liveKeys.contains(key)) {
        await deletePackage(key);
        removed++;
      }
    }
    return removed;
  }
}
