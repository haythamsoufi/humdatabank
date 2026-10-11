import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../utils/debug_logger.dart';
import 'assignment_offline_bundle_service.dart';
import 'offline_form_scripts.dart';
import 'webview_service.dart';

/// One recorded API response, as produced by [kOfflineApiRecorderJs].
typedef RecordedApiEntry = Map<String, dynamic>;

/// Captures the data an assignment entry form loads from the server so a saved
/// offline copy can serve it later (lookup lists, plugin data such as emergency
/// operations, entry bootstrap, resolved variables).
class OfflineApiRecorder {
  OfflineApiRecorder._();

  static final RegExp _assignmentPath = RegExp(r'/assignment/(\d+)');

  /// Assignment id for an entry-form URL or path, or null for any other page.
  static int? assignmentIdForUrl(String url) {
    final m = _assignmentPath.firstMatch(Uri.tryParse(url)?.path ?? url);
    return m == null ? null : int.tryParse(m.group(1)!);
  }

  static UserScript get userScript => UserScript(
        source: kOfflineApiRecorderJs,
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      );

  /// Parses a `{aesId, entries}` JSON payload from the page.
  static ({int aesId, List<RecordedApiEntry> entries})? parsePayload(
    Object? raw,
  ) {
    try {
      final decoded = raw is String ? jsonDecode(raw) : raw;
      if (decoded is! Map) return null;
      final id = (decoded['aesId'] as num?)?.toInt();
      final list = decoded['entries'];
      if (id == null || list is! List) return null;
      return (
        aesId: id,
        entries: [
          for (final e in list)
            if (e is Map) Map<String, dynamic>.from(e),
        ],
      );
    } catch (_) {
      return null;
    }
  }

  /// Saves responses seen while the form is open online into the matching
  /// offline copy (no-op when that assignment has no saved copy).
  static void registerLiveHandler(InAppWebViewController controller) {
    controller.addJavaScriptHandler(
      handlerName: kOfflineApiRecordHandler,
      callback: (args) async {
        final payload = parsePayload(args.isEmpty ? null : args.first);
        if (payload == null) return 'err';
        try {
          await AssignmentOfflineBundleService().mergeApiCache(
            payload.aesId,
            payload.entries,
          );
          return 'ok';
        } catch (e) {
          DebugLogger.logWarn('OFFLINE_API', 'merge failed: $e');
          return 'err';
        }
      },
    );
  }

  /// Loads [formUrl] in a hidden WebView (same session as the app's WebViews) and
  /// returns the API responses the form fetched while initialising.
  ///
  /// Completes once the page has loaded and gone quiet, or after [timeout].
  /// Throws when the page redirects to the login screen.
  static Future<List<RecordedApiEntry>> recordFormLoad({
    required String formUrl,
    required String language,
    Duration quietFor = const Duration(seconds: 3),
    Duration timeout = const Duration(seconds: 30),
  }) async {
    final collected = <RecordedApiEntry>[];
    var loadedAt = DateTime.fromMillisecondsSinceEpoch(0);
    var lastEntryAt = DateTime.fromMillisecondsSinceEpoch(0);
    var loaded = false;
    String? failure;
    InAppWebViewController? controller;

    final headless = HeadlessInAppWebView(
      initialUrlRequest: URLRequest(
        url: WebUri(formUrl),
        headers: WebViewService.defaultRequestHeaders,
      ),
      initialUserScripts: UnmodifiableListView<UserScript>([
        ...WebViewService.getRequestInterceptorScripts(language: language),
        userScript,
      ]),
      initialSettings: WebViewService.defaultSettings(allowMixedContent: true),
      onWebViewCreated: (c) {
        controller = c;
        c.addJavaScriptHandler(
          handlerName: kOfflineApiRecordHandler,
          callback: (args) {
            final payload = parsePayload(args.isEmpty ? null : args.first);
            if (payload != null) {
              collected.addAll(payload.entries);
              lastEntryAt = DateTime.now();
            }
            return 'ok';
          },
        );
      },
      onLoadStop: (c, url) {
        final path = url?.path ?? '';
        if (path.contains('/login') || path.contains('/auth/')) {
          failure = 'Session expired while preparing the offline copy.';
        }
        loaded = true;
        loadedAt = DateTime.now();
      },
      onReceivedHttpError: (c, request, response) {
        if (request.isForMainFrame == true &&
            (response.statusCode ?? 0) >= 400) {
          failure = 'Form page returned HTTP ${response.statusCode}.';
        }
      },
      onReceivedError: (c, request, error) {
        if (request.isForMainFrame == true) {
          failure = error.description;
        }
      },
    );

    final started = DateTime.now();
    try {
      await headless.run();
      while (DateTime.now().difference(started) < timeout) {
        await Future<void>.delayed(const Duration(milliseconds: 400));
        if (failure != null) break;
        if (!loaded) continue;
        final now = DateTime.now();
        final quietSinceLoad = now.difference(loadedAt) >= quietFor;
        final quietSinceEntry = now.difference(lastEntryAt) >= quietFor;
        if (quietSinceLoad && quietSinceEntry) break;
      }
      try {
        await controller?.evaluateJavascript(
          source:
              'window.__ifrcApiRecorderFlush && window.__ifrcApiRecorderFlush();',
        );
        await Future<void>.delayed(const Duration(milliseconds: 300));
      } catch (_) {}
    } finally {
      try {
        await headless.dispose();
      } catch (_) {}
    }

    if (failure != null) {
      throw AssignmentOfflineBundleException(failure!);
    }
    DebugLogger.logInfo(
      'OFFLINE_API',
      'Recorded ${collected.length} API responses for $formUrl',
    );
    return collected;
  }
}
