import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/services/assignment_offline_bundle_service.dart';
import 'package:hum_databank_app/services/offline/offline_forms_controller.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../helpers/offline_test_support.dart';

Assignment assignment(
  int id, {
  int? templateId = 7,
  String staticVersion = 'v1',
  String dataVersion = '2026-01-01T00:00:00+00:00',
}) => Assignment(
  id: id,
  name: 'Form $id',
  status: 'pending',
  completionRate: 0,
  templateId: templateId,
  formDefinitionUpdatedAt: DateTime.utc(2026, 1, 1),
  staticVersion: staticVersion,
  dataVersion: dataVersion,
);

const env = OfflineFormsEnvironment(
  language: 'en',
  submitBlockedMessage: 'Submit online only',
  online: true,
);

void main() {
  late Directory tmp;
  late FakeAdapter adapter;
  late AssignmentOfflineBundleService service;
  late OfflineFormsController controller;
  var unmetered = true;

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  OfflineFormsController buildController({
    Duration? pageTimeout,
    Duration? packageTimeout,
  }) => OfflineFormsController.forTesting(
    service: service,
    isUnmetered: () async => unmetered,
    pageTimeout: pageTimeout,
    packageTimeout: packageTimeout,
  );

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    unmetered = true;
    tmp = await Directory.systemTemp.createTemp('offline_controller_test');
    adapter = FakeAdapter({
      ...routes(),
      '/forms/assignment/7': (status: 200, body: html),
    });
    service = AssignmentOfflineBundleService.forTesting(
      dio: Dio(BaseOptions(validateStatus: (c) => c != null && c < 500))
        ..httpClientAdapter = adapter,
      baseDir: tmp,
      scope: 'user_1',
    );
    controller = buildController();
  });

  tearDown(() async {
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  group('planOfflineJobs', () {
    final package = const OfflinePackageMeta(
      key: 'template_7',
      templateId: 7,
      staticVersion: 'v1',
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
    );
    final page5 = const OfflinePageMeta(
      assignmentId: 5,
      packageKey: 'template_7',
      staticVersion: 'v1',
      formDefinitionUpdatedAtIso: '2026-01-01T00:00:00.000Z',
      dataVersion: '2026-01-01T00:00:00+00:00',
      language: 'en',
    );
    final saved = OfflineFormsIndex(
      packages: {'template_7': package},
      pages: {5: page5},
    );

    List<OfflineJob> plan(
      List<Assignment> eligible,
      OfflineFormsIndex index, {
      bool auto = false,
      bool packages = true,
      bool Function(String)? skip,
    }) => planOfflineJobs(
      eligible: eligible,
      index: index,
      language: 'en',
      autoDownload: auto,
      allowPackageWork: packages,
      skip: skip,
    );

    test('another entity of a saved template only needs its page', () {
      final jobs = plan([assignment(5), assignment(6), assignment(8)], saved);
      expect(jobs.map((j) => j.kind), everyElement(OfflineJobKind.page));
      expect(jobs.map((j) => j.assignment.id), [6, 8]);
    });

    test('nothing is planned for a template that was never saved', () {
      expect(plan([assignment(6, templateId: 9)], saved), isEmpty);
    });

    test('auto-download plans one package per template', () {
      final jobs = plan(
        [assignment(6, templateId: 9), assignment(8, templateId: 9)],
        saved,
        auto: true,
      );
      expect(jobs, hasLength(1));
      expect(jobs.single.kind, OfflineJobKind.package);
      expect(jobs.single.assignment.id, 6);
    });

    test('an outdated package is rebuilt once and its pages wait for it', () {
      final jobs = plan([
        assignment(5, staticVersion: 'v2'),
        assignment(6, staticVersion: 'v2'),
      ], saved);
      expect(jobs, hasLength(1));
      expect(jobs.single.kind, OfflineJobKind.package);
    });

    test('package work is skipped when not allowed, pages still run', () {
      final jobs = plan(
        [assignment(5, staticVersion: 'v2')],
        saved,
        packages: false,
      );
      expect(jobs, isEmpty);
      expect(
        plan([assignment(6)], saved, packages: false).single.kind,
        OfflineJobKind.page,
      );
    });

    test('failed jobs are skipped', () {
      expect(plan([assignment(6)], saved, skip: (k) => k == 'page:6'), isEmpty);
    });

    test('the number of jobs per pass is bounded', () {
      final many = [for (var i = 100; i < 200; i++) assignment(i)];
      expect(plan(many, saved), hasLength(40));
    });
  });

  group('OfflineFormsController', () {
    test('switching to another entity downloads only its page', () async {
      await controller.save(assignment(5), env);
      expect(adapter.requested, contains('/static/js/app.js'));
      adapter.requested.clear();

      final all = [assignment(6), assignment(7)];
      final busy = <bool>[];
      controller.addListener(() => busy.add(controller.isBusy(6)));
      await controller.reconcile(all: all, eligible: all, env: env);
      await controller.idle;

      expect(
        adapter.requested,
        unorderedEquals(['/forms/assignment/6', '/forms/assignment/7']),
      );
      expect(controller.statusFor(6).available, isTrue);
      expect(controller.statusFor(7).available, isTrue);
      expect(busy, everyElement(isFalse));
      expect(await service.hasOfflineForm(6), isTrue);
    });

    test('a second reconcile does no more work', () async {
      await controller.save(assignment(5), env);
      final all = [assignment(6)];
      await controller.reconcile(all: all, eligible: all, env: env);
      await controller.idle;
      adapter.requested.clear();

      await controller.reconcile(all: all, eligible: all, env: env);
      await controller.idle;

      expect(adapter.requested, isEmpty);
    });

    test(
      'saving by hand downloads the template once, then only pages',
      () async {
        final first = await controller.save(assignment(5), env);
        expect(first.ok, isTrue);
        expect(adapter.requested, contains('/static/css/app.css'));
        adapter.requested.clear();

        final second = await controller.save(assignment(6), env);
        expect(second.ok, isTrue);
        expect(adapter.requested, ['/forms/assignment/6']);
      },
    );

    test('a saved copy is marked busy only while it is being saved', () async {
      final states = <bool>[];
      controller.addListener(() => states.add(controller.isBusy(5)));
      await controller.save(assignment(5), env);
      expect(states, contains(true));
      expect(controller.isBusy(5), isFalse);
    });

    test('a failing page is not retried until the backoff passes', () async {
      await controller.save(assignment(5), env);
      adapter.routes['/forms/assignment/6'] = (status: 404, body: '');
      adapter.requested.clear();
      final all = [assignment(6)];

      await controller.reconcile(all: all, eligible: all, env: env);
      await controller.idle;
      await controller.reconcile(all: all, eligible: all, env: env);
      await controller.idle;
      expect(
        adapter.requested.where((p) => p == '/forms/assignment/6'),
        hasLength(1),
      );
      expect(controller.statusFor(6).available, isFalse);

      adapter.routes['/forms/assignment/6'] = (status: 200, body: html);
      await controller.reconcile(
        all: all,
        eligible: all,
        env: env,
        clearFailures: true,
      );
      await controller.idle;
      expect(controller.statusFor(6).available, isTrue);
    });

    test(
      'an outdated template is rebuilt on Wi-Fi but not on mobile data',
      () async {
        await controller.save(assignment(5), env);
        final all = [assignment(5, staticVersion: 'v2')];
        adapter.requested.clear();

        unmetered = false;
        await controller.reconcile(all: all, eligible: all, env: env);
        await controller.idle;
        expect(adapter.requested, isEmpty);
        expect(controller.hasOutdatedPackages, isTrue);

        unmetered = true;
        await controller.reconcile(all: all, eligible: all, env: env);
        await controller.idle;
        expect(adapter.requested, contains('/static/js/app.js'));
        expect(controller.hasOutdatedPackages, isFalse);
      },
    );

    test(
      'a template that was never saved is only downloaded with auto-download',
      () async {
        final all = [assignment(5)];
        await controller.reconcile(all: all, eligible: all, env: env);
        await controller.idle;
        expect(adapter.requested, isEmpty);

        await service.setAutoDownloadEnabled(true);
        await controller.reconcile(all: all, eligible: all, env: env);
        await controller.idle;
        expect(controller.statusFor(5).available, isTrue);
      },
    );

    test('nothing runs while offline', () async {
      await controller.save(assignment(5), env);
      adapter.requested.clear();
      final all = [assignment(6)];
      await controller.reconcile(
        all: all,
        eligible: all,
        env: const OfflineFormsEnvironment(
          language: 'en',
          submitBlockedMessage: 'x',
          online: false,
        ),
      );
      await controller.idle;
      expect(adapter.requested, isEmpty);
    });

    test('a hanging request is abandoned after the time limit', () async {
      adapter.hang.add('/forms/assignment/5');
      final c = buildController(
        pageTimeout: const Duration(milliseconds: 300),
        packageTimeout: const Duration(milliseconds: 300),
      );
      final result = await c
          .save(assignment(5), env)
          .timeout(const Duration(seconds: 5));
      expect(result.ok, isFalse);
      expect(c.isBusy(5), isFalse);
    });

    test('removing a copy removes the whole template', () async {
      await controller.save(assignment(5), env);
      await controller.save(assignment(6), env);
      await controller.remove(assignment(5));
      expect(controller.statusFor(5).available, isFalse);
      expect(controller.statusFor(6).available, isFalse);
      expect(await service.listPackages(), isEmpty);
    });
  });
}
