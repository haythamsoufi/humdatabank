import 'dart:async';
import 'dart:collection';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../models/shared/assignment.dart';
import '../../utils/debug_logger.dart';
import '../assignment_offline_bundle_service.dart';
import '../client_diagnostics_service.dart';
import '../connectivity_service.dart';
import '../offline_api_recorder.dart';
import '../storage_service.dart';

enum OfflineJobKind {
  /// The template's shared files plus one page (large).
  package,

  /// One assignment's page only (a single small request).
  page,
}

class OfflineJob {
  const OfflineJob(this.kind, this.assignment);

  final OfflineJobKind kind;
  final Assignment assignment;

  String get packageKey => offlinePackageKey(
    templateId: assignment.templateId,
    assignmentId: assignment.id,
  );

  /// Identity used to avoid duplicates and to back off after failures.
  String get key => kind == OfflineJobKind.package
      ? 'package:$packageKey'
      : 'page:${assignment.id}';
}

/// Decides which saved forms need work, without touching disk or network.
///
/// * A page is refreshed whenever its template package is current but the
///   page is missing or outdated. This is one small request, so it runs on
///   every dashboard change and never needs the user to ask.
/// * A package (large) is only (re)built when [allowPackageWork] is set, and
///   then for a template that was saved before but is outdated, or for any
///   template when [autoDownload] is on. One job covers all assignments of a
///   template.
List<OfflineJob> planOfflineJobs({
  required Iterable<Assignment> eligible,
  required OfflineFormsIndex index,
  required String language,
  required bool autoDownload,
  required bool allowPackageWork,
  bool Function(String jobKey)? skip,
  int maxJobs = 40,
}) {
  final packageJobs = <String, OfflineJob>{};
  final pageJobs = <OfflineJob>[];
  for (final a in eligible) {
    final status = evaluateOfflineForm(a, index, language: language);
    final key = offlinePackageKey(templateId: a.templateId, assignmentId: a.id);
    if (!status.packageCurrent) {
      final wanted = status.hasPackage || autoDownload;
      if (allowPackageWork && wanted && !packageJobs.containsKey(key)) {
        final job = OfflineJob(OfflineJobKind.package, a);
        if (skip == null || !skip(job.key)) packageJobs[key] = job;
      }
      continue;
    }
    if (!status.pageCurrent) {
      final job = OfflineJob(OfflineJobKind.page, a);
      if (skip == null || !skip(job.key)) pageJobs.add(job);
    }
  }
  return [
    ...packageJobs.values,
    for (final j in pageJobs)
      if (!packageJobs.containsKey(j.packageKey)) j,
  ].take(maxJobs).toList();
}

/// What the dashboard knows about the current moment.
class OfflineFormsEnvironment {
  const OfflineFormsEnvironment({
    required this.language,
    required this.submitBlockedMessage,
    required this.online,
  });

  final String language;
  final String submitBlockedMessage;

  /// The device can reach the server right now.
  final bool online;
}

class OfflineSaveResult {
  const OfflineSaveResult.success() : error = null;
  const OfflineSaveResult.failure(Object this.error);

  final Object? error;
  bool get ok => error == null;
}

class _QueuedJob {
  _QueuedJob(this.job, this.env);

  final OfflineJob job;
  final OfflineFormsEnvironment env;
}

/// Keeps assignments' offline copies up to date and exposes their state.
///
/// Work runs in the background, one job at a time, and every step has a time
/// limit so a stuck request or WebView can never leave the dashboard waiting.
class OfflineFormsController extends ChangeNotifier {
  OfflineFormsController._({
    AssignmentOfflineBundleService? service,
    Future<String?> Function()? readSessionCookie,
    Future<List<Map<String, dynamic>>> Function(String url, String language)?
    recordApi,
    Future<bool> Function()? isUnmetered,
    Duration? pageTimeout,
    Duration? packageTimeout,
  }) : _service = service ?? AssignmentOfflineBundleService(),
       _readSessionCookie =
           readSessionCookie ??
           (() => sl<StorageService>().getSecure(AppConfig.sessionCookieKey)),
       _recordApi =
           recordApi ??
           ((url, language) => OfflineApiRecorder.recordFormLoad(
             formUrl: url,
             language: language,
           )),
       _isUnmetered =
           isUnmetered ?? (() => ConnectivityService().isOnUnmeteredNetwork()),
       _pageTimeout = pageTimeout ?? const Duration(seconds: 90),
       _packageTimeout = packageTimeout ?? const Duration(minutes: 8) {
    AssignmentOfflineBundleService.savedCopiesChanged.addListener(
      _onStorageChanged,
    );
  }

  factory OfflineFormsController() => _instance;
  static final OfflineFormsController _instance = OfflineFormsController._();

  @visibleForTesting
  factory OfflineFormsController.forTesting({
    required AssignmentOfflineBundleService service,
    Future<String?> Function()? readSessionCookie,
    Future<List<Map<String, dynamic>>> Function(String url, String language)?
    recordApi,
    Future<bool> Function()? isUnmetered,
    Duration? pageTimeout,
    Duration? packageTimeout,
  }) => OfflineFormsController._(
    service: service,
    readSessionCookie: readSessionCookie ?? () async => null,
    recordApi: recordApi ?? (_, _) async => const [],
    isUnmetered: isUnmetered ?? () async => true,
    pageTimeout: pageTimeout,
    packageTimeout: packageTimeout,
  );

  static const Duration _retryAfterFailure = Duration(minutes: 10);

  final AssignmentOfflineBundleService _service;
  final Future<String?> Function() _readSessionCookie;
  final Future<List<Map<String, dynamic>>> Function(String, String) _recordApi;
  final Future<bool> Function() _isUnmetered;
  final Duration _pageTimeout;
  final Duration _packageTimeout;

  OfflineFormsIndex _index = OfflineFormsIndex.empty;
  Map<int, OfflineFormStatus> _statuses = const {};
  final Set<int> _busy = {};
  final Map<String, DateTime> _failedAt = {};
  final Map<int, Future<OfflineSaveResult>> _explicit = {};
  final ListQueue<_QueuedJob> _queue = ListQueue();
  final Set<String> _running = {};
  bool _pumping = false;
  bool _progressed = false;
  int _generation = 0;

  List<Assignment> _all = const [];
  List<Assignment> _lastEligible = const [];
  OfflineFormsEnvironment? _lastEnv;

  /// Completes once no background work is running (for tests).
  @visibleForTesting
  Future<void> get idle async {
    while (_pumping || _running.isNotEmpty) {
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
  }

  /// Saved forms were removed elsewhere (settings, sign-out, pruning).
  void _onStorageChanged() {
    _queue.clear();
    unawaited(
      refresh(_all, language: _lastEnv?.language ?? '').catchError((_) {}),
    );
  }

  OfflineFormStatus statusFor(int assignmentId) =>
      _statuses[assignmentId] ?? OfflineFormStatus.none;

  /// A heavy or user-requested save for this assignment is running.
  bool isBusy(int assignmentId) => _busy.contains(assignmentId);

  /// Some saved template no longer matches the server's static files.
  bool get hasOutdatedPackages =>
      _statuses.values.any((s) => s.hasPage && !s.packageCurrent);

  OfflineFormsIndex get index => _index;

  bool _recentlyFailed(String key) {
    final at = _failedAt[key];
    return at != null && DateTime.now().difference(at) < _retryAfterFailure;
  }

  /// Reads what is saved on disk and recomputes every assignment's state.
  Future<void> refresh(
    Iterable<Assignment> assignments, {
    required String language,
  }) async {
    final list = assignments.toList();
    final index = await _service.readIndex();
    final statuses = {
      for (final a in list)
        a.id: evaluateOfflineForm(a, index, language: language),
    };
    _index = index;
    _all = list;
    if (!mapEquals(statuses, _statuses)) {
      _statuses = statuses;
      notifyListeners();
    }
  }

  /// Forgets all state (after sign-out).
  void reset() {
    _generation++;
    _queue.clear();
    _statuses = const {};
    _index = OfflineFormsIndex.empty;
    _busy.clear();
    _failedAt.clear();
    _all = const [];
    _lastEligible = const [];
    _lastEnv = null;
    notifyListeners();
  }

  /// Refreshes states and queues the background work the plan calls for.
  ///
  /// Selecting another entity only ever adds pages (one small request each):
  /// a template that is saved and current is never downloaded again. Package
  /// downloads happen for templates that were saved before but are outdated
  /// (or for every template when auto-download is on), on Wi-Fi only.
  Future<void> reconcile({
    required Iterable<Assignment> all,
    required Iterable<Assignment> eligible,
    required OfflineFormsEnvironment env,
    bool clearFailures = false,
  }) async {
    final generation = _generation;
    await refresh(all, language: env.language);
    if (generation != _generation) return;
    if (clearFailures) _failedAt.clear();
    _lastEligible = eligible.toList();
    _lastEnv = env;
    if (!env.online) {
      _queue.clear();
      return;
    }
    await _enqueuePlan();
    unawaited(_pump());
  }

  Future<void> _enqueuePlan() async {
    final env = _lastEnv;
    if (env == null) return;
    final autoDownload = await _service.isAutoDownloadEnabled();
    final allowPackages = await _isUnmetered();
    final plan = planOfflineJobs(
      eligible: _lastEligible,
      index: _index,
      language: env.language,
      autoDownload: autoDownload,
      allowPackageWork: allowPackages,
      skip: (k) => _recentlyFailed(k) || _running.contains(k),
    );
    _queue
      ..clear()
      ..addAll(plan.map((j) => _QueuedJob(j, env)));
  }

  Future<void> _pump() async {
    if (_pumping) return;
    _pumping = true;
    final generation = _generation;
    var passes = 0;
    try {
      while (generation == _generation && passes++ < 4) {
        while (_queue.isNotEmpty && generation == _generation) {
          final next = _queue.removeFirst();
          await _run(next, explicit: false);
        }
        if (!_progressed || generation != _generation) break;
        _progressed = false;
        await refresh(_all, language: _lastEnv?.language ?? '');
        await _enqueuePlan();
        if (_queue.isEmpty) break;
      }
    } finally {
      _pumping = false;
    }
  }

  OfflineFormRequest _request(
    Assignment a,
    OfflineFormsEnvironment env,
    String? cookie,
    CancelToken cancel,
  ) => OfflineFormRequest(
    assignmentId: a.id,
    formPath: AppRoutes.formEntry(a.id),
    language: env.language,
    templateId: a.templateId,
    sessionCookieHeader: cookie,
    formDefinitionUpdatedAtIso: a.formDefinitionUpdatedAt
        ?.toUtc()
        .toIso8601String(),
    staticVersion: a.staticVersion,
    dataVersion: a.dataVersion,
    title: a.templateName ?? a.name,
    submitBlockedMessage: env.submitBlockedMessage,
    recordApiResponses: (url) => _recordApi(url, env.language),
    cancelToken: cancel,
  );

  Future<OfflineSaveResult> _run(
    _QueuedJob queued, {
    required bool explicit,
  }) async {
    final job = queued.job;
    final a = job.assignment;
    final heavy = job.kind == OfflineJobKind.package;
    final registered = _running.add(job.key);
    if (!registered && !explicit) return const OfflineSaveResult.success();
    final showBusy = heavy || explicit;
    if (showBusy) {
      _busy.add(a.id);
      notifyListeners();
    }
    final cancel = CancelToken();
    try {
      final cookie = await _readSessionCookie();
      final request = _request(a, queued.env, cookie, cancel);
      final limit = heavy ? _packageTimeout : _pageTimeout;
      final op = heavy
          ? _service.savePackageAndPage(request)
          : _service.savePage(request);
      await op.timeout(
        limit,
        onTimeout: () {
          cancel.cancel('timeout');
          throw AssignmentOfflineBundleException(
            'Saving the form took longer than ${limit.inSeconds}s.',
          );
        },
      );
      _failedAt.remove(job.key);
      _progressed = true;
      return const OfflineSaveResult.success();
    } catch (e, st) {
      cancel.cancel('failed');
      _failedAt[job.key] = DateTime.now();
      DebugLogger.logWarn(
        'OFFLINE_BUNDLE',
        '${job.kind.name} save failed for assignment ${a.id}: $e',
      );
      unawaited(
        ClientDiagnosticsService.report(
          category: ClientDiagnosticsService.categoryOfflineDownload,
          error: e,
          stackTrace: st,
          assignmentId: a.id,
          templateId: a.templateId,
          language: queued.env.language,
          trace: _service.traceFor(a.id),
          extraDetails: {'job': job.kind.name, 'explicit': explicit},
        ),
      );
      return OfflineSaveResult.failure(e);
    } finally {
      if (registered) _running.remove(job.key);
      _busy.remove(a.id);
      try {
        await refresh(_withAssignment(a), language: queued.env.language);
      } catch (_) {}
      notifyListeners();
    }
  }

  List<Assignment> _withAssignment(Assignment extra) => [
    ..._all,
    if (!_all.any((x) => x.id == extra.id)) extra,
  ];

  /// Saves one assignment because the user asked to. Uses the cheap page-only
  /// path when the template is already saved and current.
  Future<OfflineSaveResult> save(
    Assignment assignment,
    OfflineFormsEnvironment env,
  ) {
    final existing = _explicit[assignment.id];
    if (existing != null) return existing;
    final status = evaluateOfflineForm(
      assignment,
      _index,
      language: env.language,
    );
    final kind = status.packageCurrent
        ? OfflineJobKind.page
        : OfflineJobKind.package;
    final future =
        _run(
          _QueuedJob(OfflineJob(kind, assignment), env),
          explicit: true,
        ).whenComplete(() {
          _explicit.remove(assignment.id);
        });
    _explicit[assignment.id] = future;
    return future;
  }

  /// Removes the saved template of [assignment] (package and all pages).
  Future<void> remove(Assignment assignment) async {
    await _service.removeForAssignment(
      assignmentId: assignment.id,
      templateId: assignment.templateId,
    );
    await refresh(
      _withAssignment(assignment),
      language: _lastEnv?.language ?? '',
    );
  }

  /// Deletes copies of closed assignments and surplus pages.
  Future<void> prune({
    required Iterable<Assignment> current,
    required Iterable<Assignment> past,
  }) async {
    if (current.isEmpty && past.isEmpty) return;
    try {
      await _service.pruneBundles(
        closedAssignmentIds: {
          ...past.map((a) => a.id),
          ...current.where((a) => a.isEffectivelyClosed).map((a) => a.id),
        },
      );
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_BUNDLE', 'Prune failed: $e');
    }
  }
}
