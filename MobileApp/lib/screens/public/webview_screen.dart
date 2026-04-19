import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../services/session_service.dart';
import '../../services/assignment_offline_bundle_service.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/url_helper.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../services/webview_service.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/debug_logger.dart' show DebugLogger, LogLevel;

/// Route arguments for [WebViewScreen]: either a [String] path/URL, or a map
/// from the dashboard (offline bundle / future extensions).
class WebViewScreenArgs {
  final String initialUrl;
  final bool forceOfflineAssignmentBundle;
  final int? offlineAssignmentId;

  const WebViewScreenArgs({
    required this.initialUrl,
    this.forceOfflineAssignmentBundle = false,
    this.offlineAssignmentId,
  });

  static WebViewScreenArgs parse(Object? raw) {
    if (raw is WebViewScreenArgs) return raw;
    if (raw is String) {
      return WebViewScreenArgs(initialUrl: raw);
    }
    if (raw is Map) {
      final map = Map<String, dynamic>.from(raw);
      final url = (map['initialUrl'] ?? map['url'])?.toString().trim() ?? '';
      final offline = map['offline'] == true || map['force_offline'] == true;
      int? aid;
      final rawId = map['assignment_id'] ?? map['assignmentId'];
      if (rawId is int) {
        aid = rawId;
      } else if (rawId != null) {
        aid = int.tryParse(rawId.toString());
      }
      return WebViewScreenArgs(
        initialUrl: url,
        forceOfflineAssignmentBundle: offline,
        offlineAssignmentId: aid,
      );
    }
    return const WebViewScreenArgs(initialUrl: '');
  }
}

class _WebViewPayload {
  final bool isOfflineBundle;
  final String? offlineHtml;
  final String? offlineBundleDir;
  final String onlineUrl;

  const _WebViewPayload.online(this.onlineUrl)
      : isOfflineBundle = false,
        offlineHtml = null,
        offlineBundleDir = null;

  const _WebViewPayload.offline({
    required this.offlineHtml,
    required this.offlineBundleDir,
    required this.onlineUrl,
  }) : isOfflineBundle = true;
}

class WebViewScreen extends StatefulWidget {
  final String initialUrl;
  final bool forceOfflineAssignmentBundle;
  final int? offlineAssignmentId;

  const WebViewScreen({
    super.key,
    required this.initialUrl,
    this.forceOfflineAssignmentBundle = false,
    this.offlineAssignmentId,
  });

  @override
  State<WebViewScreen> createState() => _WebViewScreenState();
}

class _WebViewScreenState extends State<WebViewScreen> {
  InAppWebViewController? _webViewController;
  final SessionService _sessionService = SessionService();
  bool _isLoading = true;
  double _progress = 0;
  String? _error;
  String? _pageTitle;
  final int _currentNavIndex =
      -1; // -1 means no tab is active (WebView is on top)

  String? _payloadLanguage;
  Future<_WebViewPayload>? _payloadFuture;

  /// Throttles [setState] from WebView progress ticks (reduces rebuild / log noise).
  int _lastProgressBucket = -1;

  void _resetWebViewProgressThrottle() {
    _lastProgressBucket = -1;
  }

  void _maybeUpdateWebViewProgress(int progress) {
    final bucket = progress >= 100 ? 1000 : progress ~/ 5;
    if (bucket == _lastProgressBucket) return;
    _lastProgressBucket = bucket;
    if (!mounted) return;
    setState(() {
      _progress = progress / 100;
    });
  }

  @override
  void initState() {
    super.initState();
    _injectSession();
  }

  @override
  void dispose() {
    // Dispose WebView controller to free memory
    if (_webViewController != null) {
      _webViewController!.stopLoading();
      _webViewController = null;
    }
    super.dispose();
  }

  Future<void> _injectSession() async {
    await _sessionService.injectSessionIntoWebView();
  }

  bool _bytesLookLikePdf(List<int> bytes) =>
      bytes.length >= 4 &&
      bytes[0] == 0x25 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x44 &&
      bytes[3] == 0x46;

  bool _bytesLookLikeZip(List<int> bytes) =>
      bytes.length >= 2 && bytes[0] == 0x50 && bytes[1] == 0x4B;

  String _suggestedExportFileName(Uri url, List<int> bytes) {
    final m = RegExp(r'/assignment_status/(\d+)/').firstMatch(url.path);
    final id = m?.group(1) ?? 'export';
    if (url.path.contains('/export_pdf') && _bytesLookLikePdf(bytes)) {
      return 'assignment_$id.pdf';
    }
    if (url.path.contains('/export_excel') && _bytesLookLikeZip(bytes)) {
      return 'assignment_$id.xlsx';
    }
    if (url.path.contains('/validation_summary')) {
      final ct = _bytesLookLikePdf(bytes) ? 'pdf' : 'html';
      return 'assignment_${id}_validation.$ct';
    }
    return 'assignment_$id.bin';
  }

  Future<void> _fetchDownloadWithCookiesThenDeliver(
    Uri url,
    InAppWebViewController controller,
  ) async {
    await _handleDownload(url, controller);
  }

  /// Assignment PDF/Excel (and similar) are delivered as downloads; Android then
  /// invokes this path. [launchUrl] opens Samsung Internet / Chrome without the
  /// WebView cookie jar, so we re-fetch with [CookieManager] and share the file.
  Future<void> _handleDownload(
    Uri url,
    InAppWebViewController controller,
  ) async {
    if (WebViewService.isFormAssignmentSessionDownloadUrl(url)) {
      try {
        final webUri = WebUri(url.toString());
        final stored = await CookieManager.instance().getCookies(url: webUri);
        final cookieHeader = stored.map((c) => '${c.name}=${c.value}').join('; ');
        final headers = <String, String>{
          ...WebViewService.defaultRequestHeaders,
          if (cookieHeader.isNotEmpty) HttpHeaders.cookieHeader: cookieHeader,
        };
        final resp = await http.get(url, headers: headers);
        if (resp.statusCode < 200 || resp.statusCode >= 300) {
          throw HttpException('HTTP ${resp.statusCode}');
        }
        final body = resp.bodyBytes;
        if (url.path.contains('/export_pdf') && !_bytesLookLikePdf(body)) {
          throw const FormatException('Not a PDF (session may have expired)');
        }
        if (url.path.contains('/export_excel') && !_bytesLookLikeZip(body)) {
          throw const FormatException('Not an Excel file (session may have expired)');
        }
        final dir = await getTemporaryDirectory();
        final name = _suggestedExportFileName(url, body);
        final file = File('${dir.path}/$name');
        await file.writeAsBytes(body, flush: true);
        if (url.path.contains('/export_pdf') && _bytesLookLikePdf(body)) {
          if (mounted) {
            await Navigator.of(context).pushNamed(
              AppRoutes.pdfViewer,
              arguments: <String, String>{
                'filePath': file.path,
                'title': name,
              },
            );
          }
          DebugLogger.logInfo('WEBVIEW', 'Session PDF export opened in viewer: $name');
        } else {
          await Share.shareXFiles([XFile(file.path)], subject: name);
          DebugLogger.logInfo('WEBVIEW', 'Session export saved for share: $name');
        }
      } catch (e, st) {
        DebugLogger.logError('WEBVIEW session export failed: $e\n$st');
        if (mounted) {
          final theme = Theme.of(context);
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                '${localizations.errorOpeningDownload}: $e',
              ),
              backgroundColor: theme.colorScheme.error,
            ),
          );
        }
      }
      return;
    }

    try {
      if (defaultTargetPlatform == TargetPlatform.iOS) {
        if (mounted) {
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(localizations.couldNotOpenDownloadLink)),
          );
        }
        return;
      }
      if (await canLaunchUrl(url)) {
        await launchUrl(url, mode: LaunchMode.platformDefault);
      } else {
        if (mounted) {
          final theme = Theme.of(context);
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.couldNotOpenDownloadLink),
              backgroundColor: theme.colorScheme.error,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        final theme = Theme.of(context);
        final localizations = AppLocalizations.of(context)!;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              '${localizations.errorOpeningDownload}: ${e.toString()}',
            ),
            backgroundColor: theme.colorScheme.error,
          ),
        );
      }
    }
  }

  String _buildUrl(String path, String language) {
    return UrlHelper.resolveWebViewInitialUrl(path, language);
  }

  Future<_WebViewPayload> _resolvePayload(String language) async {
    final onlineUrl = _buildUrl(widget.initialUrl, language);
    if (widget.forceOfflineAssignmentBundle &&
        widget.offlineAssignmentId != null) {
      final svc = AssignmentOfflineBundleService();
      final html =
          await svc.readOfflineIndexHtml(widget.offlineAssignmentId!);
      if (html != null && html.isNotEmpty) {
        final dir = await svc.offlineBundleDirectoryPath(
          widget.offlineAssignmentId!,
        );
        DebugLogger.logInfo(
          'WEBVIEW',
          'Using offline bundle assignment=${widget.offlineAssignmentId} '
          'dir=$dir htmlChars=${html.length} onlineRef=$onlineUrl',
        );
        return _WebViewPayload.offline(
          offlineHtml: html,
          offlineBundleDir: dir,
          onlineUrl: onlineUrl,
        );
      }
      DebugLogger.logWarn(
        'WEBVIEW',
        'Offline bundle missing/empty for assignment=${widget.offlineAssignmentId}; '
        'falling back to online $onlineUrl',
      );
    }
    DebugLogger.logInfo('WEBVIEW', 'Using online WebView url=$onlineUrl');
    return _WebViewPayload.online(onlineUrl);
  }

  Future<_WebViewPayload> _payloadForLanguage(String language) {
    if (_payloadLanguage != language) {
      _payloadLanguage = language;
      _payloadFuture = _resolvePayload(language);
    }
    return _payloadFuture!;
  }

  void _invalidatePayload() {
    _payloadLanguage = null;
    _payloadFuture = null;
  }

  WebUri _offlineFileBaseWebUri(String bundleDir) {
    final withSlash =
        bundleDir.endsWith('/') ? bundleDir : '$bundleDir/';
    return WebUri.uri(Uri.file(withSlash));
  }

  /// Logs subresource load failures; CSS and `/static/` always at WARN.
  void _logWebViewResourceFailure({
    required bool isForMainFrame,
    required WebUri? url,
    required String kind,
    String? extra,
  }) {
    final u = url?.toString() ?? '(null url)';
    final lower = u.toLowerCase();
    final highlight = isForMainFrame ||
        lower.contains('.css') ||
        lower.contains('/static/') ||
        lower.contains('stylesheet');
    final msg =
        '$kind mainFrame=$isForMainFrame url=$u${extra != null ? ' $extra' : ''}';
    if (highlight) {
      DebugLogger.logWarn('WEBVIEW_ASSET', msg);
    } else if (DebugLogger.verboseDebugLogs) {
      DebugLogger.log('WEBVIEW_ASSET', msg, level: LogLevel.debug);
    }
  }

  Future<void> _logStylesheetDiagnostics(
    InAppWebViewController controller, {
    required bool offline,
    String? bundleDir,
    WebUri? pageUrl,
  }) async {
    try {
      final raw = await controller.evaluateJavascript(
        source: WebViewService.stylesheetLoadDiagEvaluateSource,
      );
      final s = raw?.toString() ?? '(null)';
      DebugLogger.logInfo(
        'WEBVIEW_CSS',
        'stylesheet_diag offline=$offline bundleDir=${bundleDir ?? "-"} '
        'pageUrl=${pageUrl ?? "-"} => $s',
      );
    } catch (e, st) {
      DebugLogger.logWarn('WEBVIEW_CSS', 'stylesheet_diag failed: $e\n$st');
    }
  }

  Widget _buildInAppWebView({
    required _WebViewPayload payload,
    required String language,
    required AppLocalizations localizations,
  }) {
    if (payload.isOfflineBundle) {
      final base = _offlineFileBaseWebUri(payload.offlineBundleDir!);
      return InAppWebView(
        key: ValueKey('offline|${payload.onlineUrl}|$language'),
        initialData: InAppWebViewInitialData(
          data: payload.offlineHtml!,
          baseUrl: base,
          mimeType: 'text/html',
          encoding: 'utf8',
          historyUrl: base,
        ),
        initialUserScripts: WebViewService.getRequestInterceptorScripts(
          language: language,
        ),
        initialSettings: WebViewService.offlineAssignmentBundleSettings(
          payload.offlineBundleDir!,
        ),
        onWebViewCreated: (controller) {
          _webViewController = controller;
          DebugLogger.logInfo(
            'WEBVIEW',
            'offline WebView created baseUrl=$base '
            'allowingRead=${payload.offlineBundleDir}',
          );
        },
        onConsoleMessage: (controller, consoleMessage) {
          if (!DebugLogger.verboseDebugLogs) return;
          DebugLogger.log(
            'WEBVIEW_CONSOLE',
            '${consoleMessage.messageLevel}: ${consoleMessage.message}',
            level: LogLevel.debug,
          );
        },
        shouldOverrideUrlLoading: (controller, navigationAction) async {
          final url = navigationAction.request.url;
          if (url != null &&
              WebViewService.isOfflineBundleServerOnlyAssignmentExport(url)) {
            DebugLogger.logInfo(
              'WEBVIEW',
              'Blocked offline bundle server-only export navigation: $url',
            );
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(
                    localizations.offlineFormExportRequiresConnection,
                  ),
                ),
              );
            }
            return NavigationActionPolicy.CANCEL;
          }
          if (url != null && !WebViewService.isUrlAllowed(url)) {
            DebugLogger.logWarn('WEBVIEW', 'Blocked navigation to: $url');
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text(localizations.navUrlNotAllowed),
                  backgroundColor: Theme.of(context).colorScheme.error,
                ),
              );
            }
            return NavigationActionPolicy.CANCEL;
          }
          return NavigationActionPolicy.ALLOW;
        },
        onLoadStart: (controller, url) {
          DebugLogger.logInfo('WEBVIEW', 'offline onLoadStart url=$url');
          _resetWebViewProgressThrottle();
          setState(() {
            _isLoading = true;
            _error = null;
          });
        },
        onLoadStop: (controller, url) async {
          setState(() {
            _isLoading = false;
            _error = null;
          });
          if (language == 'ar') {
            await controller.evaluateJavascript(
              source: WebViewService.arabicTajawalPostLoadEvaluateSource,
            );
          }
          final title = await controller.getTitle();
          if (title != null && mounted) {
            setState(() {
              _pageTitle = title;
            });
          }
          await _logStylesheetDiagnostics(
            controller,
            offline: true,
            bundleDir: payload.offlineBundleDir,
            pageUrl: url,
          );
        },
        onTitleChanged: (controller, title) {
          if (title != null && mounted) {
            setState(() {
              _pageTitle = title;
            });
          }
        },
        onProgressChanged: (controller, progress) {
          _maybeUpdateWebViewProgress(progress);
        },
        onReceivedError: (controller, request, error) {
          final main = request.isForMainFrame == true;
          _logWebViewResourceFailure(
            isForMainFrame: main,
            url: request.url,
            kind: 'net_error',
            extra: '${error.type} ${error.description}',
          );
          if (!main) return;
          if (WebViewService.shouldIgnoreError(error.description)) {
            return;
          }
          setState(() {
            _isLoading = false;
            _error = error.description;
          });
        },
        onReceivedHttpError: (controller, request, response) {
          final main = request.isForMainFrame == true;
          _logWebViewResourceFailure(
            isForMainFrame: main,
            url: request.url,
            kind: 'http_error',
            extra: 'status=${response.statusCode}',
          );
          if (!main) return;
          final statusCode = response.statusCode;
          if (statusCode != null && statusCode >= 400) {
            setState(() {
              _isLoading = false;
              _error = AppLocalizations.of(context)!.httpError(statusCode);
            });
          }
        },
        onDownloadStartRequest:
            (InAppWebViewController controller, DownloadStartRequest request) {
          _handleDownload(Uri.parse(request.url.toString()), controller);
        },
      );
    }

    final url = payload.onlineUrl;
    return InAppWebView(
      key: ValueKey('online|$url|$language'),
      initialUrlRequest: URLRequest(
        url: WebUri(url),
        headers: WebViewService.defaultRequestHeaders,
      ),
      initialUserScripts: WebViewService.getRequestInterceptorScripts(
        language: language,
      ),
      // Allow passive/active mixed content for this trusted surface only (some
      // deployments still emit occasional http:// asset URLs behind proxies).
      initialSettings: WebViewService.defaultSettings(allowMixedContent: true),
      onWebViewCreated: (controller) {
        _webViewController = controller;
        DebugLogger.logInfo('WEBVIEW', 'online WebView created initialUrl=$url');
      },
      onConsoleMessage: (controller, consoleMessage) {
        if (!DebugLogger.verboseDebugLogs) return;
        DebugLogger.log(
          'WEBVIEW_CONSOLE',
          '${consoleMessage.messageLevel}: ${consoleMessage.message}',
          level: LogLevel.debug,
        );
      },
      shouldOverrideUrlLoading: (controller, navigationAction) async {
        // Only gate top-level navigations; subframes/embeds are already allowed
        // by the Backoffice CSP and must match our expanded host allowlist separately.
        if (navigationAction.isForMainFrame != true) {
          final subUrl = navigationAction.request.url;
          if (subUrl != null && !WebViewService.isUrlAllowed(subUrl)) {
            DebugLogger.logWarn('WEBVIEW', 'Blocked subframe navigation: $subUrl');
            return NavigationActionPolicy.CANCEL;
          }
          return NavigationActionPolicy.ALLOW;
        }
        final navUrl = navigationAction.request.url;
        if (navUrl != null && !WebViewService.isUrlAllowed(navUrl)) {
          DebugLogger.logWarn('WEBVIEW', 'Blocked navigation to: $navUrl');
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(localizations.navUrlNotAllowed),
                backgroundColor: Theme.of(context).colorScheme.error,
              ),
            );
          }
          return NavigationActionPolicy.CANCEL;
        }
        final parsedNav = navUrl != null ? Uri.tryParse(navUrl.toString()) : null;
        if (parsedNav != null &&
            WebViewService.isFormAssignmentSessionDownloadUrl(parsedNav)) {
          unawaited(
            _fetchDownloadWithCookiesThenDeliver(parsedNav, controller),
          );
          return NavigationActionPolicy.CANCEL;
        }
        return NavigationActionPolicy.ALLOW;
      },
      onLoadStart: (controller, url) {
        DebugLogger.logInfo('WEBVIEW', 'online onLoadStart url=$url');
        _resetWebViewProgressThrottle();
        setState(() {
          _isLoading = true;
          _error = null;
        });
      },
      onLoadStop: (controller, url) async {
        setState(() {
          _isLoading = false;
          _error = null;
        });
        if (language == 'ar') {
          await controller.evaluateJavascript(
            source: WebViewService.arabicTajawalPostLoadEvaluateSource,
          );
        }
        final title = await controller.getTitle();
        if (title != null && mounted) {
          setState(() {
            _pageTitle = title;
          });
        }
        await _logStylesheetDiagnostics(
          controller,
          offline: false,
          pageUrl: url,
        );
      },
      onTitleChanged: (controller, title) {
        if (title != null && mounted) {
          setState(() {
            _pageTitle = title;
          });
        }
      },
      onProgressChanged: (controller, progress) {
        _maybeUpdateWebViewProgress(progress);
      },
      onReceivedError: (controller, request, error) {
        final main = request.isForMainFrame == true;
        _logWebViewResourceFailure(
          isForMainFrame: main,
          url: request.url,
          kind: 'net_error',
          extra: '${error.type} ${error.description}',
        );
        if (!main) return;
        if (WebViewService.shouldIgnoreError(error.description)) {
          DebugLogger.logInfo(
            'WEBVIEW',
            'mainFrame net error ignored: ${error.description}',
          );
          return;
        }
        setState(() {
          _isLoading = false;
          _error = error.description;
        });
      },
      onReceivedHttpError: (controller, request, response) {
        final main = request.isForMainFrame == true;
        _logWebViewResourceFailure(
          isForMainFrame: main,
          url: request.url,
          kind: 'http_error',
          extra: 'status=${response.statusCode}',
        );
        if (!main) return;
        final statusCode = response.statusCode;
        if (statusCode != null && statusCode >= 400) {
          setState(() {
            _isLoading = false;
            _error = AppLocalizations.of(context)!.httpError(statusCode);
          });
        }
      },
      onDownloadStartRequest:
          (InAppWebViewController controller, DownloadStartRequest request) {
        _handleDownload(Uri.parse(request.url.toString()), controller);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<AuthProvider, LanguageProvider>(
      builder: (context, authProvider, languageProvider, child) {
        final language = languageProvider.currentLanguage;

        final localizations = AppLocalizations.of(context)!;
        final theme = Theme.of(context);

        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: _pageTitle ?? localizations.loading,
            actions: [
              if (_webViewController != null)
                IconButton(
                  icon: const Icon(Icons.refresh),
                  onPressed: () {
                    if (widget.forceOfflineAssignmentBundle &&
                        widget.offlineAssignmentId != null) {
                      _invalidatePayload();
                    }
                    _webViewController?.reload();
                  },
                  tooltip: localizations.refresh,
                ),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () {
                  Navigator.of(context).pop();
                },
                tooltip: localizations.close,
              ),
            ],
          ),
          body: ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: SafeArea(
              top: true,
              bottom: false,
              child: ListView(
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  SizedBox(
                    height:
                        MediaQuery.of(context).size.height -
                        MediaQuery.of(context).padding.top -
                        kToolbarHeight -
                        50 - // Bottom navigation bar height
                        MediaQuery.of(
                          context,
                        ).padding.bottom, // Safe area bottom padding
                    child: Stack(
                      children: [
                        FutureBuilder<_WebViewPayload>(
                          future: _payloadForLanguage(language),
                          builder: (context, snapshot) {
                            if (snapshot.connectionState !=
                                ConnectionState.done) {
                              return const SizedBox.shrink();
                            }
                            if (snapshot.hasError) {
                              return Center(
                                child: Padding(
                                  padding: const EdgeInsets.all(24),
                                  child: Text(
                                    snapshot.error.toString(),
                                    textAlign: TextAlign.center,
                                  ),
                                ),
                              );
                            }
                            final payload = snapshot.data!;
                            if (widget.forceOfflineAssignmentBundle &&
                                !payload.isOfflineBundle) {
                              return Center(
                                child: Padding(
                                  padding: const EdgeInsets.all(24),
                                  child: Text(
                                    localizations.offlineFormNotDownloaded,
                                    textAlign: TextAlign.center,
                                  ),
                                ),
                              );
                            }
                            return _buildInAppWebView(
                              payload: payload,
                              language: language,
                              localizations: localizations,
                            );
                          },
                        ),
                        // Loading Indicator
                        if (_isLoading && _progress < 1.0)
                          Column(
                            children: [
                              LinearProgressIndicator(
                                value: _progress,
                                backgroundColor: context.dividerColor,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  Color(AppConstants.ifrcRed),
                                ),
                                minHeight: 3,
                              ),
                              Expanded(
                                child: Container(
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: [
                                        context.navyBackgroundColor(
                                          opacity: 0.05,
                                        ),
                                        theme.scaffoldBackgroundColor,
                                      ],
                                    ),
                                  ),
                                  child: Center(
                                    child: Column(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        CircularProgressIndicator(
                                          valueColor:
                                              AlwaysStoppedAnimation<Color>(
                                                Color(AppConstants.ifrcRed),
                                              ),
                                        ),
                                        const SizedBox(height: 16),
                                        Text(
                                          localizations.loading,
                                          style: const TextStyle(
                                            color: Color(
                                              AppConstants.textSecondary,
                                            ),
                                            fontSize: 14,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        // Error Display
                        if (_error != null && !_isLoading)
                          Container(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  context.navyBackgroundColor(opacity: 0.05),
                                  theme.scaffoldBackgroundColor,
                                ],
                              ),
                            ),
                            child: Center(
                              child: Padding(
                                padding: const EdgeInsets.all(24),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.all(20),
                                      decoration: BoxDecoration(
                                        color: const Color(
                                          AppConstants.errorColor,
                                        ).withValues(alpha: 0.1),
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Icon(
                                        Icons.error_outline,
                                        size: 64,
                                        color: Color(AppConstants.errorColor),
                                      ),
                                    ),
                                    const SizedBox(height: 24),
                                    Text(
                                      localizations.oopsSomethingWentWrong,
                                      style: TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.bold,
                                        color: theme.colorScheme.onSurface,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      _error!,
                                      style: TextStyle(
                                        color: theme.colorScheme.onSurface
                                            .withValues(alpha: 0.6),
                                        fontSize: 14,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 24),
                                    ElevatedButton.icon(
                                      onPressed: () {
                                        setState(() {
                                          _error = null;
                                        });
                                        if (widget.forceOfflineAssignmentBundle &&
                                            widget.offlineAssignmentId != null) {
                                          _invalidatePayload();
                                          setState(() {});
                                          return;
                                        }
                                        _webViewController?.reload();
                                      },
                                      icon: const Icon(Icons.refresh),
                                      label: Text(localizations.retry),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Color(
                                          AppConstants.ifrcRed,
                                        ),
                                        foregroundColor:
                                            theme.colorScheme.onPrimary,
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 24,
                                          vertical: 12,
                                        ),
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(
                                            12,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          floatingActionButton: widget.initialUrl.contains('/countries/')
              ? FloatingActionButton(
                  heroTag: 'menu_button_webview',
                  onPressed: () => _showNavigationMenu(
                    context,
                    languageProvider,
                    theme,
                    localizations,
                    language,
                  ),
                  backgroundColor: Color(AppConstants.ifrcRed),
                  foregroundColor: theme.colorScheme.onPrimary,
                  tooltip: localizations.navigationMenu,
                  child: const Icon(Icons.menu),
                )
              : null,
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: _currentNavIndex,
            // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
          ),
        );
      },
    );
  }

  void _showNavigationMenu(
    BuildContext context,
    LanguageProvider languageProvider,
    ThemeData theme,
    AppLocalizations localizations,
    String language,
  ) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isFocalPoint = user?.isFocalPoint ?? false;

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 16,
                  ),
                  child: Text(
                    localizations.navigation,
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                ),
                const Divider(height: 1),
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    physics: const ClampingScrollPhysics(),
                    children: [
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.home,
                        title: localizations.home,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).popUntil((route) {
                            return route.isFirst ||
                                route.settings.name == AppRoutes.dashboard;
                          });
                        },
                      ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.library_books,
                        title: localizations.indicatorBank,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          Navigator.of(
                            context,
                          ).pushNamed(AppRoutes.indicatorBank);
                        },
                      ),
                      // Resources/Notifications - navigate to native screen
                      if (isFocalPoint)
                        _buildMenuTile(
                          context: context,
                          theme: theme,
                          icon: Icons.notifications,
                          title: localizations.notifications,
                          onTap: () {
                            Navigator.pop(bottomSheetContext);
                            Navigator.of(context).pop();
                            Navigator.of(
                              context,
                            ).pushNamed(AppRoutes.notifications);
                          },
                        )
                      else
                        _buildMenuTile(
                          context: context,
                          theme: theme,
                          icon: Icons.folder,
                          title: localizations.resources,
                          onTap: () {
                            Navigator.pop(bottomSheetContext);
                            Navigator.of(context).pop();
                            Navigator.of(
                              context,
                            ).pushNamed(AppRoutes.resources);
                          },
                        ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.public,
                        title: localizations.countries,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          _showCountriesSheet(context, theme);
                        },
                      ),
                      Padding(
                        padding: const EdgeInsets.only(
                          top: 8,
                          left: 24,
                          right: 24,
                          bottom: 8,
                        ),
                        child: Text(
                          localizations.analysis,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface.withValues(
                              alpha: 0.7,
                            ),
                          ),
                        ),
                      ),
                      // Disaggregation Analysis - navigate to native screen
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.analytics,
                        title: localizations.disaggregationAnalysis,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          Navigator.of(
                            context,
                          ).pushNamed(AppRoutes.disaggregationAnalysis);
                        },
                      ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.bar_chart,
                        title: localizations.dataVisualization,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          final fullUrl =
                              UrlHelper.buildFrontendUrlWithLanguage(
                                '/dataviz',
                                language,
                              );
                          Navigator.of(
                            context,
                          ).pushNamed(AppRoutes.webview, arguments: fullUrl);
                        },
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
    final loc = AppLocalizations.of(context)!;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.9,
          ),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 24,
                    vertical: 16,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        loc.countries,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.pop(bottomSheetContext),
                        tooltip: loc.close,
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                const Expanded(child: CountriesWidget()),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMenuTile({
    required BuildContext context,
    required ThemeData theme,
    required IconData icon,
    required String title,
    required VoidCallback onTap,
  }) {
    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Icon(icon, color: Color(AppConstants.ifrcRed), size: 20),
      title: Text(
        title,
        style: theme.textTheme.bodyLarge?.copyWith(
          fontWeight: FontWeight.w500,
          color: theme.colorScheme.onSurface,
        ),
      ),
      trailing: Icon(
        Icons.chevron_right,
        color: theme.colorScheme.onSurface.withValues(alpha: 0.3),
        size: 20,
      ),
      onTap: onTap,
    );
  }
}
