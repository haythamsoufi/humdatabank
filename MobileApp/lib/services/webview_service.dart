import 'dart:collection';
import 'dart:io';

import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:path/path.dart' as p;

import '../config/app_config.dart';
import '../utils/debug_logger.dart';

class WebViewService {
  static const Map<String, String> defaultRequestHeaders = {
    'Accept-Encoding': 'identity',
    'X-Mobile-App': 'IFRC-Databank-Flutter',
  };

  /// Validates if a URL is allowed to load in WebView
  /// Returns true if URL matches allowed patterns, false otherwise
  static bool isUrlAllowed(Uri url) {
    // Block sensitive admin actions from being accessed through the mobile app WebView.
    // These are intentionally enforced even in debug builds.
    if (_isSensitiveAdminUrl(url)) {
      DebugLogger.logWarn('WEBVIEW', 'Blocked sensitive admin URL: $url');
      return false;
    }

    // Document preview (non-PDF) uses `/admin/documents/serve/{id}` in WebView.
    if (isAdminDocumentServeUrl(url)) {
      DebugLogger.logInfo('WEBVIEW', 'URL allowed (admin document serve): ${url.toString()}');
      return true;
    }

    final allowedPatterns = AppConfig.getAllowedUrlPatterns();
    final urlString = url.toString();

    for (final pattern in allowedPatterns) {
      // Handle wildcard patterns
      if (pattern.contains('*')) {
        final regexPattern = pattern
            .replaceAll('.', r'\.')
            .replaceAll('*', '.*')
            .replaceAll(':', r'\:');
        final regex = RegExp('^$regexPattern');
        if (regex.hasMatch(urlString)) {
          DebugLogger.logInfo('WEBVIEW', 'URL allowed (pattern): $urlString');
          return true;
        }
      } else if (urlString.startsWith(pattern)) {
        DebugLogger.logInfo('WEBVIEW', 'URL allowed (exact): $urlString');
        return true;
      }
    }

    // In debug mode, log blocked URLs but still allow them
    // In production, strictly enforce whitelist
    if (kDebugMode) {
      DebugLogger.logWarn(
        'WEBVIEW',
        'URL not in whitelist (allowed in debug): $urlString',
      );
      return true; // Allow in debug mode for development
    }

    DebugLogger.logWarn(
      'WEBVIEW',
      'URL blocked (not in whitelist): $urlString',
    );
    return false;
  }

  static bool _isSensitiveAdminUrl(Uri url) {
    // Only consider backend/admin-style paths. If there is no path, nothing to block.
    final path = url.path;

    // Normalize just in case
    final normalized = path.endsWith('/') && path.length > 1
        ? path.substring(0, path.length - 1)
        : path;

    // Blocklist of sensitive admin surfaces that should only be available in the web platform.
    // Note: we block /admin/assignments web pages to prevent public URL toggles from being accessed
    // via the embedded web platform inside the mobile app.
    const blockedPrefixes = <String>[
      '/admin/users',
      '/admin/plugins',
      '/admin/api',
      '/api-management',
      '/admin/push-notifications',
      '/admin/assignments',
    ];

    for (final prefix in blockedPrefixes) {
      if (normalized == prefix || normalized.startsWith('$prefix/')) {
        return true;
      }
    }

    return false;
  }

  /// Streamed file delivery for submitted documents (`?download=1` / serve).
  /// Must stay allowed in the WebView whitelist so previews can load in release.
  static bool isAdminDocumentServeUrl(Uri url) {
    if (url.scheme != 'http' && url.scheme != 'https') return false;
    final path = url.path;
    return path.startsWith('/admin/documents/serve/') ||
        path.startsWith('/admin/documents/download/');
  }

  /// True for assignment exports that require the WebView session cookie.
  ///
  /// Android routes these through [onDownloadStartRequest]; opening them with
  /// [launchUrl] runs in the system browser without cookies and hits the login page.
  static bool isFormAssignmentSessionDownloadUrl(Uri uri) {
    if (uri.scheme != 'http' && uri.scheme != 'https') {
      return false;
    }
    final path = uri.path;
    if (!path.contains('/forms/assignment_status/')) {
      return false;
    }
    return path.contains('/export_pdf') ||
        path.contains('/export_excel') ||
        path.contains('/validation_summary');
  }

  /// True when a saved offline bundle resolves an export/validation link to
  /// `file:///…/forms/assignment_status/…` — those handlers exist only on the
  /// server, so loading them in the WebView yields `net::ERR_FILE_NOT_FOUND`.
  static bool isOfflineBundleServerOnlyAssignmentExport(Uri? url) {
    if (url == null) return false;
    if (url.scheme != 'file') return false;
    final path = url.path;
    if (!path.contains('/forms/assignment_status/')) return false;
    return path.contains('/export_pdf') ||
        path.contains('/export_excel') ||
        path.contains('/validation_summary');
  }

  /// Whether a navigation is allowed inside a saved offline assignment WebView.
  ///
  /// Release builds enforce [isUrlAllowed] for http(s), which **does not**
  /// include `file:` URLs. WKWebView on iOS often invokes
  /// [InAppWebView.shouldOverrideUrlLoading] for `file:` loads (main frame and
  /// assets); Android may not, which made offline bundles appear to work only
  /// on Android. Local `file:` URLs under [bundleDirectoryPath] must be allowed.
  static bool isOfflineBundleNavigationAllowed(
    WebUri? webUri,
    String bundleDirectoryPath,
  ) {
    if (webUri == null) return true;
    final uri = Uri.tryParse(webUri.toString());
    if (uri == null) return false;

    if (uri.scheme == 'about') {
      return true;
    }

    if (uri.scheme == 'file') {
      return _isFileUrlUnderOfflineBundle(uri, bundleDirectoryPath);
    }

    return isUrlAllowed(uri);
  }

  static bool _isFileUrlUnderOfflineBundle(Uri fileUri, String bundleDirectoryPath) {
    assert(fileUri.scheme == 'file');
    String filePath;
    try {
      filePath = fileUri.toFilePath();
    } catch (_) {
      filePath = fileUri.path;
    }

    try {
      final bundleDir = Directory(bundleDirectoryPath);
      if (!bundleDir.existsSync()) return false;
      final bundleResolved = bundleDir.resolveSymbolicLinksSync();
      final fileResolved = File(filePath).resolveSymbolicLinksSync();
      return p.equals(bundleResolved, fileResolved) ||
          p.isWithin(bundleResolved, fileResolved);
    } catch (e, st) {
      DebugLogger.logWarn(
        'WEBVIEW',
        'offline bundle file URL check fallback: $e\n$st',
      );
      final normBundle = p.normalize(bundleDirectoryPath);
      final normFile = p.normalize(filePath);
      if (normFile == normBundle) return true;
      final sep = p.separator;
      final prefix = normBundle.endsWith(sep) ? normBundle : '$normBundle$sep';
      return normFile.startsWith(prefix);
    }
  }

  /// Validates if a URL string is allowed to load in WebView
  static bool isUrlStringAllowed(String? urlString) {
    if (urlString == null || urlString.isEmpty) {
      return false;
    }

    try {
      final uri = Uri.parse(urlString);
      return isUrlAllowed(uri);
    } catch (e) {
      DebugLogger.logError('Failed to parse URL for validation: $urlString');
      return false;
    }
  }

  static UnmodifiableListView<UserScript> getRequestInterceptorScripts({
    String? language,
  }) {
    final scripts = <UserScript>[
      // Do not inject a second CSP via <meta>: the backoffice (and website) already
      // send Content-Security-Policy headers. A stricter client CSP intersects with the
      // server's policy and blocks allowed third-party scripts/styles (e.g. cdnjs).
      // Suppress console messages from WebView pages
      UserScript(
        source: '''
          (function() {
            // Override console methods to suppress logging - do this as early as possible
            const noop = function() {};
            const originalConsole = window.console || {};
            Object.defineProperty(window, 'console', {
              value: {
                log: noop,
                info: noop,
                warn: noop,
                error: noop,
                debug: noop,
                trace: noop,
                table: noop,
                group: noop,
                groupEnd: noop,
                groupCollapsed: noop,
                time: noop,
                timeEnd: noop,
                assert: noop,
                clear: originalConsole.clear || noop,
                count: noop,
                dir: noop,
                dirxml: noop,
                profile: noop,
                profileEnd: noop,
                timeStamp: noop,
                context: originalConsole.context || noop,
              },
              writable: false,
              configurable: false
            });

            // Suppress uncaught errors and unhandled promise rejections
            window.addEventListener('error', function(event) {
              event.preventDefault();
              event.stopPropagation();
              return false;
            }, true);

            window.addEventListener('unhandledrejection', function(event) {
              event.preventDefault();
              event.stopPropagation();
              return false;
            });

            // Also suppress errors at the window.onerror level
            window.onerror = function() {
              return true; // Suppress error
            };

            window.onunhandledrejection = function() {
              return true; // Suppress unhandled rejection
            };
          })();
        ''',
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      ),
      // Inject Tajawal font for Arabic - load font early
      if (language == 'ar')
        UserScript(
          source: '''
            (function() {
              function loadTajawal() {
                if (document.querySelector('link[href*="Tajawal"]')) return;
                var link = document.createElement('link');
                link.href = 'https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap';
                link.rel = 'stylesheet';
                link.crossOrigin = 'anonymous';
                var parent = document.head || document.documentElement;
                if (parent) parent.appendChild(link);
              }
              if (document.head) {
                loadTajawal();
              } else {
                document.addEventListener('DOMContentLoaded', loadTajawal);
              }
            })();
          ''',
          injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
        ),
      // Inject Tajawal font for Arabic - apply CSS at document end
      if (language == 'ar')
        UserScript(
          source: '''
            (function() {
              function applyTajawalFont() {
                // Remove any existing Tajawal style injection to avoid duplicates
                const existingStyle = document.getElementById('tajawal-font-injection');
                if (existingStyle) {
                  existingStyle.remove();
                }

                // Inject CSS to apply Tajawal font with high specificity
                const style = document.createElement('style');
                style.id = 'tajawal-font-injection';
                style.textContent = `
                  * {
                    font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                  }
                  body, html {
                    font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                  }
                  [dir="rtl"], .rtl, [dir="rtl"] *, .rtl * {
                    font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                  }
                  h1, h2, h3, h4, h5, h6, p, span, div, a, button, input, textarea, select, label, li, td, th {
                    font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                  }
                `;
                document.head.appendChild(style);
              }

              // Apply immediately if DOM is ready
              if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', applyTajawalFont);
              } else {
                applyTajawalFont();
              }

              // Also apply after a short delay to catch dynamically loaded content
              setTimeout(applyTajawalFont, 100);
              setTimeout(applyTajawalFont, 500);
              setTimeout(applyTajawalFont, 1000);
            })();
          ''',
          injectionTime: UserScriptInjectionTime.AT_DOCUMENT_END,
        ),
      // Inject mobile app detection flag
      UserScript(
        source: '''
          (function() {
            window.isMobileApp = true;
            window.humdatabankMobileApp = true;
            window.IFRCMobileApp = true;
            var root = document.documentElement;
            if (root) {
              root.setAttribute('data-mobile-app', 'true');
              root.classList.add('mobile-app');
            }
          })();
        ''',
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      ),
      // Bridge for auth-drafts.js → Flutter [addJavaScriptHandler('authDraftTelemetry')].
      // Page console is intentionally no-op in this WebView; drafts must not rely on console.*.
      UserScript(
        source: r'''
(function() {
  window.__ifrcAuthDraftsDartLog = function(payload) {
    try {
      var s = (typeof payload === 'string') ? payload : JSON.stringify(payload);
      if (window.flutter_inappwebview && typeof window.flutter_inappwebview.callHandler === 'function') {
        window.flutter_inappwebview.callHandler('authDraftTelemetry', s);
      }
    } catch (e) { /* no-op */ }
  };
})();
''',
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      ),
      // Inject CSS to improve scrolling smoothness and match Flutter's native scrolling feel
      UserScript(
        source: '''
          (function() {
            function applySmoothScrolling() {
              const style = document.createElement('style');
              style.id = 'smooth-scrolling-injection';

              // Remove existing style if present
              const existing = document.getElementById('smooth-scrolling-injection');
              if (existing) {
                existing.remove();
              }

              style.textContent = `
                html, body {
                  -webkit-overflow-scrolling: touch !important;
                  overflow-scrolling: touch !important;
                  overscroll-behavior: contain !important;
                  -webkit-tap-highlight-color: transparent !important;
                  /* Enable momentum scrolling like Flutter */
                  -webkit-transform: translate3d(0, 0, 0) !important;
                  transform: translate3d(0, 0, 0) !important;
                }
                /* Improve scrolling performance for scrollable containers */
                [style*="overflow"], [class*="scroll"], [class*="overflow"] {
                  -webkit-overflow-scrolling: touch !important;
                }
                /* Remove tap highlight for better touch response */
                * {
                  -webkit-tap-highlight-color: transparent !important;
                }
              `;

              if (document.head) {
                document.head.appendChild(style);
              } else {
                document.addEventListener('DOMContentLoaded', function() {
                  document.head.appendChild(style);
                });
              }
            }

            // Apply immediately if possible
            if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', applySmoothScrolling);
            } else {
              applySmoothScrolling();
            }

            // Also apply after page fully loads
            window.addEventListener('load', applySmoothScrolling);
          })();
        ''',
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      ),
      UserScript(
        source:
            '''
        (function() {
          const correctBackendUrl = '${AppConfig.backendUrl}';
          const backendPatterns = [
            'http://127.0.0.1:5000',
            'http://localhost:5000',
            'https://backoffice-databank.fly.dev',
            'https://databank-stage.ifrc.org',
            'http://backoffice:5000',
            '10.0.2.2:5000'
          ];

          function replaceBackendUrl(url) {
            if (!url || typeof url !== 'string') return url;

            for (const pattern of backendPatterns) {
              if (url.includes(pattern)) {
                url = url.split(pattern).join(correctBackendUrl);
                break;
              }
            }

            if (url.includes('/api/') && !url.startsWith(correctBackendUrl)) {
              const apiIndex = url.indexOf('/api/');
              if (apiIndex !== -1) {
                const apiPath = url.substring(apiIndex);
                url = correctBackendUrl + apiPath;
              }
            }

            return url;
          }

          const originalFetch = window.fetch;
          window.fetch = function(input, init) {
            let url;
            let options = init ? {...init} : {};

            if (typeof input === 'string') {
              url = replaceBackendUrl(input);
            } else if (input instanceof Request) {
              url = replaceBackendUrl(input.url);
              options = {
                method: input.method,
                headers: input.headers,
                body: input.body,
                mode: input.mode,
                credentials: input.credentials,
                cache: input.cache,
                redirect: input.redirect,
                referrer: input.referrer,
                integrity: input.integrity,
                ...options
              };
            } else {
              url = replaceBackendUrl(String(input));
            }

            if (typeof input === 'string') {
              return originalFetch.call(this, url, options);
            } else {
              return originalFetch.call(this, new Request(url, options));
            }
          };

          const originalOpen = XMLHttpRequest.prototype.open;
          XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
            url = replaceBackendUrl(url);
            return originalOpen.call(this, method, url, async !== false, user, password);
          };
        })();
      ''',
        injectionTime: UserScriptInjectionTime.AT_DOCUMENT_START,
      ),
    ];

    return UnmodifiableListView(scripts);
  }

  static final UnmodifiableListView<UserScript> requestInterceptorScripts =
      getRequestInterceptorScripts();

  /// Settings for opening a saved assignment bundle from disk (`file://` HTML + assets).
  static InAppWebViewSettings offlineAssignmentBundleSettings(
    String bundleDirectoryPath,
  ) {
    final access = WebUri(Uri.directory(bundleDirectoryPath).toString());
    final s = defaultSettings();
    return InAppWebViewSettings(
      javaScriptEnabled: s.javaScriptEnabled,
      domStorageEnabled: s.domStorageEnabled,
      databaseEnabled: s.databaseEnabled,
      useHybridComposition: s.useHybridComposition,
      allowsInlineMediaPlayback: s.allowsInlineMediaPlayback,
      mediaPlaybackRequiresUserGesture: s.mediaPlaybackRequiresUserGesture,
      supportMultipleWindows: s.supportMultipleWindows,
      verticalScrollBarEnabled: s.verticalScrollBarEnabled,
      horizontalScrollBarEnabled: s.horizontalScrollBarEnabled,
      disableVerticalScroll: s.disableVerticalScroll,
      disableHorizontalScroll: s.disableHorizontalScroll,
      supportZoom: s.supportZoom,
      builtInZoomControls: s.builtInZoomControls,
      displayZoomControls: s.displayZoomControls,
      transparentBackground: s.transparentBackground,
      mixedContentMode: s.mixedContentMode,
      allowingReadAccessTo: access,
      allowFileAccess: true,
      allowFileAccessFromFileURLs: true,
      allowUniversalAccessFromFileURLs: true,
    );
  }

  static InAppWebViewSettings defaultSettings({
    bool allowMixedContent = false,
  }) {
    return InAppWebViewSettings(
      javaScriptEnabled: true,
      domStorageEnabled: true,
      databaseEnabled: true,
      useHybridComposition: true,
      allowsInlineMediaPlayback: true,
      mediaPlaybackRequiresUserGesture: false,
      supportMultipleWindows: false,
      // Enable vertical scrolling and ensure smooth scrolling
      verticalScrollBarEnabled: true,
      horizontalScrollBarEnabled: true,
      // Improve scrolling performance - ensure scrolling is enabled
      disableVerticalScroll: false,
      disableHorizontalScroll: false,
      // Ensure gestures work properly
      supportZoom: false, // Disable zoom to avoid gesture conflicts
      builtInZoomControls: false,
      displayZoomControls: false,
      // Performance optimizations for smooth scrolling
      // These settings help match Flutter's native scrolling feel
      transparentBackground: false,
      mixedContentMode: allowMixedContent
          ? MixedContentMode.MIXED_CONTENT_ALWAYS_ALLOW
          : MixedContentMode.MIXED_CONTENT_NEVER_ALLOW,
      // Security: rely on the document's own CSP response headers; URL allowlisting
      // remains in [isUrlAllowed] / shouldOverrideUrlLoading.
    );
  }

  static Future<void> applyPostCreationSettings(
    InAppWebViewController controller, {
    bool allowMixedContent = false,
  }) async {
    if (allowMixedContent) {
      await controller.setSettings(
        settings: InAppWebViewSettings(
          mixedContentMode: MixedContentMode.MIXED_CONTENT_ALWAYS_ALLOW,
        ),
      );
    }
  }

  /// Reinforces Tajawal from [InAppWebView.onLoadStop] when the app language is Arabic.
  /// [getRequestInterceptorScripts] already injects at document start/end; this is idempotent
  /// and uses a distinct style id for late-loaded markup.
  static const String arabicTajawalPostLoadEvaluateSource = r'''
(function() {
  const link = document.createElement('link');
  link.href = 'https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap';
  link.rel = 'stylesheet';
  link.crossOrigin = 'anonymous';
  if (!document.querySelector('link[href*="Tajawal"]')) {
    document.head.appendChild(link);
  }
  const styleId = 'tajawal-font-injection-final';
  let style = document.getElementById(styleId);
  if (!style) {
    style = document.createElement('style');
    style.id = styleId;
    document.head.appendChild(style);
  }
  style.textContent = `
    * {
      font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
    }
    body, html {
      font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
    }
    [dir="rtl"], .rtl, [dir="rtl"] *, .rtl * {
      font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
    }
    h1, h2, h3, h4, h5, h6, p, span, div, a, button, input, textarea, select, label, li, td, th, .text-base, .text-sm, .text-lg, .text-xl, .text-2xl, .text-3xl, .text-4xl, .text-5xl, .text-6xl {
      font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
    }
  `;
})();''';

  /// Run from [InAppWebView.onLoadStop] via [InAppWebViewController.evaluateJavascript].
  /// Compact JSON (keeps under logger truncation): stylesheet counts + sample hrefs.
  static const String stylesheetLoadDiagEvaluateSource = r'''
(function() {
  function trunc(s, n) {
    s = String(s || '');
    return s.length > n ? s.substring(0, n) + '…' : s;
  }
  var blocked = 0;
  var rulePositive = 0;
  var sample = [];
  try {
    var n = document.styleSheets.length;
    for (var i = 0; i < n; i++) {
      var sh = document.styleSheets[i];
      var href = '';
      try { href = String(sh.href || ''); } catch (e0) { href = '?'; }
      var rules = -2;
      try {
        if (sh.cssRules) {
          rules = sh.cssRules.length;
          if (rules > 0) { rulePositive++; }
        }
      } catch (e1) {
        rules = -1;
        blocked++;
      }
      if (sample.length < 4) {
        sample.push({ href: trunc(href, 96), rules: rules });
      }
    }
  } catch (e) {
    return JSON.stringify({ err: trunc(String(e), 120) });
  }
  var linkHrefs = [];
  try {
    var nodes = document.querySelectorAll('link[rel*="stylesheet"]');
    for (var j = 0; j < nodes.length && linkHrefs.length < 5; j++) {
      linkHrefs.push(trunc(String(nodes[j].href || ''), 96));
    }
  } catch (e2) {}
  return JSON.stringify({
    u: trunc(String(document.URL || ''), 120),
    sheets: document.styleSheets.length,
    blocked: blocked,
    withRules: rulePositive,
    sample: sample,
    linkHrefs: linkHrefs
  });
})();''';

  static bool shouldIgnoreError(String? description) {
    if (description == null || description.isEmpty) {
      return false;
    }

    final descriptionLower = description.toLowerCase();

    const ignoredFragments = [
      'ERR_CONTENT_LENGTH_MISMATCH',
      'ERR_BLOCKED_BY_ORB',
      'ERR_BLOCKED_BY_RESPONSE',
      'ERR_HTTP_RESPONSE_CODE_FAILURE',
      'ERR_CONNECTION_REFUSED',
      'ERR_NETWORK_CHANGED',
      'ERR_INTERNET_DISCONNECTED',
      'connection refused',
      'net::err_connection_refused',
      'net::err_aborted',
      'net::err_failed',
      // These are often transient and don't prevent page from loading
      'failed to fetch',
      'networkerror',
      // iOS WKWebView: common when a navigation is cancelled/replaced (e.g.
      // policy decision) — not a user-facing load failure for the main frame.
      'webkiterrordomain',
      'frame load interrupted',
      'error 102',
    ];

    return ignoredFragments.any(
      (fragment) => descriptionLower.contains(fragment.toLowerCase()),
    );
  }
}
