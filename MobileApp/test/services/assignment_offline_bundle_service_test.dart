import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/services/assignment_offline_bundle_service.dart';
import 'package:path/path.dart' as p;

class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.routes);

  final Map<String, ({int status, String body})> routes;
  final List<String> requested = [];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    requested.add(options.uri.path);
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
