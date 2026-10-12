import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/services/assignment_offline_bundle_service.dart';
import 'package:hum_databank_app/services/client_diagnostics_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers/offline_test_support.dart';

void main() {
  late Directory tmp;
  late FakeAdapter adapter;
  late AssignmentOfflineBundleService svc;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  AssignmentOfflineBundleService build(
    FakeAdapter a, {
    String scope = 'user_1',
  }) {
    final dio = Dio(BaseOptions(validateStatus: (c) => c != null && c < 500))
      ..httpClientAdapter = a;
    return AssignmentOfflineBundleService.forTesting(
      dio: dio,
      baseDir: tmp,
      scope: scope,
    );
  }

  OfflineFormRequest req(
    int id, {
    int? templateId = 7,
    String? staticVersion = 'v1',
    String? dataVersion = '2026-01-01T00:00:00+00:00',
    String language = 'en',
    String? title,
    String? cookie,
    Future<List<Map<String, dynamic>>> Function(String)? record,
  }) => OfflineFormRequest(
    assignmentId: id,
    formPath: '/forms/assignment/$id',
    language: language,
    templateId: templateId,
    staticVersion: staticVersion,
    dataVersion: dataVersion,
    title: title,
    sessionCookieHeader: cookie,
    formDefinitionUpdatedAtIso: '2026-01-01T00:00:00+00:00',
    submitBlockedMessage: 'Submit online only',
    recordApiResponses: record,
  );

  Future<void> savePackage(
    AssignmentOfflineBundleService s,
    int id, {
    int? templateId = 7,
    String? staticVersion = 'v1',
    String? dataVersion = '2026-01-01T00:00:00+00:00',
    String language = 'en',
    String? title,
    String? cookie,
    Future<List<Map<String, dynamic>>> Function(String)? record,
  }) => s.savePackageAndPage(
    req(
      id,
      templateId: templateId,
      staticVersion: staticVersion,
      dataVersion: dataVersion,
      language: language,
      title: title,
      cookie: cookie,
      record: record,
    ),
  );

  Future<String> pageHtml(AssignmentOfflineBundleService s, int id) async =>
      File((await s.offlinePagePath(id))!).readAsString();

  Directory pkgDir([int template = 7]) =>
      Directory(p.join(tmp.path, 'user_1', 'template_$template'));

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('offline_bundle_test');
    adapter = FakeAdapter(routes());
    svc = build(adapter);
  });

  tearDown(() async {
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  group('template package + assignment pages', () {
    test('saves the shared files once and a page per assignment', () async {
      await savePackage(svc, 5, title: 'Annual report · 2026');

      expect(
        File(p.join(pkgDir().path, 'static/js/app.js')).existsSync(),
        isTrue,
      );
      expect(
        File(p.join(pkgDir().path, 'static/css/app.css')).existsSync(),
        isTrue,
      );
      expect(File(p.join(pkgDir().path, 'page_5.html')).existsSync(), isTrue);
      expect(await svc.hasOfflineForm(5), isTrue);

      final index = await svc.readIndex();
      expect(index.templateIds, {7});
      expect(index.packages['template_7']!.title, 'Annual report · 2026');
      expect(index.packages['template_7']!.assetCount, 2);
      expect(index.pages[5]!.packageKey, 'template_7');
    });

    test(
      'another entity of the same template downloads only its page',
      () async {
        await savePackage(svc, 5);
        adapter.requested.clear();

        await svc.savePage(req(6));

        expect(adapter.requested, ['/forms/assignment/6']);
        expect(await svc.hasOfflineForm(6), isTrue);
        expect(File(p.join(pkgDir().path, 'page_6.html')).existsSync(), isTrue);
        expect(await pageHtml(svc, 6), contains('static/js/app.js'));
      },
    );

    test('a page references the shared files relatively', () async {
      await savePackage(svc, 5);
      final page = await pageHtml(svc, 5);
      expect(page, contains('href="static/css/app.css"'));
      expect(page, contains('src="static/js/app.js"'));
      expect(page, contains('offline_api_cache.js'));
      expect(page, contains('Submit online only'));
    });

    test(
      'a page for a new assignment fetches only files the package lacks',
      () async {
        await savePackage(svc, 5);
        final extra = FakeAdapter({
          ...routes(),
          '/forms/assignment/6': (
            status: 200,
            body:
                '<html><head>'
                '<link rel="stylesheet" href="/static/css/app.css?v=1">'
                '<link rel="stylesheet" href="/static/css/extra.css">'
                '<script src="/static/js/app.js?v=1"></script>'
                '</head><body></body></html>',
          ),
          '/static/css/extra.css': (status: 200, body: '.x{}'),
        });
        final s = build(extra);

        await s.savePage(req(6));

        expect(
          extra.requested,
          unorderedEquals(['/forms/assignment/6', '/static/css/extra.css']),
        );
        expect(
          File(p.join(pkgDir().path, 'static/css/extra.css')).existsSync(),
          isTrue,
        );
        expect((await s.readIndex()).packages['template_7']!.assetCount, 3);
      },
    );

    test('saving a page needs the template package', () async {
      await expectLater(
        svc.savePage(req(6)),
        throwsA(isA<AssignmentOfflineBundleException>()),
      );
      expect(await svc.hasOfflineForm(6), isFalse);
    });

    test('saving a page refuses an out-of-date package', () async {
      await savePackage(svc, 5);
      await expectLater(
        svc.savePage(req(6, staticVersion: 'v2')),
        throwsA(isA<AssignmentOfflineBundleException>()),
      );
    });

    test(
      'a new static release downloads the package again and keeps pages',
      () async {
        await savePackage(svc, 5);
        await svc.savePage(req(6));
        adapter.requested.clear();

        await savePackage(svc, 5, staticVersion: 'v2');

        expect(adapter.requested, contains('/static/js/app.js'));
        expect(adapter.requested, contains('/static/css/app.css'));
        final index = await svc.readIndex();
        expect(index.packages['template_7']!.staticVersion, 'v2');
        expect(index.pages[5]!.staticVersion, 'v2');
        expect(index.pages[6]!.staticVersion, 'v1');
        expect(await svc.hasOfflineForm(6), isTrue);
      },
    );

    test('an incomplete refresh keeps the previous working copy', () async {
      await savePackage(svc, 5);

      final broken = build(FakeAdapter(routes(cssOk: false)));
      await expectLater(
        savePackage(broken, 5, staticVersion: 'v2'),
        throwsA(isA<AssignmentOfflineBundleException>()),
      );

      final index = await svc.readIndex();
      expect(index.packages['template_7']!.staticVersion, 'v1');
      expect(await svc.hasOfflineForm(5), isTrue);
      expect(
        Directory(p.join(tmp.path, 'user_1', 'tmp_template_7')).existsSync(),
        isFalse,
      );
    });

    test('templates without an id get their own package', () async {
      await savePackage(svc, 5, templateId: null);
      expect(
        Directory(p.join(tmp.path, 'user_1', 'solo_5')).existsSync(),
        isTrue,
      );
      expect((await svc.readIndex()).pages[5]!.packageKey, 'solo_5');
    });

    test('records metadata and the API data the form loads', () async {
      await savePackage(
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

      final index = await svc.readIndex();
      final page = index.pages[5]!;
      expect(page.templateId, 7);
      expect(page.dataVersion, '2026-01-01T00:00:00+00:00');
      expect(page.language, 'en');
      expect(index.packages['template_7']!.apiEntryCount, 1);
      final script = await File(
        p.join(pkgDir().path, 'offline_api_cache.js'),
      ).readAsString();
      expect(script, startsWith('window.__IFRC_OFFLINE_API__='));
      expect(script, contains('/api/forms/lookup-lists/country_map/options'));
    });

    test('a failed API recording does not fail the save', () async {
      await savePackage(svc, 5, record: (_) async => throw StateError('boom'));
      expect(await svc.hasOfflineForm(5), isTrue);
      expect((await svc.readIndex()).packages['template_7']!.apiEntryCount, 0);
    });

    test('rebuilding the package keeps API data recorded earlier', () async {
      await savePackage(svc, 5);
      await svc.mergeApiCache(5, [
        {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{"a":1}'},
      ]);
      await savePackage(svc, 5, staticVersion: 'v2');
      final cache =
          jsonDecode(
                await File(
                  p.join(pkgDir().path, 'offline_api_cache.json'),
                ).readAsString(),
              )
              as Map;
      expect(cache.keys, contains('GET /a'));
    });

    test('many assets are downloaded in parallel and all arrive', () async {
      final links = [
        for (var i = 0; i < 60; i++)
          '<link rel="stylesheet" href="/static/css/c$i.css">',
      ].join();
      final a = FakeAdapter({
        '/forms/assignment/5': (
          status: 200,
          body: '<html><head>$links</head></html>',
        ),
        for (var i = 0; i < 60; i++)
          '/static/css/c$i.css': (status: 200, body: '.c$i{}'),
      });
      final s = build(a);
      await savePackage(s, 5);
      expect((await s.readIndex()).packages['template_7']!.assetCount, 60);
      expect(a.requested.toSet().length, 61);
    });
  });

  group('plugin fields', () {
    const pluginHtml =
        '<html><head>'
        '<script type="module" src="/static/js/forms/main.js?v=1"></script>'
        '</head><body>'
        "<div class=\"plugin-field-container\" data-entry-form-config='"
        '{&#34;es_module_path&#34;: &#34;/plugins/static/eo/js/field.js&#34;, '
        '&#34;css_files&#34;: [&#34;/plugins/static/eo/css/field.css&#34;]}'
        "'></div>"
        '<script type="module">import { X } from "/plugins/static/eo/js/inline.js";</script>'
        '<link rel="stylesheet" href="/plugins/static/eo/css/field.css">'
        '</body></html>';

    FakeAdapter pluginAdapter() => FakeAdapter({
      '/forms/assignment/5': (status: 200, body: pluginHtml),
      '/static/js/forms/main.js': (status: 200, body: 'export const a=1;'),
      '/plugins/static/eo/js/field.js': (
        status: 200,
        body:
            "import { log } from '/static/js/forms/modules/debug.js';\n"
            "import { h } from './helper.js';\n"
            "const mod = await import('/plugins/static/eo/js/lazy.js');\n"
            "script.src = '/static/vendor/leaflet/leaflet.js';\n",
      ),
      '/plugins/static/eo/js/helper.js': (
        status: 200,
        body: 'export const h=1;',
      ),
      '/plugins/static/eo/js/lazy.js': (status: 200, body: 'export const l=1;'),
      '/plugins/static/eo/js/inline.js': (
        status: 200,
        body: 'export const X=1;',
      ),
      '/plugins/static/eo/css/field.css': (status: 200, body: '.eo{color:red}'),
      '/static/js/forms/modules/debug.js': (
        status: 200,
        body: 'export const log=1;',
      ),
      '/static/vendor/leaflet/leaflet.js': (status: 200, body: 'L={};'),
    });

    test('mirrors plugin modules, styles and their imports', () async {
      await savePackage(build(pluginAdapter()), 5);
      for (final f in [
        'plugins/static/eo/js/field.js',
        'plugins/static/eo/js/helper.js',
        'plugins/static/eo/js/lazy.js',
        'plugins/static/eo/js/inline.js',
        'plugins/static/eo/css/field.css',
        'static/js/forms/modules/debug.js',
        'static/vendor/leaflet/leaflet.js',
      ]) {
        expect(File(p.join(pkgDir().path, f)).existsSync(), isTrue, reason: f);
      }
    });

    test(
      'makes root-absolute paths inside plugin scripts work from disk',
      () async {
        await savePackage(build(pluginAdapter()), 5);
        final js = File(
          p.join(pkgDir().path, 'plugins/static/eo/js/field.js'),
        ).readAsStringSync();
        expect(
          js,
          contains("from '../../../../static/js/forms/modules/debug.js'"),
        );
        expect(js, contains("import('./lazy.js')"));
        expect(js, contains("script.src = 'static/vendor/leaflet/leaflet.js'"));
        expect(js, isNot(contains("'/static/")));
      },
    );

    test('points the page at saved plugin files', () async {
      final s = build(pluginAdapter());
      await savePackage(s, 5);
      final page = await pageHtml(s, 5);
      expect(page, contains('href="plugins/static/eo/css/field.css"'));
      expect(page, contains('from "./plugins/static/eo/js/inline.js"'));
      expect(page, contains('data-entry-form-config'));
      expect(page, contains("var P = '/plugins/static/'"));
      expect(
        page.lastIndexOf('var P = ') <
            page.toLowerCase().lastIndexOf('</body>'),
        isTrue,
      );
    });
  });

  group('best-effort assets', () {
    test(
      'a file only mentioned in inline script text cannot fail the save',
      () async {
        final a = FakeAdapter({
          ...routes(),
          '/forms/assignment/5': (
            status: 200,
            body:
                '<html><head>'
                '<link rel="stylesheet" href="/static/css/app.css?v=1">'
                '<script src="/static/js/app.js?v=1"></script>'
                "<script>var x = '/static/js/ghost.js';</script>"
                '</head><body></body></html>',
          ),
        });
        final s = build(a);
        await savePackage(s, 5);
        expect(await s.hasOfflineForm(5), isTrue);
        expect(
          (await s.readIndex()).packages['template_7']!.missingAssetCount,
          1,
        );
      },
    );

    test('a missing plugin file cannot fail the save', () async {
      final a = FakeAdapter({
        ...routes(),
        '/forms/assignment/5': (
          status: 200,
          body:
              '<html><head>'
              '<link rel="stylesheet" href="/static/css/app.css?v=1">'
              '<script src="/static/js/app.js?v=1"></script>'
              '<link rel="stylesheet" href="/plugins/static/eo/css/gone.css">'
              '</head><body></body></html>',
        ),
      });
      final s = build(a);
      await savePackage(s, 5);
      expect(await s.hasOfflineForm(5), isTrue);
    });

    test('a missing script the page loads still fails the save', () async {
      final a = FakeAdapter({
        ...routes(),
        '/static/js/app.js': (status: 404, body: ''),
      });
      final s = build(a);
      await expectLater(
        savePackage(s, 5),
        throwsA(isA<AssignmentOfflineBundleException>()),
      );
      expect(await s.hasOfflineForm(5), isFalse);
    });

    test('keeps a trace and exception details to report a failure', () async {
      final a = FakeAdapter({
        ...routes(),
        '/static/js/app.js': (status: 404, body: ''),
      });
      final s = build(a);
      Object? error;
      try {
        await savePackage(s, 5);
      } catch (e) {
        error = e;
      }
      final trace = s.traceFor(5).join('\n');
      expect(
        trace,
        contains('page databank.ifrc.org/forms/assignment/5 HTTP 200'),
      );
      expect(
        trace,
        contains(
          'missing databank.ifrc.org/static/js/app.js HTTP 404 CRITICAL',
        ),
      );
      expect(trace, contains('build failed'));

      final info = ClientDiagnosticsService.describe(error!);
      expect(info.type, 'AssignmentOfflineBundleException');
      expect(info.details['critical_missing'], [
        'databank.ifrc.org/static/js/app.js',
      ]);
    });

    test('describes network errors with status and request', () {
      final err = DioException(
        requestOptions: RequestOptions(
          path: 'https://h.org/forms/assignment/5',
          method: 'GET',
        ),
        type: DioExceptionType.connectionTimeout,
        message: 'timed out',
      );
      final info = ClientDiagnosticsService.describe(err);
      expect(info.type, 'DioException/connectionTimeout');
      expect(info.details['request'], 'GET h.org/forms/assignment/5');
    });
  });

  group('third-party files', () {
    const extHtml =
        '<html><head>'
        '<link rel="stylesheet" href="/static/css/app.css?v=1">'
        '<link rel="stylesheet" '
        'href="https://fonts.googleapis.com/css2?family=Inter:wght@400&amp;display=swap">'
        '<script src="https://cdn.example.com/lib/chart.min.js"></script>'
        '<script src="https://www.googletagmanager.com/gtag/js?id=X"></script>'
        '<link rel="preconnect" href="https://fonts.gstatic.com">'
        '</head><body>form</body></html>';

    FakeAdapter extAdapter() => FakeAdapter({
      ...routes(),
      '/forms/assignment/5': (status: 200, body: extHtml),
      '/css2': (
        status: 200,
        body:
            '@font-face{src:url(https://fonts.gstatic.com/s/inter/v1/a.woff2)}',
      ),
      '/s/inter/v1/a.woff2': (status: 200, body: 'FONT'),
      '/lib/chart.min.js': (status: 200, body: 'chart();'),
    });

    test(
      'mirrors CDN libraries and web fonts and rewrites references',
      () async {
        final a = extAdapter();
        final s = build(a);
        await savePackage(s, 5);

        final page = await pageHtml(s, 5);
        expect(page, isNot(contains('https://cdn.example.com')));
        expect(page, isNot(contains('https://fonts.googleapis.com')));
        expect(page, contains('static/ext/cdn.example.com/lib/chart.min.js'));

        expect(
          File(
            p.join(
              pkgDir().path,
              'static/ext/cdn.example.com/lib/chart.min.js',
            ),
          ).existsSync(),
          isTrue,
        );
        final fontCss = Directory(
          p.join(pkgDir().path, 'static/ext/fonts.googleapis.com'),
        ).listSync().whereType<File>().single;
        expect(fontCss.path, endsWith('.css'));
        final css = fontCss.readAsStringSync();
        expect(css, isNot(contains('https://')));
        expect(
          File(
            p.normalize(
              p.join(
                fontCss.parent.path,
                RegExp(r'url\(([^)]+)\)').firstMatch(css)!.group(1)!,
              ),
            ),
          ).existsSync(),
          isTrue,
        );
        expect(a.requested, isNot(contains('/gtag/js')));
      },
    );

    test('never sends the session cookie to third-party hosts', () async {
      final a = extAdapter();
      await savePackage(build(a), 5, cookie: 'session=secret');
      expect(a.headersByHost['cdn.example.com']?['Cookie'], isNull);
      expect(a.headersByHost['fonts.googleapis.com']?['Cookie'], isNull);
      expect(a.headersByHost['databank.ifrc.org']?['Cookie'], 'session=secret');
    });

    test('a failing CDN file does not block the save', () async {
      final a = FakeAdapter({
        ...routes(),
        '/forms/assignment/5': (status: 200, body: extHtml),
      });
      final s = build(a);
      await savePackage(s, 5);
      expect(await s.hasOfflineForm(5), isTrue);
      expect(
        (await s.readIndex()).packages['template_7']!.missingAssetCount,
        greaterThan(0),
      );
    });
  });

  group('API cache', () {
    test(
      'responses seen on one assignment serve every assignment of the template',
      () async {
        await savePackage(svc, 5);
        await svc.savePage(req(6));

        final ok = await svc.mergeApiCache(6, [
          {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{"a":1}'},
          {'k': 'GET /b', 's': 200, 't': 'application/json', 'b': '{"b":1}'},
        ]);
        await svc.mergeApiCache(5, [
          {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{"a":2}'},
        ]);

        expect(ok, isTrue);
        expect(
          (await svc.readIndex()).packages['template_7']!.apiEntryCount,
          2,
        );
        final cache =
            jsonDecode(
                  await File(
                    p.join(pkgDir().path, 'offline_api_cache.json'),
                  ).readAsString(),
                )
                as Map;
        expect(cache['GET /a']['b'], '{"a":2}');
        expect(cache['GET /b']['b'], '{"b":1}');
      },
    );

    test('ignores responses for assignments without a saved page', () async {
      expect(
        await svc.mergeApiCache(99, [
          {'k': 'GET /a', 's': 200, 't': 'application/json', 'b': '{}'},
        ]),
        isFalse,
      );
    });
  });

  group('storage', () {
    test(
      'lists templates with size and assignments, and removes them',
      () async {
        await savePackage(svc, 5, title: 'Annual report');
        await svc.savePage(req(6));

        final packages = await svc.listPackages();
        expect(packages, hasLength(1));
        expect(packages.single.templateId, 7);
        expect(packages.single.title, 'Annual report');
        expect(packages.single.assignmentIds, [5, 6]);
        expect(packages.single.sizeBytes, greaterThan(0));

        final before = AssignmentOfflineBundleService.savedCopiesChanged.value;
        await svc.removePackage(packages.single);
        expect(
          AssignmentOfflineBundleService.savedCopiesChanged.value,
          greaterThan(before),
        );
        expect(await svc.listPackages(), isEmpty);
        expect(await svc.hasOfflineForm(6), isFalse);
      },
    );

    test('removing for an assignment removes its whole template', () async {
      await savePackage(svc, 5, templateId: 7);
      await savePackage(svc, 6, templateId: 8);

      await svc.removeForAssignment(assignmentId: 5, templateId: 7);

      expect((await svc.readIndex()).templateIds, {8});
    });

    test('auto-download preference persists and notifies', () async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      expect(await svc.isAutoDownloadEnabled(), isFalse);
      final before = AssignmentOfflineBundleService.autoDownloadChanged.value;
      await svc.setAutoDownloadEnabled(true);
      expect(await svc.isAutoDownloadEnabled(), isTrue);
      expect(
        AssignmentOfflineBundleService.autoDownloadChanged.value,
        greaterThan(before),
      );
    });
  });

  group('housekeeping', () {
    test(
      'copies are separated per user and legacy folders are removed',
      () async {
        Directory(p.join(tmp.path, 'assignment_1')).createSync(recursive: true);
        Directory(
          p.join(tmp.path, 'user_1', 'assignment_3'),
        ).createSync(recursive: true);
        await savePackage(svc, 5);
        expect(
          Directory(p.join(tmp.path, 'assignment_1')).existsSync(),
          isFalse,
        );
        expect(
          Directory(p.join(tmp.path, 'user_1', 'assignment_3')).existsSync(),
          isFalse,
        );

        final other = build(adapter, scope: 'user_2');
        expect(await other.hasOfflineForm(5), isFalse);
        expect(Directory(p.join(tmp.path, 'user_1')).existsSync(), isFalse);
      },
    );

    test('packages from another layout version are discarded', () async {
      final old = Directory(p.join(tmp.path, 'user_1', 'template_9'))
        ..createSync(recursive: true);
      File(p.join(old.path, 'package.json')).writeAsStringSync('{"layout":1}');
      expect((await svc.readIndex()).packages, isEmpty);
      expect(old.existsSync(), isFalse);
    });

    test('clearAll removes every saved form', () async {
      await savePackage(svc, 5);
      await svc.clearAll();
      expect(await svc.hasOfflineForm(5), isFalse);
    });

    test('a save that finishes after clearAll is discarded', () async {
      final slow = svc.savePackageAndPage(
        req(
          5,
          record: (_) async {
            await svc.clearAll();
            return const [];
          },
        ),
      );
      await expectLater(slow, throwsA(isA<AssignmentOfflineBundleException>()));
      expect(await svc.hasOfflineForm(5), isFalse);
    });

    test('prunes closed assignments, old pages and surplus pages', () async {
      await savePackage(svc, 5);
      await svc.savePage(req(6));

      expect(await svc.pruneBundles(closedAssignmentIds: {5}), 1);
      expect(await svc.hasOfflineForm(5), isFalse);
      expect(await svc.hasOfflineForm(6), isTrue);

      final future = DateTime.now().add(const Duration(days: 91));
      expect(await svc.pruneBundles(now: future), greaterThanOrEqualTo(1));
      expect(await svc.listPackages(), isEmpty);

      await savePackage(svc, 5);
      await svc.savePage(req(6));
      expect(await svc.pruneBundles(maxPages: 1), 1);
      expect((await svc.readIndex()).pages, hasLength(1));
    });
  });

  group('evaluateOfflineForm', () {
    Assignment assignment({
      DateTime? formDefinition,
      String? staticVersion = 'v1',
      String? dataVersion = '2026-01-01T00:00:00+00:00',
      int? templateId = 7,
    }) => Assignment(
      id: 5,
      name: 'x',
      status: 'pending',
      completionRate: 0,
      templateId: templateId,
      formDefinitionUpdatedAt: formDefinition ?? DateTime.utc(2026, 1, 1),
      staticVersion: staticVersion,
      dataVersion: dataVersion,
    );

    const package = OfflinePackageMeta(
      key: 'template_7',
      templateId: 7,
      staticVersion: 'v1',
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
    );
    const page = OfflinePageMeta(
      assignmentId: 5,
      packageKey: 'template_7',
      templateId: 7,
      staticVersion: 'v1',
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
      dataVersion: '2026-01-01T00:00:00+00:00',
      language: 'en',
    );
    const index = OfflineFormsIndex(
      packages: {'template_7': package},
      pages: {5: page},
    );

    OfflineFormStatus status(
      Assignment a, {
      OfflineFormsIndex i = index,
      String? lang,
    }) => evaluateOfflineForm(a, i, language: lang);

    test('nothing saved', () {
      final s = status(assignment(), i: OfflineFormsIndex.empty);
      expect(s.available, isFalse);
      expect(s.hasPackage, isFalse);
      expect(s.needsPage, isFalse);
      expect(s.needsPackage, isFalse);
    });

    test('is current when everything matches', () {
      final s = status(assignment(), lang: 'en');
      expect(s.available, isTrue);
      expect(s.outdated, isFalse);
      expect(s.needsPage, isFalse);
    });

    test('a saved template makes other assignments need only a page', () {
      final other = Assignment(
        id: 6,
        name: 'y',
        status: 'pending',
        completionRate: 0,
        templateId: 7,
        formDefinitionUpdatedAt: DateTime.utc(2026, 1, 1),
        staticVersion: 'v1',
        dataVersion: '2026-01-02T00:00:00+00:00',
      );
      final s = status(other);
      expect(s.available, isFalse);
      expect(s.packageCurrent, isTrue);
      expect(s.needsPage, isTrue);
      expect(s.needsPackage, isFalse);
    });

    test('a new static release needs the package again', () {
      final s = status(assignment(staticVersion: 'v2'));
      expect(s.needsPackage, isTrue);
      expect(s.needsPage, isFalse);
      expect(s.outdated, isTrue);
      expect(s.available, isTrue);
    });

    test('changed assignment data needs only the page', () {
      final s = status(assignment(dataVersion: '2026-01-05T00:00:00+00:00'));
      expect(s.needsPage, isTrue);
      expect(s.needsPackage, isFalse);
      expect(s.outdated, isTrue);
    });

    test('a newer form definition needs only the page', () {
      final s = status(assignment(formDefinition: DateTime.utc(2026, 3, 1)));
      expect(s.needsPage, isTrue);
      expect(s.needsPackage, isFalse);
    });

    test('a different language needs only the page', () {
      expect(status(assignment(), lang: 'fr').needsPage, isTrue);
    });

    test('a page written against an older package is outdated', () {
      const old = OfflinePageMeta(
        assignmentId: 5,
        packageKey: 'template_7',
        staticVersion: 'v0',
        formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
        dataVersion: '2026-01-01T00:00:00+00:00',
      );
      final s = status(
        assignment(),
        i: const OfflineFormsIndex(
          packages: {'template_7': package},
          pages: {5: old},
        ),
      );
      expect(s.needsPage, isTrue);
    });

    test(
      'is never outdated against an older server that reports no versions',
      () {
        final a = Assignment(
          id: 5,
          name: 'x',
          status: 'p',
          completionRate: 0,
          templateId: 7,
        );
        final s = status(a, lang: 'en');
        expect(s.outdated, isFalse);
        expect(s.needsPackage, isFalse);
      },
    );

    test('assignments without a template use their own package', () {
      final s = status(
        assignment(templateId: null),
        i: const OfflineFormsIndex(packages: {'template_7': package}),
      );
      expect(s.hasPackage, isFalse);
    });
  });
}
