import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/services/assignment_offline_bundle_service.dart';
import 'package:hum_databank_app/widgets/offline_storage_sheet.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path/path.dart' as p;

class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.routes);

  final Map<String, ({int status, String body})> routes;
  final List<String> requested = [];
  final Map<String, Map<String, dynamic>> headersByHost = {};

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requested.add(options.uri.path);
    headersByHost[options.uri.host] = Map.of(options.headers);
    final r = routes[options.uri.path];
    if (r == null) return ResponseBody.fromBytes(<int>[], 404);
    return ResponseBody.fromBytes(utf8.encode(r.body), r.status);
  }

  @override
  void close({bool force = false}) {}
}

const _html = '<html><head>'
    '<link rel="stylesheet" href="/static/css/app.css?v=1">'
    '<script src="/static/js/app.js?v=1"></script>'
    '</head><body><form>form</form></body></html>';

Map<String, ({int status, String body})> _routes({bool cssOk = true}) => {
      '/forms/assignment/5': (status: 200, body: _html),
      '/forms/assignment/6': (status: 200, body: _html),
      '/static/css/app.css': (status: cssOk ? 200 : 404, body: 'body{color:red}'),
      '/static/js/app.js': (status: 200, body: 'console.log(1);'),
    };

void main() {
  late Directory tmp;
  late _FakeAdapter adapter;
  late AssignmentOfflineBundleService svc;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  AssignmentOfflineBundleService build(_FakeAdapter a, {String scope = 'user_1'}) {
    final dio = Dio(BaseOptions(validateStatus: (c) => c != null && c < 500))
      ..httpClientAdapter = a;
    return AssignmentOfflineBundleService.forTesting(
      dio: dio,
      baseDir: tmp,
      scope: scope,
    );
  }

  Future<void> download(
    AssignmentOfflineBundleService s,
    int id, {
    int? templateId = 7,
    String? staticVersion = 'v1',
    String? dataVersion = '2026-01-01T00:00:00+00:00',
    String language = 'en',
    Future<List<Map<String, dynamic>>> Function(String)? record,
  }) {
    return s.downloadAndSave(
      assignmentId: id,
      formPath: '/forms/assignment/$id',
      language: language,
      templateId: templateId,
      staticVersion: staticVersion,
      dataVersion: dataVersion,
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00+00:00',
      submitBlockedMessage: 'Submit online only',
      recordApiResponses: record,
    );
  }

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('offline_bundle_test');
    adapter = _FakeAdapter(_routes());
    svc = build(adapter);
  });

  tearDown(() async {
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  group('storage listing', () {
    test('lists copies with size and title and notifies on removal', () async {
      await svc.downloadAndSave(
        assignmentId: 5,
        formPath: '/forms/assignment/5',
        language: 'en',
        templateId: 7,
        title: 'Annual report · 2026',
      );
      final copies = await svc.listSavedCopies();
      expect(copies, hasLength(1));
      expect(copies.single.assignmentId, 5);
      expect(copies.single.templateId, 7);
      expect(copies.single.title, 'Annual report · 2026');
      expect(copies.single.sizeBytes, greaterThan(0));

      final before = AssignmentOfflineBundleService.savedCopiesChanged.value;
      await svc.deleteBundle(5);
      expect(AssignmentOfflineBundleService.savedCopiesChanged.value, greaterThan(before));
      expect(await svc.listSavedCopies(), isEmpty);
    });

    test('groups copies by template for the storage screen', () {
      final now = DateTime(2026, 1, 1);
      final groups = groupOfflineCopies([
        OfflineCopySummary(assignmentId: 1, templateId: 7, title: 'A', savedAt: now, sizeBytes: 10),
        OfflineCopySummary(assignmentId: 2, templateId: 7, title: 'A', savedAt: now, sizeBytes: 20),
        const OfflineCopySummary(assignmentId: 3, sizeBytes: 5),
      ]);
      expect(groups, hasLength(2));
      expect(groups.first.copies, hasLength(2));
      expect(groups.first.sizeBytes, 30);
      expect(groups.last.title, '#3');
    });

    test('auto-download preference persists and notifies', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      expect(await svc.isAutoDownloadEnabled(), isFalse);
      final before = AssignmentOfflineBundleService.autoDownloadChanged.value;
      await svc.setAutoDownloadEnabled(true);
      expect(await svc.isAutoDownloadEnabled(), isTrue);
      expect(AssignmentOfflineBundleService.autoDownloadChanged.value, greaterThan(before));
    });
  });

  group('plugin fields', () {
    const pluginHtml = '<html><head>'
        '<script type="module" src="/static/js/forms/main.js?v=1"></script>'
        '</head><body>'
        "<div class=\"plugin-field-container\" data-entry-form-config='"
        '{&#34;es_module_path&#34;: &#34;/plugins/static/eo/js/field.js&#34;, '
        '&#34;css_files&#34;: [&#34;/plugins/static/eo/css/field.css&#34;]}'
        "'></div>"
        '<script type="module">import { X } from "/plugins/static/eo/js/inline.js";</script>'
        '<link rel="stylesheet" href="/plugins/static/eo/css/field.css">'
        '</body></html>';

    _FakeAdapter pluginAdapter() => _FakeAdapter({
          '/forms/assignment/5': (status: 200, body: pluginHtml),
          '/static/js/forms/main.js': (status: 200, body: 'export const a=1;'),
          '/plugins/static/eo/js/field.js': (
            status: 200,
            body: "import { log } from '/static/js/forms/modules/debug.js';\n"
                "import { h } from './helper.js';\n"
                "const mod = await import('/plugins/static/eo/js/lazy.js');\n"
                "script.src = '/static/vendor/leaflet/leaflet.js';\n"
          ),
          '/plugins/static/eo/js/helper.js': (status: 200, body: 'export const h=1;'),
          '/plugins/static/eo/js/lazy.js': (status: 200, body: 'export const l=1;'),
          '/plugins/static/eo/js/inline.js': (status: 200, body: 'export const X=1;'),
          '/plugins/static/eo/css/field.css': (status: 200, body: '.eo{color:red}'),
          '/static/js/forms/modules/debug.js': (status: 200, body: 'export const log=1;'),
          '/static/vendor/leaflet/leaflet.js': (status: 200, body: 'L={};'),
        });

    test('mirrors plugin modules, styles and their imports', () async {
      final s = build(pluginAdapter());
      await download(s, 5);
      final dir = Directory(await s.offlineBundleDirectoryPath(5));
      for (final f in [
        'plugins/static/eo/js/field.js',
        'plugins/static/eo/js/helper.js',
        'plugins/static/eo/js/lazy.js',
        'plugins/static/eo/js/inline.js',
        'plugins/static/eo/css/field.css',
        'static/js/forms/modules/debug.js',
        'static/vendor/leaflet/leaflet.js',
      ]) {
        expect(File(p.join(dir.path, f)).existsSync(), isTrue, reason: f);
      }
    });

    test('makes root-absolute paths inside plugin scripts work from disk',
        () async {
      final s = build(pluginAdapter());
      await download(s, 5);
      final dir = Directory(await s.offlineBundleDirectoryPath(5));
      final js = File(p.join(dir.path, 'plugins/static/eo/js/field.js'))
          .readAsStringSync();
      expect(js, contains("from '../../../../static/js/forms/modules/debug.js'"));
      expect(js, contains("import('./lazy.js')"));
      expect(js, contains("script.src = 'static/vendor/leaflet/leaflet.js'"));
      expect(js, isNot(contains("'/static/")));
    });

    test('points the page at saved plugin files', () async {
      final s = build(pluginAdapter());
      await download(s, 5);
      final html = (await s.readOfflineIndexHtml(5))!;
      expect(html, contains('href="plugins/static/eo/css/field.css"'));
      expect(html, contains('from "./plugins/static/eo/js/inline.js"'));
      expect(html, contains('data-entry-form-config'));
      expect(html, contains("var P = '/plugins/static/'"));
      expect(html.lastIndexOf('var P = ') < html.toLowerCase().lastIndexOf('</body>'), isTrue);
    });
  });

  group('third-party files', () {
    const extHtml = '<html><head>'
        '<link rel="stylesheet" href="/static/css/app.css?v=1">'
        '<link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=Inter:wght@400&amp;display=swap">'
        '<script src="https://cdn.example.com/lib/chart.min.js"></script>'
        '<script src="https://www.googletagmanager.com/gtag/js?id=X"></script>'
        '<link rel="preconnect" href="https://fonts.gstatic.com">'
        '</head><body>form</body></html>';

    _FakeAdapter extAdapter() => _FakeAdapter({
          ..._routes(),
          '/forms/assignment/5': (status: 200, body: extHtml),
          '/css2': (
            status: 200,
            body: '@font-face{src:url(https://fonts.gstatic.com/s/inter/v1/a.woff2)}'
          ),
          '/s/inter/v1/a.woff2': (status: 200, body: 'FONT'),
          '/lib/chart.min.js': (status: 200, body: 'chart();'),
        });

    test('mirrors CDN libraries and web fonts and rewrites references',
        () async {
      final a = extAdapter();
      final s = build(a);
      await download(s, 5);
      final dir = Directory(await s.offlineBundleDirectoryPath(5));

      final html = (await s.readOfflineIndexHtml(5))!;
      expect(html, isNot(contains('https://cdn.example.com')));
      expect(html, isNot(contains('https://fonts.googleapis.com')));
      expect(html, contains('static/ext/cdn.example.com/lib/chart.min.js'));

      final chart = File(p.join(dir.path, 'static/ext/cdn.example.com/lib/chart.min.js'));
      expect(chart.existsSync(), isTrue);

      final fontCss = Directory(p.join(dir.path, 'static/ext/fonts.googleapis.com'))
          .listSync()
          .whereType<File>()
          .single;
      expect(fontCss.path, endsWith('.css'));
      final css = fontCss.readAsStringSync();
      expect(css, isNot(contains('https://')));
      expect(
        File(p.normalize(p.join(
          fontCss.parent.path,
          RegExp(r'url\(([^)]+)\)').firstMatch(css)!.group(1)!,
        ))).existsSync(),
        isTrue,
      );
      expect(a.requested, isNot(contains('/gtag/js')));
    });

    test('never sends the session cookie to third-party hosts', () async {
      final a = extAdapter();
      final s = build(a);
      await s.downloadAndSave(
        assignmentId: 5,
        formPath: '/forms/assignment/5',
        language: 'en',
        sessionCookieHeader: 'session=secret',
        templateId: 7,
      );
      expect(a.headersByHost['cdn.example.com']?['Cookie'], isNull);
      expect(a.headersByHost['fonts.googleapis.com']?['Cookie'], isNull);
      expect(a.headersByHost['databank.ifrc.org']?['Cookie'], 'session=secret');
    });

    test('a failing CDN file does not block the download', () async {
      final a = _FakeAdapter({
        ..._routes(),
        '/forms/assignment/5': (status: 200, body: extHtml),
      });
      final s = build(a);
      await download(s, 5);
      expect(await s.hasOfflineBundle(5), isTrue);
      expect((await s.readBundleMeta(5))!.missingAssetCount, greaterThan(0));
    });
  });

  group('downloadAndSave', () {
    test('saves page, assets, metadata and recorded API data', () async {
      await download(
        svc,
        5,
        record: (_) async => [
          {
            'k': 'GET /api/forms/lookup-lists/country_map/options',
            's': 200,
            't': 'application/json',
            'b': '{"options":[1,2]}',
          },
        ],
      );

      expect(await svc.hasOfflineBundle(5), isTrue);
      final html = (await svc.readOfflineIndexHtml(5))!;
      expect(html, contains('offline_api_cache.js'));
      expect(html, contains('Submit online only'));

      final meta = (await svc.readBundleMeta(5))!;
      expect(meta.templateId, 7);
      expect(meta.staticVersion, 'v1');
      expect(meta.dataVersion, '2026-01-01T00:00:00+00:00');
      expect(meta.language, 'en');
      expect(meta.apiEntryCount, 1);
      expect(meta.assetCount, 2);
      expect(meta.missingAssetCount, 0);

      final dir = Directory(await svc.offlineBundleDirectoryPath(5));
      final script =
          await File(p.join(dir.path, 'offline_api_cache.js')).readAsString();
      expect(script, startsWith('window.__IFRC_OFFLINE_API__='));
      expect(script, contains('/api/forms/lookup-lists/country_map/options'));
    });

    test('a failed API recording does not fail the download', () async {
      await download(svc, 5, record: (_) async => throw StateError('boom'));
      expect(await svc.hasOfflineBundle(5), isTrue);
      expect((await svc.readBundleMeta(5))!.apiEntryCount, 0);
    });

    test('reuses static files from a sibling copy of the same template',
        () async {
      await download(svc, 5);
      adapter.requested.clear();

      await download(svc, 6);

      expect(adapter.requested, ['/forms/assignment/6']);
      final dir = Directory(await svc.offlineBundleDirectoryPath(6));
      expect(File(p.join(dir.path, 'static/js/app.js')).existsSync(), isTrue);
    });

    test('downloads static files again when the static release changed',
        () async {
      await download(svc, 5);
      adapter.requested.clear();

      await download(svc, 6, staticVersion: 'v2');

      expect(adapter.requested, contains('/static/js/app.js'));
      expect(adapter.requested, contains('/static/css/app.css'));
    });

    test('refreshing reuses the assignment\'s own static files', () async {
      await download(svc, 5);
      adapter.requested.clear();

      await download(svc, 5, dataVersion: '2026-02-01T00:00:00+00:00');

      expect(adapter.requested, ['/forms/assignment/5']);
      expect((await svc.readBundleMeta(5))!.dataVersion,
          '2026-02-01T00:00:00+00:00');
    });

    test('an incomplete refresh keeps the previous working copy', () async {
      await download(svc, 5);
      final before = (await svc.readBundleMeta(5))!;

      final broken = build(_FakeAdapter(_routes(cssOk: false)));
      await expectLater(
        download(broken, 5, staticVersion: 'v2'),
        throwsA(isA<AssignmentOfflineBundleException>()),
      );

      expect(await svc.hasOfflineBundle(5), isTrue);
      expect((await svc.readBundleMeta(5))!.staticVersion, before.staticVersion);
      expect(
        Directory(p.join(tmp.path, 'user_1', 'tmp_assignment_5')).existsSync(),
        isFalse,
      );
    });
  });

  group('template packages', () {
    test('lists templates and deletes every copy of one', () async {
      await download(svc, 5, templateId: 7);
      await download(svc, 6, templateId: 8);

      expect(await svc.templateIdsWithBundles(), {7, 8});

      await svc.deleteBundlesForTemplate(7, alsoAssignmentId: 5);
      expect(await svc.hasOfflineBundle(5), isFalse);
      expect(await svc.hasOfflineBundle(6), isTrue);
      expect(await svc.templateIdsWithBundles(), {8});
    });

    test('backfills a template id on a copy saved without one', () async {
      await download(svc, 5, templateId: null);
      expect((await svc.readBundleMeta(5))!.templateId, isNull);

      await svc.backfillTemplateId(5, 7);

      expect((await svc.readBundleMeta(5))!.templateId, 7);
    });
  });

  group('API cache', () {
    test('merges recorded responses into an existing copy', () async {
      await download(svc, 5);

      final ok = await svc.mergeApiCache(5, [
        {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{"a":1}'},
        {'k': 'GET /b', 's': 200, 't': 'application/json', 'b': '{"b":1}'},
      ]);
      await svc.mergeApiCache(5, [
        {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{"a":2}'},
      ]);

      expect(ok, isTrue);
      expect((await svc.readBundleMeta(5))!.apiEntryCount, 2);
      final dir = Directory(await svc.offlineBundleDirectoryPath(5));
      final cache = jsonDecode(
        await File(p.join(dir.path, 'offline_api_cache.json')).readAsString(),
      ) as Map;
      expect(cache['GET /a']['b'], '{"a":2}');
    });

    test('ignores responses for assignments without a saved copy', () async {
      expect(
        await svc.mergeApiCache(99, [
          {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{}'},
        ]),
        isFalse,
      );
    });
  });

  group('housekeeping', () {
    test('copies are separated per user and legacy folders are removed',
        () async {
      Directory(p.join(tmp.path, 'assignment_1')).createSync(recursive: true);
      await download(svc, 5);
      expect(Directory(p.join(tmp.path, 'assignment_1')).existsSync(), isFalse);

      final other = build(adapter, scope: 'user_2');
      expect(await other.hasOfflineBundle(5), isFalse);
      expect(Directory(p.join(tmp.path, 'user_1')).existsSync(), isFalse);
    });

    test('clearAll removes every saved copy', () async {
      await download(svc, 5);
      await svc.clearAll();
      expect(await svc.hasOfflineBundle(5), isFalse);
    });

    test('prunes old, closed and surplus copies', () async {
      await download(svc, 5);
      await download(svc, 6);

      final future = DateTime.now().add(const Duration(days: 90));
      expect(await svc.pruneBundles(now: future), 2);

      await download(svc, 5);
      await download(svc, 6);
      expect(await svc.pruneBundles(closedAssignmentIds: {5}), 1);
      expect(await svc.hasOfflineBundle(5), isFalse);
      expect(await svc.hasOfflineBundle(6), isTrue);

      await download(svc, 5);
      expect(await svc.pruneBundles(maxBundles: 1), 1);
    });
  });

  group('isAssignmentOfflineBundleStale', () {
    final base = Assignment(
      id: 5,
      name: 'x',
      status: 'pending',
      completionRate: 0,
      formDefinitionUpdatedAt: DateTime.utc(2026, 1, 1),
      staticVersion: 'v1',
      dataVersion: '2026-01-01T00:00:00+00:00',
    );
    const fresh = AssignmentOfflineBundleMeta(
      assignmentId: 5,
      assetCount: 1,
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
      staticVersion: 'v1',
      dataVersion: '2026-01-01T00:00:00+00:00',
      language: 'en',
    );

    bool stale(Assignment a, AssignmentOfflineBundleMeta? m, {String? lang}) =>
        isAssignmentOfflineBundleStale(a, m, language: lang);

    test('is current when everything matches', () {
      expect(stale(base, fresh, lang: 'en'), isFalse);
    });

    test('detects a newer form definition', () {
      final a = Assignment(
        id: 5,
        name: 'x',
        status: 'p',
        completionRate: 0,
        formDefinitionUpdatedAt: DateTime.utc(2026, 3, 1),
        staticVersion: 'v1',
        dataVersion: '2026-01-01T00:00:00+00:00',
      );
      expect(stale(a, fresh), isTrue);
    });

    test('detects a new static release', () {
      final a = Assignment(
        id: 5,
        name: 'x',
        status: 'p',
        completionRate: 0,
        formDefinitionUpdatedAt: DateTime.utc(2026, 1, 1),
        staticVersion: 'v2',
        dataVersion: '2026-01-01T00:00:00+00:00',
      );
      expect(stale(a, fresh), isTrue);
    });

    test('detects changed assignment data', () {
      final a = Assignment(
        id: 5,
        name: 'x',
        status: 'p',
        completionRate: 0,
        formDefinitionUpdatedAt: DateTime.utc(2026, 1, 1),
        staticVersion: 'v1',
        dataVersion: '2026-01-05T00:00:00+00:00',
      );
      expect(stale(a, fresh), isTrue);
    });

    test('detects a different language', () {
      expect(stale(base, fresh, lang: 'fr'), isTrue);
    });

    test('copies from older builds without versions are stale', () {
      const legacy = AssignmentOfflineBundleMeta(
        assignmentId: 5,
        assetCount: 1,
        formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
      );
      expect(stale(base, legacy), isTrue);
    });

    test('is never stale against an older server that reports no versions',
        () {
      final a = Assignment(
        id: 5,
        name: 'x',
        status: 'p',
        completionRate: 0,
      );
      expect(stale(a, fresh, lang: 'en'), isFalse);
    });
  });
}
